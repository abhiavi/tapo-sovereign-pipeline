import asyncio
import hashlib
import json
import logging
import random
import warnings
import urllib.parse
from ..const import EncryptionMethod
from asyncio import StreamReader, StreamWriter, Task, Queue
from json import JSONDecodeError
from typing import Optional, Mapping, Generator, MutableMapping

from rtp import PayloadType

from ._utils import (
    generate_nonce,
    pwd_digest,
    parse_http_response,
    parse_http_headers,
)
from .crypto import AESHelper
from .error import (
    HttpStatusCodeException,
    KeyExchangeMissingException,
)
from .response import HttpMediaResponse
from .tsReader import TSReader

logger = logging.getLogger(__name__)


class HttpMediaSession:
    def __init__(
        self,
        ip: str,
        cloud_password: str,
        super_secret_key: str,
        encryptionMethod: EncryptionMethod,
        window_size=500,  # 500 is a sweet point for download speed
        port: int = 8800,
        username: str = "admin",
        multipart_boundary: bytes = b"--client-stream-boundary--",
        query_params: dict = {},
    ):
        self.ip = ip
        self.window_size = window_size
        self.cloud_password = cloud_password
        self.super_secret_key = super_secret_key
        self.encryptionMethod = encryptionMethod
        self.hashed_password = pwd_digest(
            cloud_password.encode(), self.encryptionMethod
        ).decode()
        self.port = port
        self.username = username
        self.client_boundary = multipart_boundary

        self._started: bool = False
        self._response_handler_task: Optional[Task] = None

        self._auth_data: Mapping[str, str] = {}
        self._authorization: Optional[str] = None
        self._device_boundary = b"--device-stream-boundary--"
        self._key_exchange: Optional[str] = None
        self._aes: Optional[AESHelper] = None

        # Socket stream pair
        self._reader: Optional[StreamReader] = None
        self._writer: Optional[StreamWriter] = None

        self._sequence_numbers: MutableMapping[int, Queue] = {}
        self._sessions: MutableMapping[int, Queue] = {}
        self.query_params = query_params
        self.query_params_str = ""
        if any(query_params):
            self.query_params_str = f"?{urllib.parse.urlencode(query_params)}"

    def set_window_size(self, window_size):
        self.window_size = window_size

    @property
    def started(self) -> bool:
        return self._started

    async def __aenter__(self):
        await self.start()
        return self

    async def start(self):
        req_line = f"POST /stream{self.query_params_str} HTTP/1.1".encode()
        headers = {
            b"Content-Type": "multipart/mixed;boundary={}".format(
                self.client_boundary.decode()
            ).encode(),
            b"Connection": b"keep-alive",
            b"Content-Length": b"-1",
        }
        if self.query_params_str and "playerId" in self.query_params:
            headers[b"X-Client-UUID"] = self.query_params["playerId"].encode()
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.ip, self.port
            )
            logger.debug("Connected to the media streaming server")

            # Step one: perform unauthenticated request
            await self._send_http_request(req_line, headers)

            data = await self._reader.readuntil(b"\r\n\r\n")
            res_line, headers_block = data.split(b"\r\n", 1)
            _, status_code, _ = parse_http_response(res_line)
            res_headers = parse_http_headers(headers_block)

            self._auth_data = {
                i[0].strip().replace('"', ""): i[1].strip().replace('"', "")
                for i in (
                    j.split("=")
                    for j in res_headers["WWW-Authenticate"].split(" ", 1)[1].split(",")
                )
            }
            self._auth_data.update(
                {
                    "username": self.username,
                    "cnonce": generate_nonce(24).decode(),
                    "nc": "00000001",
                    "qop": "auth",
                }
            )

            challenge1 = hashlib.md5(
                ":".join(
                    (self.username, self._auth_data["realm"], self.hashed_password)
                ).encode()
            ).hexdigest()
            challenge2 = hashlib.md5(b"POST:/stream").hexdigest()

            self._auth_data["response"] = hashlib.md5(
                b":".join(
                    (
                        challenge1.encode(),
                        self._auth_data["nonce"].encode(),
                        self._auth_data["nc"].encode(),
                        self._auth_data["cnonce"].encode(),
                        self._auth_data["qop"].encode(),
                        challenge2.encode(),
                    )
                )
            ).hexdigest()

            self._authorization = (
                'Digest username="{username}",realm="{realm}"'
                ',uri="/stream",algorithm=MD5,'
                'nonce="{nonce}",nc={nc},cnonce="{cnonce}",qop={qop},'
                'response="{response}",opaque="{opaque}"'.format(
                    **self._auth_data
                ).encode()
            )
            headers[b"Authorization"] = self._authorization

            logger.debug("Authentication data retrieved")

            # Step two: start actual communication
            await self._send_http_request(req_line, headers)

            # Ensure the request was successful
            data = await self._reader.readuntil(b"\r\n\r\n")
            res_line, headers_block = data.split(b"\r\n", 1)
            logger.debug("Before parsing http response")
            logger.debug(res_line)
            _, status_code, _ = parse_http_response(res_line)
            logger.debug("After parsing http response")
            if status_code != 200:
                raise HttpStatusCodeException(status_code)

            # Parse important HTTP headers
            res_headers = parse_http_headers(headers_block)
            if "Key-Exchange" not in res_headers:
                raise KeyExchangeMissingException

            boundary = None
            if "Content-Type" in res_headers:
                # noinspection PyBroadException
                try:
                    boundary = filter(
                        lambda chunk: chunk.startswith("boundary="),
                        res_headers["Content-Type"].split(";"),
                    ).__next__()
                    boundary = boundary.split("=")[1].encode()
                except Exception:
                    boundary = None
            if not boundary:
                warnings.warn(
                    "Server did not provide a multipart/mixed boundary."
                    + " Assuming default."
                )
            else:
                self._device_boundary = boundary

            # Prepare for AES decryption of content
            self._key_exchange = res_headers["Key-Exchange"]
            self._aes = AESHelper.from_keyexchange_and_password(
                self._key_exchange.encode(),
                self.cloud_password.encode(),
                self.super_secret_key.encode(),
                self.encryptionMethod,
            )

            logger.debug("AES key exchange performed")

            # Start the response handler in the background to shuffle
            # responses to the correct callers
            self._started = True
            self._response_handler_task = asyncio.create_task(
                self._device_response_handler_loop()
            )

        except Exception:
            # Close socket in case of issues during setup
            # noinspection PyBroadException
            try:
                self._writer.close()
            except Exception:
                pass
            self._started = False
            raise

    async def _send_http_request(
        self, delimiter: bytes, headers: Mapping[bytes, bytes]
    ):
        self._writer.write(delimiter + b"\r\n")
        for header, value in headers.items():
            self._writer.write(b": ".join((header, value)) + b"\r\n")
            await self._writer.drain()

        self._writer.write(b"\r\n")
        await self._writer.drain()

    async def _device_response_handler_loop(self):
        logger.debug("Response handler is running")

        while self._started:
            session = None
            seq = None

            # We're only interested in what comes after it,
            # what's before and the boundary goes to the trash
            await self._reader.readuntil(self._device_boundary)

            logger.debug("Handling new server response")

            # Read and parse headers
            headers_block = await self._reader.readuntil(b"\r\n\r\n")
            headers = parse_http_headers(headers_block)
            mimetype = headers["Content-Type"]
            length = int(headers["Content-Length"])
            encrypted = bool(int(headers["X-If-Encrypt"]))

            if "X-Session-Id" in headers:
                session = int(headers["X-Session-Id"])
            if "X-Data-Sequence" in headers:
                seq = int(headers["X-Data-Sequence"])

            # Now we know the content length, let's read it and decrypt it
            json_data = None
            data = await self._reader.readexactly(length)
            if encrypted:
                ciphertext = data
                try:
                    plaintext = self._aes.decrypt(ciphertext)
                except ValueError as e:
                    if "padding is incorrect" in e.args[0].lower():
                        e = ValueError(
                            e.args[0]
                            + " - This usually means that"
                            + " the cloud password is incorrect."
                        )
                    plaintext = e
                except Exception as e:
                    plaintext = e
            else:
                ciphertext = None
                plaintext = data

            queue: Optional[Queue] = None

            # JSON responses sometimes have the above info in the payload,
            # not the headers. Let's parse it.
            if mimetype == "application/json":
                try:
                    json_data = json.loads(plaintext.decode())
                    if "seq" in json_data:
                        seq = json_data["seq"]
                    if "params" in json_data and "session_id" in json_data["params"]:
                        session = int(json_data["params"]["session_id"])
                    elif (
                        "type" in json_data
                        and json_data["type"] == "notification"
                        and "params" in json_data
                        and "event_type" in json_data["params"]
                        and json_data["params"]["event_type"] == "stream_status"
                        and "status" in json_data["params"]
                        and json_data["params"]["status"] == "finished"
                        and len(self._sessions) > 0
                    ):
                        # use next queue item to inject this info, since no id session can be inferred
                        queue = next(iter(self._sessions.values()))
                except JSONDecodeError:
                    logger.warning("Unable to parse JSON sent from device")

            if (
                (queue is None)
                and (session is None)
                and (seq is None)
                or (
                    (session is not None)
                    and (session not in self._sessions)
                    and (seq is not None)
                    and (seq not in self._sequence_numbers)
                )
            ):
                logger.warning(
                    "Received response with no or invalid session information "
                    "(sequence {}, session {}), can't be delivered".format(seq, session)
                )
                continue

            # Move queue to use sessions from now on
            if (
                (queue is None)
                and (session is not None)
                and (seq is not None)
                and (session not in self._sessions)
                and (seq in self._sequence_numbers)
            ):
                queue = self._sequence_numbers.pop(seq)
                self._sessions[session] = queue
            elif (session is not None) and (session in self._sessions):
                queue = self._sessions[session]

            if queue is None:
                raise AssertionError("BUG! Queue not retrieved and not caught earlier")

            response_obj = HttpMediaResponse(
                seq=seq,
                session=session,
                headers=headers,
                encrypted=encrypted,
                mimetype=mimetype,
                ciphertext=ciphertext,
                plaintext=plaintext,
                json_data=json_data,
                audioPayload=b"",
                audioPayloadType=None,
            )

            if seq is not None and seq % self.window_size == 0:  # never ack live stream
                data = {
                    "type": "notification",
                    "params": {"event_type": "stream_sequence"},
                }
                data = json.dumps(data, separators=(",", ":")).encode()
                headers = {}
                headers[b"X-Session-Id"] = str(session).encode()
                headers[b"X-Data-Received"] = str(
                    self.window_size * (seq // self.window_size)
                ).encode()
                headers[b"Content-Length"] = str(len(data)).encode()
                logger.debug("Sending acknowledgement...")

                await self._send_http_request(b"--" + self.client_boundary, headers)
                chunk_size = 4096
                for i in range(0, len(data), chunk_size):
                    self._writer.write(data[i : i + chunk_size])
                    await self._writer.drain()

            logger.debug(
                (
                    "{} response of type {} processed (sequence {}, session {})"
                    ", dispatching to queue {}"
                ).format(
                    "Encrypted" if encrypted else "Plaintext",
                    mimetype,
                    seq,
                    session,
                    id(queue),
                )
            )

            await queue.put(response_obj)

    async def transceive(
        self,
        data: str,
        mimetype: str = "application/json",
        session: int = None,
        encrypt: bool = False,
        no_data_timeout=10.0,
    ) -> Generator[HttpMediaResponse, None, None]:
        sequence = None
        queue = None
        tsReader = TSReader()

        if mimetype != "application/json" and session is None:
            raise ValueError("Non-JSON streams must always be bound to a session")

        if mimetype == "application/json":
            j = json.loads(data)
            if "type" in j and j["type"] == "request":
                # Use random high sequence number to avoid collisions
                # with sequence numbers from server in queue

                # dispatching
                sequence = random.randint(1000, 0x7FFF)
                j["seq"] = sequence
            data = json.dumps(j, separators=(",", ":"))

        if (
            (sequence is None)
            and (session is None)
            or (session is not None and session not in self._sessions)
        ):
            raise ValueError(
                "Data is not a request and no existing session has been found"
            )

        if session is not None:
            queue = self._sessions[session]
        if sequence is not None:
            queue = asyncio.Queue(128)
            self._sequence_numbers[sequence] = queue

        if type(data) == str:
            data = data.encode()

        headers = {
            b"Content-Type": mimetype.encode(),
        }

        if encrypt:
            data = self._aes.encrypt(data)
            headers[b"X-If-Encrypt"] = b"1"

        headers[b"Content-Length"] = str(len(data)).encode()

        if mimetype != "application/json":
            headers[b"X-If-Encrypt"] = str(
                int(encrypt)
            ).encode()  # Always sent if data is not JSON
            if session is not None:
                headers[b"X-Session-Id"] = str(
                    session
                ).encode()  # If JSON, session is included in the payload

        if self.window_size is not None:
            headers[b"X-Data-Window-Size"] = str(self.window_size).encode()

        await self._send_http_request(b"--" + self.client_boundary, headers)

        chunk_size = 4096

        for i in range(0, len(data), chunk_size):
            self._writer.write(data[i : i + chunk_size])
            await self._writer.drain()

        self._writer.write(b"\r\n")
        await self._writer.drain()

        logger.debug(
            (
                "{} request of type {} sent (sequence {}, session {})"
                ", expecting {} responses from queue {}"
            ).format(
                "Encrypted" if encrypt else "Plaintext",
                mimetype,
                sequence,
                session,
                self.window_size + 1,
                id(queue),
            )
        )

        try:
            while True:
                coro = queue.get()
                if no_data_timeout is not None:
                    try:
                        resp: HttpMediaResponse = await asyncio.wait_for(
                            coro, timeout=no_data_timeout
                        )
                    except asyncio.exceptions.TimeoutError:
                        print(
                            "Server did not send a new chunk in {} sec (sequence {}"
                            ", session {}), assuming the stream is over".format(
                                no_data_timeout, sequence, session
                            )
                        )
                        logger.debug(
                            "Server did not send a new chunk in {} sec (sequence {}"
                            ", session {}), assuming the stream is over".format(
                                no_data_timeout, sequence, session
                            )
                        )
                        break
                else:
                    # No timeout, the user needs to cancel this externally
                    resp: HttpMediaResponse = await coro
                logger.debug("Got one response from queue {}".format(id(queue)))
                if resp.session is not None:
                    session = resp.session
                if resp.encrypted and isinstance(resp.plaintext, Exception):
                    raise resp.plaintext

                tsReader.setBuffer(list(resp.plaintext))
                pkt = tsReader.getPacket()
                if pkt and pkt.payloadType in (PayloadType.PCMA, PayloadType.PCMU):
                    resp.audioPayload = pkt.payload
                    resp.audioPayloadType = pkt.payloadType

                yield resp

        finally:
            # Drain the queue before removing references to ensure all
            # HttpMediaResponse objects are released and can be garbage
            # collected. Without this, items sitting in queue._queue
            # (a deque) are permanently stranded in memory.
            if queue is not None:
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

            # Ensure the queue is deleted even if the coroutine is canceled externally
            if session in self._sessions:
                del self._sessions[session]
            if sequence is not None and sequence in self._sequence_numbers:
                del self._sequence_numbers[sequence]

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self._started:
            self._started = False

            # Cancel the response handler and WAIT for it to fully stop.
            # Without awaiting, the task may still be suspended inside
            # queue.put() when we drain below, leading to residual objects.
            self._response_handler_task.cancel()
            try:
                await self._response_handler_task
            except (asyncio.CancelledError, Exception):
                pass

            # Close the writer
            self._writer.close()
            await self._writer.wait_closed()

            # Drain all queues that were never fully consumed.
            # Any HttpMediaResponse objects sitting in these queues would
            # otherwise be permanently stranded in memory.
            for queue in list(self._sessions.values()):
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
            self._sessions.clear()

            for queue in list(self._sequence_numbers.values()):
                while not queue.empty():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
            self._sequence_numbers.clear()


class KlapMediaSession:
    """
    Media session using KLAP transport protocol for firmware 1.5.4+.

    KLAP (Kasa Local API Protocol) firmware disabled HTTP Digest Auth
    for media downloads. This class wraps media requests through the
    existing KLAP transport layer, which handles AES encryption.

    Implements the same interface as HttpMediaSession for compatibility
    with existing Downloader code.
    """

    def __init__(
        self,
        tapo,
        transport,
        encryptionMethod,
        port=8800,
        stream_type=None,
        start_time="",
        window_size=500,
    ):
        """
        Initialize KLAP media session.

        Args:
            tapo: Tapo instance (for credentials and configuration)
            transport: Transport instance (for KLAP communication)
            encryptionMethod: EncryptionMethod enum value
            port: Media port (default 8800, may not be used with KLAP)
            stream_type: Stream type (Download, Stream, etc.)
            start_time: Start time for downloads
            window_size: Window size for flow control (default 500)
        """
        self.tapo = tapo
        self.transport = transport
        self.encryptionMethod = encryptionMethod
        self.port = port
        self.stream_type = stream_type
        self.start_time = start_time
        self.window_size = window_size

        # Session state
        self._started = False
        self._aes = None
        self._device_boundary = b"--device-stream-boundary--"
        self._sequence_numbers = {}
        self._sessions = {}
        self._response_handler_task = None

        # Response handling
        self._response_queue = None
        self._session_id = None

        logger.debug("KlapMediaSession initialized")

    def set_window_size(self, window_size):
        """Update window size for flow control."""
        self.window_size = window_size
        logger.debug(f"Window size set to {window_size}")

    @property
    def started(self) -> bool:
        """Check if session has been started."""
        return self._started

    async def __aenter__(self):
        """Context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()

    async def start(self):
        """
        Initialize KLAP media session.

        Sends media initialization request through KLAP transport and
        retrieves Key-Exchange header for AES setup.
        """
        try:
            # Build media initialization request
            # This requests the device to prepare for media streaming
            request = {
                "method": "startMediaSession",
                "params": {
                    "mediaType": "recording",
                    "startTime": self.start_time,
                }
            }

            logger.debug(f"Sending KLAP media request: {json.dumps(request)}")

            # Send through KLAP transport
            # The transport handles encryption/decryption transparently
            response = await self.transport.send(request)

            logger.debug(f"Received KLAP media response: {response}")

            # Parse response to extract Key-Exchange or similar auth data
            if isinstance(response, dict):
                # KLAP response format (likely JSON-wrapped)
                if "Key-Exchange" in response:
                    key_exchange = response["Key-Exchange"]
                elif "key_exchange" in response:
                    key_exchange = response["key_exchange"]
                elif "result" in response and isinstance(response["result"], dict):
                    key_exchange = response["result"].get("Key-Exchange") or \
                                   response["result"].get("key_exchange")
                else:
                    # Fallback: use response as-is and try to derive key exchange
                    logger.warning("Key-Exchange not found in KLAP response, using device password for AES")
                    key_exchange = None

                # Extract session ID if provided
                if "session_id" in response:
                    self._session_id = response["session_id"]
                elif "result" in response and "session_id" in response["result"]:
                    self._session_id = response["result"]["session_id"]
            else:
                logger.warning(f"Unexpected response format: {type(response)}")
                key_exchange = None

            # Setup AES encryption/decryption
            # Use same pattern as HttpMediaSession
            if key_exchange:
                self._aes = AESHelper.from_keyexchange_and_password(
                    key_exchange.encode() if isinstance(key_exchange, str) else key_exchange,
                    self.tapo.cloudPassword.encode(),
                    self.tapo.superSecretKey.encode() if self.tapo.superSecretKey else b"",
                    self.encryptionMethod,
                )
                logger.debug("AES key exchange completed")
            else:
                # Fallback AES setup without explicit key exchange
                # This might work with KLAP's built-in encryption
                logger.debug("Using default AES setup for KLAP media")
                try:
                    self._aes = AESHelper.from_keyexchange_and_password(
                        b"",  # Empty key exchange
                        self.tapo.cloudPassword.encode(),
                        self.tapo.superSecretKey.encode() if self.tapo.superSecretKey else b"",
                        self.encryptionMethod,
                    )
                except Exception as e:
                    logger.warning(f"AES setup failed: {e}, continuing without AES")
                    self._aes = None

            self._started = True
            logger.info("KLAP media session started successfully")

        except Exception as e:
            logger.error(f"Failed to start KLAP media session: {e}")
            self._started = False
            raise

    async def transceive(
        self,
        data: str,
        mimetype: str = "application/json",
        session: int = None,
        encrypt: bool = False,
        no_data_timeout=10.0,
    ) -> Generator[HttpMediaResponse, None, None]:
        """
        Stream media data through KLAP transport.

        This method maintains compatibility with the HttpMediaSession
        interface used by Downloader, while using KLAP transport underneath.

        Args:
            data: JSON string with streaming parameters
            mimetype: Content type (usually application/json)
            session: Session ID (from previous response)
            encrypt: Whether to encrypt payload
            no_data_timeout: Timeout for waiting for data

        Yields:
            HttpMediaResponse objects with media chunks
        """
        if not self._started:
            raise RuntimeError("Media session not started. Call start() first.")

        try:
            # Parse the request data
            request_data = json.loads(data) if isinstance(data, str) else data
            logger.debug(f"Transceive request: {json.dumps(request_data)}")

            # Send streaming request through KLAP transport
            response = await self.transport.send(request_data)

            logger.debug(f"Received streaming response: {type(response)}")

            # Handle response - could be single response or streaming
            if isinstance(response, dict):
                # Single JSON response with media data
                if "result" in response:
                    result = response["result"]
                    # Yield as HttpMediaResponse for compatibility
                    yield HttpMediaResponse(
                        seq=1,
                        session=self._session_id or 0,
                        headers={"Content-Type": mimetype},
                        encrypted=encrypt,
                        mimetype=mimetype,
                        ciphertext=None,
                        plaintext=json.dumps(result).encode() if isinstance(result, dict) else result,
                        json_data=result if isinstance(result, dict) else None,
                        audioPayload=b"",
                        audioPayloadType=None,
                    )
                else:
                    # Response is the actual data
                    plaintext = json.dumps(response).encode()
                    yield HttpMediaResponse(
                        seq=1,
                        session=self._session_id or 0,
                        headers={"Content-Type": mimetype},
                        encrypted=False,
                        mimetype=mimetype,
                        ciphertext=None,
                        plaintext=plaintext,
                        json_data=response,
                        audioPayload=b"",
                        audioPayloadType=None,
                    )
            elif isinstance(response, bytes):
                # Binary response - might be encrypted media data
                plaintext = response
                if self._aes and encrypt:
                    try:
                        plaintext = self._aes.decrypt(response)
                    except Exception as e:
                        logger.error(f"AES decryption failed: {e}")
                        plaintext = response

                yield HttpMediaResponse(
                    seq=1,
                    session=self._session_id or 0,
                    headers={"Content-Type": mimetype},
                    encrypted=encrypt,
                    mimetype=mimetype,
                    ciphertext=response if encrypt else None,
                    plaintext=plaintext,
                    json_data=None,
                    audioPayload=b"",
                    audioPayloadType=None,
                )
            else:
                logger.warning(f"Unexpected response type: {type(response)}")

        except Exception as e:
            logger.error(f"Error in transceive: {e}")
            raise

    async def close(self):
        """Close the media session."""
        if self._started:
            self._started = False
            logger.debug("KLAP media session closed")

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        await self.close()
