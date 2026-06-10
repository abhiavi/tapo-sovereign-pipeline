# KLAP Firmware (1.5.0+) Media Download Investigation

**Issue**: HTTP 401 on media downloads despite correct credentials
**Root Cause**: Firmware 1.5.4 uses KLAP protocol which disabled standard HTTP Digest Auth for media

---

## Current pytapo Architecture

### API Calls (✅ WORKING)
- Uses KLAP transport from `kasa` library
- Handles AES encryption/decryption automatically
- ramesh:10102013 credentials work perfectly
- Can list recordings successfully

### Media Downloads (❌ NOT WORKING)
- Still uses legacy `HttpMediaSession`
- Attempts standard HTTP Digest Auth on port 8800
- KLAP cameras return HTTP 401 because this endpoint was disabled
- No KLAP wrapper for media requests

---

## KLAP Protocol Architecture

### What We Know
1. **KLAP is used for API calls** - Detected via `_isKLAP()` and uses `KlapTransport`
2. **KLAP uses AES encryption** - In `pytapo/media_stream/crypto.py`
3. **There's a DownloaderV2** - Uses HLS (HTTP Live Streaming) instead of raw media
4. **Version Detection** - KLAP v1 and v2 are supported

### What's Missing for Media Downloads
- Media requests are NOT wrapped in KLAP
- HttpMediaSession doesn't know about KLAP
- Media endpoint might:
  - Be on a different port
  - Require KLAP handshake first
  - Require AES encryption wrapper
  - Have moved to HLS endpoint instead

---

## Possible Solutions

### Option 1: Wrap Media Requests in KLAP ⭐ MOST LIKELY
**Approach**: Use KLAP transport for media HTTP requests

```python
# Instead of:
session = HttpMediaSession(...)  # Direct HTTP

# Could be:
klap_transport.send(media_request)  # KLAP-wrapped
```

**Implementation Needed**:
- Detect if device is KLAP
- Use KlapTransport to send media requests
- Handle AES encrypted responses

---

### Option 2: Use DownloaderV2 with HLS
**Approach**: Use HTTP Live Streaming instead of raw media download

The DownloaderV2 already exists and uses:
- HLS protocol
- ffmpeg for processing
- Different endpoints

**Status**: Incomplete in pytapo (marked as "not finished")

---

### Option 3: Different Media Endpoint for KLAP
**Approach**: KLAP cameras might expose media on different endpoint

Possible endpoints to try:
- `/stream` (current - fails with 401)
- `/media/stream`
- `/recording/stream`
- Different port (not 8800)

---

## Key Files to Modify

### 1. `pytapo/__init__.py` - Line 303
**Current**:
```python
def getMediaSession(self, stream_type: StreamType = None, start_time=""):
    ...
    return HttpMediaSession(...)  # Always returns this
```

**Needed**: Check if KLAP and handle differently

### 2. `pytapo/media_stream/session.py`
**Current**: Only HttpMediaSession exists

**Needed**: Either:
- Add KLAP support to HttpMediaSession, OR
- Create KlapMediaSession class

### 3. `pytapo/media_stream/crypto.py`
**Current**: Has AES helpers

**Usage**: Might need to use for KLAP media wrapping

---

## Investigation Tasks

### 1. Check pytapo GitHub Issues
**Search for**:
- "KLAP media"
- "KLAP download"
- "firmware 1.5 download"
- "HTTP 401 media"

### 2. Analyze KLAP Transport
**File**: `pytapo/transport/klap/klap.py`
- Uses `kasa.transports.KlapTransport` or `KlapTransportV2`
- Handles AES encryption automatically
- Media might need to use same transport

### 3. Test Media Endpoint
**Possible endpoints**:
```
/stream                    # Current - HTTP 401
/recording/stream
/media/stream
/api/media/stream
```

### 4. Check Port
- Current: 8800
- Possible alternatives: 8443, 443, 80

---

## Hypothesis

**Most Likely**: KLAP cameras require media requests to:
1. Use KlapTransport instead of raw HTTP
2. Send request as encrypted KLAP message
3. Receive response as encrypted KLAP message

**Evidence**:
- API calls work with KLAP → KLAP transport is working
- Media fails with 401 → Standard HTTP auth doesn't work
- DownloaderV2 exists → Community knows HTTP media is broken
- No secondary password exists → It's not a credential issue

---

## Next Steps

1. **Check pytapo GitHub** for KLAP media download issues/discussions
2. **Examine KlapTransport API** to understand how to send media requests
3. **Analyze HttpMediaSession** to see if it can be KLAP-enabled
4. **Test alternative endpoints** if KLAP wrapping doesn't work
5. **Consider DownloaderV2** as fallback if nothing else works

---

## Research Sources

- pytapo GitHub: https://github.com/JurajNyiri/pytapo
- kasa library (KLAP implementation): https://github.com/python-kasa/python-kasa
- KLAP protocol details: Reverse-engineered by pytapo/kasa community

---

**Status**: Ready for implementation once KLAP media strategy is confirmed
