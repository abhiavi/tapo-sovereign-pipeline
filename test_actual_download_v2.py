#!/usr/bin/env python3
"""
Proper recording download test from Kitchen camera with unique output folder.
"""

import asyncio
import sys
import os
from datetime import datetime
from pytapo import Tapo
from pytapo.media_stream.session import KlapMediaSession, HttpMediaSession
from pytapo.media_stream._utils import StreamType
from pytapo.media_stream.downloader import Downloader

# Cloud credentials
CLOUD_USER = "khaparde.abhishek@gmail.com"
CLOUD_PASS = "Summer123!"

# Create unique output folder for this test
TEST_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
DOWNLOADS_FOLDER = os.path.expanduser(f"~/Downloads/tapo_test_{TEST_TIMESTAMP}")
os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)

print(f"Test output folder: {DOWNLOADS_FOLDER}\n")

def connect_and_prepare():
    """Connect to Kitchen camera and prepare download (synchronous)."""

    camera_name = "Kitchen"
    camera_ip = "192.168.29.169"

    print(f"{'='*70}")
    print(f"KITCHEN CAMERA DOWNLOAD TEST")
    print(f"{'='*70}\n")

    try:
        print(f"1. Connecting to {camera_name}...")
        tapo = Tapo(camera_ip, CLOUD_USER, CLOUD_PASS)
        print(f"   ✓ Connected")
        print(f"   Device Type: {tapo.deviceType}")
        print(f"   KLAP Enabled: {tapo.isKLAP}")

        print(f"\n2. Retrieving recordings...")
        today = datetime.now().strftime("%Y%m%d")
        recordings = tapo.getRecordings(today)

        if not recordings:
            print(f"   ⚠ No recordings found for today")
            return None

        print(f"   ✓ Found {len(recordings)} recording session(s)")
        first_rec = recordings[0]
        rec_key = list(first_rec.keys())[0]
        start_time = first_rec[rec_key]['startTime']
        end_time = first_rec[rec_key]['endTime']

        print(f"   Recording key: {rec_key}")
        print(f"   Start time: {start_time}")
        print(f"   End time: {end_time}")

        print(f"\n3. Getting media session...")
        media_session = tapo.getMediaSession(StreamType.Download)
        session_type = type(media_session).__name__
        print(f"   Session type: {session_type}")

        print(f"\n4. Getting time correction...")
        time_corr = tapo.getTimeCorrection()
        print(f"   Time correction: {time_corr}")

        print(f"\n5. Creating downloader...")
        print(f"   Output folder: {DOWNLOADS_FOLDER}")
        downloader = Downloader(
            tapo,
            start_time,
            end_time,
            time_corr,
            DOWNLOADS_FOLDER
        )
        print(f"   ✓ Downloader ready")

        return {
            'downloader': downloader,
            'camera_name': camera_name,
            'start_time': start_time,
            'end_time': end_time,
        }

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return None

async def download_async(prep_data):
    """Download the recording (asynchronous)."""

    print(f"\n6. Downloading recording...")
    print(f"   This may take a few minutes...")

    try:
        chunk_count = 0
        async for chunk in prep_data['downloader'].download():
            chunk_count += 1
            if chunk_count % 5 == 0:
                print(f"   ↓ Processed {chunk_count} chunks...")

        print(f"\n   ✓ Download completed!")
        print(f"   Total chunks: {chunk_count}")

        # Check for NEW files in output folder
        files = os.listdir(DOWNLOADS_FOLDER)
        print(f"\n7. Verifying files...")
        print(f"   Files in output folder: {len(files)}")

        for f in files:
            full_path = os.path.join(DOWNLOADS_FOLDER, f)
            size = os.path.getsize(full_path)
            mtime = datetime.fromtimestamp(os.path.getmtime(full_path))
            print(f"   - {f} ({size} bytes, modified: {mtime})")

        # Find video files
        video_files = [f for f in files if f.endswith(('.mp4', '.mkv', '.avi', '.mov'))]

        if video_files:
            print(f"\n{'='*70}")
            print(f"✅ DOWNLOAD SUCCESSFUL")
            print(f"{'='*70}")
            for vf in video_files:
                full_path = os.path.join(DOWNLOADS_FOLDER, vf)
                size = os.path.getsize(full_path)
                print(f"Video: {vf}")
                print(f"Size: {size / (1024*1024):.2f} MB")
                print(f"Path: {full_path}")
            print(f"{'='*70}\n")
            return True
        else:
            print(f"\n⚠ No video files found in output folder")
            print(f"Files created: {files}")
            return False

    except Exception as e:
        print(f"\n✗ Download error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test."""

    print(f"\n{'='*70}")
    print(f"KITCHEN CAMERA RECORDING DOWNLOAD - VERIFICATION TEST")
    print(f"{'='*70}\n")

    try:
        # Step 1: Connect and prepare
        prep_data = connect_and_prepare()
        if prep_data is None:
            print(f"\n✗ Failed to connect to camera")
            return 1

        # Step 2: Download
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(download_async(prep_data))
            return 0 if success else 1
        finally:
            loop.close()

    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
