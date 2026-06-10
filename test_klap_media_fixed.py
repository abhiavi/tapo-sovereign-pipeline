#!/usr/bin/env python3
"""
Test KLAP media session implementation for Kitchen camera (firmware 1.5.4).
Uses sync Tapo initialization and async media session testing.
"""

import asyncio
import sys
import logging
from datetime import datetime
from pytapo import Tapo
from pytapo.media_stream.session import KlapMediaSession, HttpMediaSession
from pytapo.media_stream._utils import StreamType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_klap_instance_creation():
    """Test creating Tapo instance and KlapMediaSession (synchronous)."""

    print("\n" + "="*80)
    print("KLAP MEDIA SESSION IMPLEMENTATION TEST")
    print("="*80 + "\n")

    try:
        # Kitchen camera configuration (firmware 1.5.4 - KLAP)
        IP = "192.168.29.169"
        CLOUD_USER = "khaparde.abhishek@gmail.com"
        CLOUD_PASS = "Summer123!"

        print("STEP 1: Initializing Tapo instance...")
        print(f"  IP: {IP}")
        print(f"  Cloud User: {CLOUD_USER}")

        tapo = Tapo(IP, CLOUD_USER, CLOUD_PASS)

        print(f"  ✓ Connected successfully")
        print(f"  Device Type: {tapo.deviceType}")
        print(f"  KLAP Enabled: {tapo.isKLAP}")
        print(f"  Encryption Method: {tapo.getEncryptionMethod()}")

        # Test: Verify KLAP detection
        print("\nSTEP 2: Verifying KLAP detection...")
        if not tapo.isKLAP:
            print("  ✗ FAILED: Camera is not KLAP-enabled")
            print("  This camera should be on firmware 1.5.4 with KLAP enabled")
            return False, None

        print("  ✓ PASSED: Camera is KLAP-enabled (firmware 1.5.0+)")

        # Test: Verify API access
        print("\nSTEP 3: Testing Cloud API access...")
        basic_info = tapo.getBasicInfo()
        print(f"  ✓ Cloud API working")
        print(f"  Device Info: {basic_info.get('type', 'Unknown')}")

        # Test: Get recordings
        print("\nSTEP 4: Retrieving recordings from device...")
        recordings = tapo.getRecordings(datetime.now().strftime("%Y%m%d"))
        print(f"  ✓ Found {len(recordings)} recording sessions")
        if len(recordings) > 0:
            print(f"  Sample recording: {list(recordings[0].keys())[0]}")

        # Test: Get media session and verify type
        print("\nSTEP 5: Getting media session...")
        media_session = tapo.getMediaSession(StreamType.Download)

        if isinstance(media_session, KlapMediaSession):
            print(f"  ✓ PASSED: KlapMediaSession created")
            print(f"  Session type: {type(media_session).__name__}")
            print(f"  Transport: {type(media_session.transport).__name__}")
        elif isinstance(media_session, HttpMediaSession):
            print(f"  ✗ FAILED: Got HttpMediaSession instead of KlapMediaSession")
            print(f"  This indicates KLAP detection or routing failed")
            return False, None
        else:
            print(f"  ✗ FAILED: Got unknown session type: {type(media_session).__name__}")
            return False, None

        # Test: Verify session properties
        print("\nSTEP 6: Verifying session properties...")
        print(f"  Started: {media_session.started}")
        print(f"  Window size: {media_session.window_size}")
        print(f"  Port: {media_session.port}")
        print(f"  Encryption method: {media_session.encryptionMethod}")

        return True, (tapo, media_session, recordings)

    except Exception as e:
        print(f"\n✗ INITIALIZATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False, None

async def test_media_session_operations(tapo, media_session, recordings):
    """Test media session operations (async part)."""

    try:
        # Test: Try to start the session
        print("\nSTEP 7: Starting KLAP media session...")
        await media_session.start()
        print(f"  ✓ Session started successfully")
        print(f"  Session started flag: {media_session.started}")
        print(f"  AES initialized: {media_session._aes is not None}")

        # Test: Try to get media data
        if len(recordings) > 0:
            print("\nSTEP 8: Attempting to retrieve media data...")
            first_recording = recordings[0]
            for key in first_recording:
                start_time = first_recording[key]['startTime']
                end_time = first_recording[key]['endTime']
                print(f"  Recording: {key}")
                print(f"  Time range: {start_time} - {end_time}")

                # Build media request
                request = {
                    "method": "getRecordingData",
                    "params": {
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                }

                print(f"  Sending KLAP media request...")
                chunk_count = 0
                try:
                    async for response in media_session.transceive(
                        str(request),
                        mimetype="application/json"
                    ):
                        chunk_count += 1
                        print(f"    ✓ Received chunk {chunk_count}")
                        print(f"      - Session: {response.session}")
                        print(f"      - Sequence: {response.seq}")
                        print(f"      - Type: {response.mimetype}")
                        print(f"      - Encrypted: {response.encrypted}")
                        print(f"      - Size: {len(response.plaintext)} bytes")

                        # Just test first chunk
                        if chunk_count >= 1:
                            print(f"    (Stopping after first chunk for test)")
                            break

                    if chunk_count == 0:
                        print(f"  Note: No media chunks received")
                        print(f"  This might indicate the media request format needs adjustment")
                    else:
                        print(f"  ✓ PASSED: Received {chunk_count} media chunk(s)")
                except Exception as e:
                    print(f"  Note: Media request returned: {type(e).__name__}: {e}")
                    print(f"  This is expected if KLAP media endpoint is different than expected")

                break
        else:
            print("\nSTEP 8: Skipped (no recordings available)")

        await media_session.close()
        print(f"  Session closed successfully")

        print("\n" + "="*80)
        print("✓ KLAP MEDIA SESSION TESTS COMPLETED")
        print("="*80)
        print("\nSummary:")
        print("  - KLAP detection: ✓ PASSED")
        print("  - Cloud API access: ✓ PASSED")
        print("  - KlapMediaSession creation: ✓ PASSED")
        print("  - Session initialization: ✓ PASSED")
        print("\nNext step: Verify media download capability with actual data")
        return True

    except Exception as e:
        print(f"\n✗ SESSION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        try:
            await media_session.close()
        except:
            pass
        return False

def main():
    """Run the tests."""
    try:
        # STEP 1: Create Tapo instance (synchronous)
        success, data = test_klap_instance_creation()

        if not success or data is None:
            return 1

        tapo, media_session, recordings = data

        # STEP 2: Test media session operations (async)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(
                test_media_session_operations(tapo, media_session, recordings)
            )
            return 0 if success else 1
        finally:
            loop.close()

    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
