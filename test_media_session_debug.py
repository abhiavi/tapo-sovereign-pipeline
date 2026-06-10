#!/usr/bin/env python3
"""
Debug what HttpMediaSession is actually returning.
"""

import asyncio
import sys
import os
from datetime import datetime
from pytapo import Tapo
from pytapo.media_stream._utils import StreamType

# Cloud credentials
CLOUD_USER = "khaparde.abhishek@gmail.com"
CLOUD_PASS = "Summer123!"

def debug_media_session():
    """Debug the media session."""

    camera_name = "Kitchen"
    camera_ip = "192.168.29.169"

    print(f"\n{'='*70}")
    print(f"DEBUGGING KITCHEN CAMERA MEDIA SESSION")
    print(f"{'='*70}\n")

    try:
        print(f"Connecting to {camera_name}...")
        tapo = Tapo(camera_ip, CLOUD_USER, CLOUD_PASS)
        print(f"✓ Connected\n")

        print(f"Getting recordings...")
        today = datetime.now().strftime("%Y%m%d")
        recordings = tapo.getRecordings(today)

        if not recordings:
            print(f"No recordings found!")
            return False

        print(f"✓ Found {len(recordings)} session(s)\n")

        first_rec = recordings[0]
        rec_key = list(first_rec.keys())[0]
        start_time = first_rec[rec_key]['startTime']
        end_time = first_rec[rec_key]['endTime']

        print(f"Recording details:")
        print(f"  Key: {rec_key}")
        print(f"  Start: {start_time}")
        print(f"  End: {end_time}")
        print(f"  Duration: {end_time - start_time} seconds\n")

        print(f"Creating media session...")
        media_session = tapo.getMediaSession(StreamType.Download)
        print(f"✓ Session type: {type(media_session).__name__}\n")

        print(f"Getting time correction...")
        time_corr = tapo.getTimeCorrection()
        print(f"✓ Time correction: {time_corr}\n")

        # Now test the media session
        return debug_async(media_session, start_time, end_time, time_corr)

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def debug_async(media_session, start_time, end_time, time_corr):
    """Debug the async media operations."""

    try:
        print(f"Starting media session...")
        await media_session.start()
        print(f"✓ Session started\n")

        print(f"Building media request...")
        # Build request similar to what Downloader uses
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

        print(f"Request: {request}\n")

        print(f"Sending transceive request...")
        chunk_count = 0
        total_bytes = 0

        async for response in media_session.transceive(
            str(request),
            mimetype="application/json",
            encrypt=False,
        ):
            chunk_count += 1
            data_len = len(response.plaintext) if response.plaintext else 0
            total_bytes += data_len

            print(f"Chunk {chunk_count}:")
            print(f"  - Session ID: {response.session}")
            print(f"  - Sequence: {response.seq}")
            print(f"  - MIME type: {response.mimetype}")
            print(f"  - Encrypted: {response.encrypted}")
            print(f"  - Data size: {data_len} bytes")
            print(f"  - Has JSON: {response.json_data is not None}")

            if response.json_data:
                print(f"  - JSON data keys: {list(response.json_data.keys())}")

            # Check if this looks like actual video data
            if data_len > 0:
                # Check magic bytes for common formats
                if response.plaintext:
                    magic = response.plaintext[:8]
                    print(f"  - Magic bytes: {magic.hex()}")

            if chunk_count >= 3:
                print(f"\n(Stopping after 3 chunks for debug)\n")
                break

        print(f"\nSummary:")
        print(f"  Total chunks received: {chunk_count}")
        print(f"  Total bytes received: {total_bytes}")

        if total_bytes == 0:
            print(f"\n⚠️ WARNING: No actual data received!")
            print(f"This suggests the media endpoint returned metadata but no video data")
        else:
            print(f"\n✓ Data is being received correctly")

        await media_session.close()
        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success = loop.run_until_complete(asyncio.get_event_loop().create_task(
            asyncio.create_task(debug_media_session()) if asyncio.iscoroutine(debug_media_session()) else asyncio.sleep(0)
        )) if asyncio.iscoroutine(debug_media_session()) else debug_media_session()
        return 0 if success else 1
    finally:
        loop.close()

if __name__ == "__main__":
    sys.exit(main())
