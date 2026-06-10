#!/usr/bin/env python3
"""
Test recording download from ALL cameras - properly handling async/sync.
"""

import asyncio
import os
from datetime import datetime
from pytapo import Tapo
from pytapo.media_stream._utils import StreamType
from pytapo.media_stream.downloader import Downloader

CLOUD_USER = "admin"
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

def test_camera_connection(camera_info):
    """Test connection to a camera (SYNCHRONOUS)."""

    name = camera_info['name']
    ip = camera_info['ip']

    print(f"  {name:25}", end=" ", flush=True)

    try:
        tapo = Tapo(ip, CLOUD_USER, CLOUD_PASS, cloudPassword="10102013")

        # Try to get recordings
        today = datetime.now().strftime("%Y%m%d")
        recordings = tapo.getRecordings(today)

        if not recordings:
            print("✗ (no recordings)")
            return None

        # Prepare downloader
        first_rec = recordings[0]
        rec_key = list(first_rec.keys())[0]
        start_time = first_rec[rec_key]['startTime']
        end_time = first_rec[rec_key]['endTime']

        media_session = tapo.getMediaSession(StreamType.Download)
        time_corr = tapo.getTimeCorrection()

        output_dir = os.path.expanduser(f"~/Downloads/test_{name}_{datetime.now().strftime('%H%M%S')}")
        os.makedirs(output_dir, exist_ok=True)

        downloader = Downloader(tapo, start_time, end_time, time_corr, output_dir)

        print("✓", flush=True)

        return {
            'name': name,
            'ip': ip,
            'downloader': downloader,
            'output_dir': output_dir,
            'session_type': type(media_session).__name__,
        }

    except Exception as e:
        error = str(e)
        if '401' in error:
            print("✗ (HTTP 401)")
        elif 'connection' in error.lower() or 'timeout' in error.lower():
            print("✗ (connection error)")
        elif 'no recordings' in error.lower():
            print("✗ (no recordings)")
        else:
            print(f"✗ ({error[:20]})")
        return None

async def download_from_camera(prep):
    """Download from prepared camera (ASYNCHRONOUS)."""

    try:
        chunk_count = 0
        async for _ in prep['downloader'].download():
            chunk_count += 1

        # Check if file was created
        files = os.listdir(prep['output_dir'])
        video_files = [f for f in files if f.endswith(('.mp4', '.mkv', '.avi', '.mov'))]

        if video_files:
            file_path = os.path.join(prep['output_dir'], video_files[0])
            file_size = os.path.getsize(file_path)
            return {
                'status': 'success',
                'camera': prep['name'],
                'file': file_path,
                'size': file_size,
            }
        else:
            return {
                'status': 'no_file',
                'camera': prep['name'],
                'error': f'No file created (chunks: {chunk_count})',
            }

    except Exception as e:
        return {
            'status': 'download_error',
            'camera': prep['name'],
            'error': str(e)[:50],
        }

async def download_all_prepared(prepared_cameras):
    """Download from all prepared cameras in parallel."""

    if not prepared_cameras:
        return []

    tasks = [download_from_camera(prep) for prep in prepared_cameras]
    return await asyncio.gather(*tasks)

def main():
    print("\n" + "="*70)
    print("TESTING ALL 7 CAMERAS FOR RECORDING DOWNLOAD")
    print("="*70 + "\n")

    # STEP 1: Test all connections synchronously
    print("Phase 1: Testing connections...")
    prepared_cameras = []

    for camera in CAMERAS:
        result = test_camera_connection(camera)
        if result:
            prepared_cameras.append(result)

    print(f"\n✓ {len(prepared_cameras)}/{len(CAMERAS)} cameras ready for download\n")

    if not prepared_cameras:
        print("❌ No working cameras found")
        return 1

    # STEP 2: Download from all prepared cameras asynchronously
    print("Phase 2: Downloading recordings...")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(download_all_prepared(prepared_cameras))
    finally:
        loop.close()

    # STEP 3: Print results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70 + "\n")

    successful = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] != 'success']

    print(f"✓ Successful: {len(successful)}/{len(prepared_cameras)}\n")
    for r in successful:
        size_mb = r['size'] / (1024*1024)
        filename = os.path.basename(r['file'])
        print(f"  ✓ {r['camera']:25} {size_mb:7.2f} MB  {filename}")

    if failed:
        print(f"\n✗ Failed: {len(failed)}/{len(prepared_cameras)}\n")
        for r in failed:
            print(f"  ✗ {r['camera']:25} {r.get('error', 'Unknown error')}")

    print(f"\n{'='*70}\n")

    if successful:
        print(f"✅ WORKING CAMERAS: {', '.join([r['camera'] for r in successful])}")
        print(f"\nYour backup system can use: {successful[0]['camera']}")
        return 0
    else:
        print(f"❌ NO WORKING CAMERAS")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
