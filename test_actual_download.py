#!/usr/bin/env python3
"""
Test actual recording download from Tapo camera to Downloads folder.
Uses the KLAP implementation with fallback to HTTP if needed.
"""

import asyncio
import sys
import os
from datetime import datetime
from pytapo import Tapo
from pytapo.media_stream.session import KlapMediaSession, HttpMediaSession
from pytapo.media_stream._utils import StreamType
from pytapo.media_stream.downloader import Downloader

# Camera configuration - IPs with cloud credentials
CLOUD_USER = "khaparde.abhishek@gmail.com"
CLOUD_PASS = "Summer123!"

CAMERAS = [
    {'name': 'Bedroom', 'ip': '192.168.29.198'},
    {'name': 'Ground_Backyard', 'ip': '192.168.29.167'},
    {'name': 'Hall', 'ip': '192.168.29.249'},
    {'name': 'Office', 'ip': '192.168.29.14'},
    {'name': 'Outsidefront_Ground', 'ip': '192.168.29.101'},
    {'name': 'Outside_Front_Top', 'ip': '192.168.29.13'},
    {'name': 'Kitchen', 'ip': '192.168.29.169'}
]

# Downloads folder
DOWNLOADS_FOLDER = os.path.expanduser("~/Downloads")
os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)

def connect_and_prepare(camera_info):
    """Connect to camera and prepare download info (synchronous)."""

    camera_name = camera_info['name']
    camera_ip = camera_info['ip']

    print(f"\n{'='*70}")
    print(f"DOWNLOADING FROM: {camera_name} ({camera_ip})")
    print(f"{'='*70}")

    try:
        # Connect to camera
        print(f"1. Connecting to {camera_name}...")
        tapo = Tapo(camera_ip, CLOUD_USER, CLOUD_PASS)
        print(f"   ✓ Connected")
        print(f"   Device Type: {tapo.deviceType}")
        print(f"   KLAP Enabled: {tapo.isKLAP}")

        # Get recordings
        print(f"\n2. Retrieving recordings...")
        today = datetime.now().strftime("%Y%m%d")
        recordings = tapo.getRecordings(today)

        if not recordings:
            print(f"   ⚠ No recordings found for today ({today})")
            return None

        print(f"   ✓ Found {len(recordings)} recording session(s)")

        # Get first recording details
        first_rec = recordings[0]
        rec_key = list(first_rec.keys())[0]
        start_time = first_rec[rec_key]['startTime']
        end_time = first_rec[rec_key]['endTime']
        print(f"   Recording: {rec_key}")
        print(f"   Time: {start_time} - {end_time}")

        # Get media session
        print(f"\n3. Getting media session...")
        media_session = tapo.getMediaSession(StreamType.Download)
        session_type = type(media_session).__name__
        print(f"   ✓ Session type: {session_type}")

        if isinstance(media_session, KlapMediaSession):
            print(f"   ℹ Using KLAP media session (firmware 1.5.4+)")
        elif isinstance(media_session, HttpMediaSession):
            print(f"   ℹ Using HTTP media session (legacy firmware)")

        # Get time correction
        print(f"\n4. Getting time correction...")
        time_corr = tapo.getTimeCorrection()
        print(f"   ✓ Time correction: {time_corr}")

        # Create downloader
        print(f"\n5. Creating downloader...")
        downloader = Downloader(
            tapo,
            start_time,
            end_time,
            time_corr,
            DOWNLOADS_FOLDER
        )
        print(f"   ✓ Downloader created")
        print(f"   Output directory: {DOWNLOADS_FOLDER}")

        return {
            'tapo': tapo,
            'downloader': downloader,
            'camera_name': camera_name,
            'start_time': start_time,
            'end_time': end_time,
        }

    except Exception as e:
        print(f"\n✗ Connection error: {e}")
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
            if chunk_count % 10 == 0:
                print(f"   ↓ Processed {chunk_count} chunks...")

        print(f"\n   ✓ Download completed!")
        print(f"   Total chunks processed: {chunk_count}")

        # Check for output file
        files = os.listdir(DOWNLOADS_FOLDER)
        video_files = [f for f in files if f.endswith(('.mp4', '.mkv', '.avi', '.mov'))]

        if video_files:
            # Get the most recently modified video file
            latest_video = max(
                [os.path.join(DOWNLOADS_FOLDER, f) for f in video_files],
                key=os.path.getctime
            )
            file_name = os.path.basename(latest_video)
            file_size = os.path.getsize(latest_video)
            print(f"\n{'='*70}")
            print(f"✅ SUCCESS! RECORDING DOWNLOADED")
            print(f"{'='*70}")
            print(f"Camera: {prep_data['camera_name']}")
            print(f"File: {file_name}")
            print(f"Size: {file_size / (1024*1024):.2f} MB")
            print(f"Location: {latest_video}")
            print(f"{'='*70}\n")
            return True
        else:
            print(f"\n⚠ Download completed but no video file found")
            print(f"   Files in directory: {files}")
            return False

    except Exception as e:
        print(f"\n✗ Download error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Test download from first available camera."""

    print("\n" + "="*70)
    print("TAPO CAMERA RECORDING DOWNLOAD TEST")
    print("="*70)

    print(f"\nAvailable cameras:")
    for i, cam in enumerate(CAMERAS, 1):
        print(f"  {i}. {cam['name']:25} ({cam['ip']})")

    # Test with Kitchen camera (the one we know best)
    test_camera = CAMERAS[6]  # Kitchen
    print(f"\nAttempting to download from: {test_camera['name']}")

    try:
        # STEP 1: Synchronous - Connect and prepare
        prep_data = connect_and_prepare(test_camera)
        if prep_data is None:
            return 1

        # STEP 2: Asynchronous - Download
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
