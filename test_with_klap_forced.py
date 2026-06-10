#!/usr/bin/env python3
"""
Test with KLAP mode FORCED (since detection may not be working).
"""

import asyncio
from pytapo import Tapo
from pytapo.media_stream.session import KlapMediaSession
from pytapo.media_stream._utils import StreamType
from datetime import datetime

CLOUD_USER = "khaparde.abhishek@gmail.com"
CLOUD_PASS = "Summer123!"

def main():
    print("\n" + "="*70)
    print("KITCHEN CAMERA TEST - FORCING KLAP MODE")
    print("="*70 + "\n")

    print("1. Connecting with FORCED KLAP mode...")
    # Force isKLAP=True to use KlapMediaSession
    tapo = Tapo(
        "192.168.29.169",
        CLOUD_USER,
        CLOUD_PASS,
        isKLAP=True  # ← FORCE KLAP MODE
    )
    print(f"   ✓ Connected")
    print(f"   Device Type: {tapo.deviceType}")
    print(f"   isKLAP setting: {tapo.isKLAP}\n")

    print("2. Getting recordings...")
    recordings = tapo.getRecordings(datetime.now().strftime("%Y%m%d"))
    if not recordings:
        print("   ✗ No recordings!")
        return False

    print(f"   ✓ Found {len(recordings)} sessions\n")

    first_rec = recordings[0]
    rec_key = list(first_rec.keys())[0]
    start_time = first_rec[rec_key]['startTime']
    end_time = first_rec[rec_key]['endTime']

    print(f"3. Recording details:")
    print(f"   Start: {start_time}")
    print(f"   End: {end_time}\n")

    print("4. Getting media session...")
    media_session = tapo.getMediaSession(StreamType.Download)
    session_type = type(media_session).__name__
    print(f"   Session type: {session_type}")

    if isinstance(media_session, KlapMediaSession):
        print(f"   ✓ Using KlapMediaSession (KLAP mode)\n")
    else:
        print(f"   ✗ Not using KlapMediaSession - got {session_type}\n")
        return False

    print("5. Getting time correction...")
    time_corr = tapo.getTimeCorrection()
    print(f"   Time correction: {time_corr}\n")

    # Test async
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(test_klap_async(media_session, start_time, end_time))
        return 0 if result else 1
    finally:
        loop.close()

async def test_klap_async(media_session, start_time, end_time):
    """Test KlapMediaSession."""
    try:
        print("6. Starting KlapMediaSession...")
        await media_session.start()
        print("   ✓ Started successfully\n")

        request = {
            "type": "request",
            "method": "playback",
            "params": {
                "playback": {
                    "start_time": start_time,
                    "end_time": end_time,
                    "scale": "1/1",
                    "channels": [0, 1],
                }
            },
        }

        print("7. Requesting media through KLAP transport...")
        chunk_num = 0
        total_bytes = 0

        async for response in media_session.transceive(
            str(request),
            mimetype="application/json",
            encrypt=False,
        ):
            chunk_num += 1
            data_len = len(response.plaintext) if response.plaintext else 0
            total_bytes += data_len
            print(f"   Chunk {chunk_num}: {data_len} bytes")

            if chunk_num >= 5:
                print(f"   (stopping after 5 chunks)")
                break

        await media_session.close()

        print(f"\n8. Results:")
        print(f"   Total chunks: {chunk_num}")
        print(f"   Total bytes: {total_bytes}")

        if total_bytes > 0:
            print(f"\n   ✓ SUCCESS! KlapMediaSession is working")
            print(f"   Video data flowing through KLAP transport")
            return True
        else:
            print(f"\n   ⚠️  KlapMediaSession started but no data received")
            return False

    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
