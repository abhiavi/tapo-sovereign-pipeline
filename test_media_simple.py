#!/usr/bin/env python3
"""
Simple test: Check if HttpMediaSession actually returns video data.
"""

import asyncio
from pytapo import Tapo
from pytapo.media_stream._utils import StreamType
from datetime import datetime

CLOUD_USER = "khaparde.abhishek@gmail.com"
CLOUD_PASS = "Summer123!"

def main():
    print("\n1. Connecting to Kitchen camera...")
    tapo = Tapo("192.168.29.169", CLOUD_USER, CLOUD_PASS)
    print("   ✓ Connected\n")

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
    print(f"   Key: {rec_key}")
    print(f"   Start: {start_time}")
    print(f"   End: {end_time}")
    print(f"   Duration: {end_time - start_time} seconds\n")

    print("4. Getting media session...")
    media_session = tapo.getMediaSession(StreamType.Download)
    print(f"   Session type: {type(media_session).__name__}\n")

    print("5. Getting time correction...")
    time_corr = tapo.getTimeCorrection()
    print(f"   Time correction: {time_corr}\n")

    # Run async test
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(test_media_async(media_session, start_time, end_time))
        return 0 if result else 1
    finally:
        loop.close()

async def test_media_async(media_session, start_time, end_time):
    """Test media session async operations."""
    try:
        print("6. Starting media session...")
        await media_session.start()
        print("   ✓ Started\n")

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

        print("7. Requesting media data...")
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

        print(f"\n8. Results:")
        print(f"   Chunks received: {chunk_num}")
        print(f"   Total bytes: {total_bytes}")

        if total_bytes == 0:
            print(f"\n   ⚠️  PROBLEM: No video data received!")
            print(f"   The media session is returning but NOT sending actual video data")
            return False
        else:
            print(f"\n   ✓ Video data is flowing correctly")
            return True

    except Exception as e:
        print(f"   ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
