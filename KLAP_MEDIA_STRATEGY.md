# KLAP Media Download Strategy

**Problem**: Firmware 1.5.4 (KLAP) disabled standard HTTP Digest Auth for media downloads
**Current Status**: pytapo doesn't have a working solution for KLAP media downloads
**Solution**: Need to implement KLAP-aware media handling

---

## Why HTTP 401 is Happening

```
Your Request Path (Currently):
1. Tapo(ip, email, password, device_username="ramesh", device_password="10102013")
2. Uses KLAP transport for API → getRecordings() ✅ WORKS
3. Uses HttpMediaSession for media → HTTP 401 ❌ FAILS

The Disconnect:
- API layer: Uses KLAP encrypted transport ✅
- Media layer: Still tries legacy HTTP Digest Auth ❌
- Camera firmware 1.5.4: Disabled HTTP Digest endpoint for media
```

---

## Three Viable Approaches

### Approach A: KLAP-Wrapped Media Request ⭐ MOST LIKELY

**Concept**: Use KlapTransport to send media requests instead of raw HTTP

**How it might work**:
```python
# Instead of HttpMediaSession making raw HTTP request:
GET /stream HTTP/1.1
Authorization: Digest ...

# Send through KLAP:
klap_transport.send({
    "method": "get_stream",
    "params": {
        "start_time": 1234567890,
        "end_time": 1234567900
    }
})
```

**Challenges**:
- Need to understand KLAP protocol for media
- KlapTransport may not support binary streaming
- Response handling would be different

**Implementation**:
1. Modify `Tapo.getMediaSession()` to detect KLAP
2. Return KlapMediaSession instead of HttpMediaSession for KLAP cameras
3. Implement KlapMediaSession to use klapTransport

---

### Approach B: HLS Streaming via DownloaderV2 ⭐ FALLBACK

**Concept**: Use HTTP Live Streaming (HLS) instead of raw media download

**Current Status**: DownloaderV2 exists but is "not finished"

**How it works**:
```python
# Uses HLS playlist endpoint
GET /recording/hls/playlist.m3u8
# Returns .ts (transport stream) segments
# Pipes to ffmpeg for MP4 conversion
```

**Advantages**:
- Already partially implemented in pytapo
- HLS might not be blocked like raw media
- Standard streaming approach

**Challenges**:
- Requires ffmpeg dependency
- Slower than direct media download
- HLS endpoint might also require KLAP

**Implementation**:
1. Complete DownloaderV2 implementation
2. Add error handling and retries
3. Test with KLAP camera

---

### Approach C: Different Media Endpoint

**Concept**: KLAP cameras might expose media on different endpoint/port

**Possible endpoints**:
```
/stream                  # Current (fails with 401)
/recording/download
/recording/stream
/media/download
/api/recording/stream
```

**Port alternatives**:
```
8800  # Current
8443  # HTTPS
443
20002 # Sometimes used by TP-Link
```

**Implementation**:
1. Try alternative endpoints with HttpMediaSession
2. Monitor which ones respond without 401
3. Use working endpoint

---

## Recommended Implementation Path

### Phase 1: Investigate (Done ✓)
- [x] Identify KLAP as root cause
- [x] Confirm ramesh:10102013 is correct
- [x] Understand pytapo architecture

### Phase 2: Implement Approach A (KLAP-Wrapped)

**Steps**:
1. **Understand KlapTransport capabilities**
   - Check if it can handle binary media responses
   - Check if it supports streaming requests

2. **Create KlapMediaSession class**
   ```python
   class KlapMediaSession:
       def __init__(self, tapo, start_time, end_time, time_correction):
           self.tapo = tapo
           self.start_time = start_time
           self.end_time = end_time

       async def download(self):
           # Use tapo's KLAP transport to get media
           # Parse response and yield chunks
   ```

3. **Modify getMediaSession() to detect KLAP**
   ```python
   def getMediaSession(self, stream_type):
       if self.isKLAP:
           return KlapMediaSession(...)  # New
       else:
           return HttpMediaSession(...)  # Old
   ```

4. **Test with Kitchen camera**

### Phase 2B: Fallback to Approach B (HLS)

If Approach A doesn't work:
1. Complete DownloaderV2 implementation
2. Use HLS streaming instead
3. Trade off: Slower but might work

---

## Technical Deep Dive

### Understanding KLAP for Media

**KLAP Protocol Flow**:
```
1. Client sends handshake
2. KlapTransport establishes encrypted tunnel
3. Requests sent through tunnel (encrypted)
4. Responses received through tunnel (encrypted)
5. KlapTransport handles encryption/decryption
```

**For Media**:
- Needs to send: start_time, end_time, channel info
- Receives: Binary video data
- Encryption: AES (handled by KlapTransport)

### Current HttpMediaSession Flow

```python
# 1. Connect to port 8800
await asyncio.open_connection(self.ip, self.port)

# 2. Send HTTP Digest Auth
POST /stream HTTP/1.1
Authorization: Digest username="admin" ...

# 3. Receive video chunks
{multipart video data}
```

**Why it fails on KLAP**:
- KLAP cameras don't listen for HTTP Digest on port 8800
- Media endpoint might be different or require KLAP wrapper

---

## Key Files to Monitor/Modify

```
pytapo/__init__.py
  └─ getMediaSession()  # Detect KLAP here

pytapo/media_stream/
  ├─ session.py        # HttpMediaSession (legacy)
  ├─ klap_session.py   # KlapMediaSession (new - if needed)
  ├─ downloaderv2.py   # HLS approach (fallback)
  └─ downloader.py     # Current (won't work with KLAP)
```

---

## Testing Strategy

### Test 1: Approach A (KLAP-Wrapped)
```python
# Once KlapMediaSession is implemented
tapo = Tapo(..., device_password="10102013")
downloader = KlapMediaSession(tapo, start, end, time_corr)
async for chunk in downloader.download():
    # Should receive video data
```

### Test 2: Approach B (HLS)
```python
# Use DownloaderV2
downloader_v2 = DownloaderV2(tapo, start, end, time_corr)
# Should work with ffmpeg
```

### Test 3: Approach C (Different Endpoint)
```python
# Try alternative ports/endpoints
# Monitor for 200 response instead of 401
```

---

## Success Criteria

- [x] Identify KLAP as root cause
- [ ] Implement KLAP media download support
- [ ] Test successful file download
- [ ] Verify all 7 cameras work
- [ ] Deploy to production

---

## Resources

1. **pytapo GitHub**: https://github.com/JurajNyiri/pytapo
   - Issues tab: Search "KLAP media"
   - Discussions: Community solutions

2. **kasa library**: https://github.com/python-kasa/python-kasa
   - KlapTransport documentation
   - Protocol implementation details

3. **KLAP Protocol**: Reverse-engineered by community
   - Not officially documented by TP-Link
   - Best efforts based on observed behavior

---

## Next Action

**Immediate**: Research if KlapTransport can handle binary media streaming
- Check kasa library documentation
- Test if we can send media requests through it

**If successful**: Implement KlapMediaSession
**If unsuccessful**: Fall back to DownloaderV2 HLS approach

---

**Status**: Ready for Approach A implementation
