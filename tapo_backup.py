#!/usr/bin/env python3
"""
Tapo Camera Backup System for adraca-pve
Uses pytapo library to download recordings from Tapo cameras
Syncs to /mnt/warehouse/tapo_backups on adraca-minipc
"""

import asyncio
import os
import datetime
import subprocess
import sys
import json
import logging

# Setup logging
log_file = "/var/log/tapo_camera_backup.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Camera configuration
CAMERAS = [
    {'name': 'Bedroom', 'ip': '192.168.29.198', 'user': 'abhishek', 'pass': '20112020'},
    {'name': 'Ground_Backyard', 'ip': '192.168.29.167', 'user': 'abhishek', 'pass': '20112020'},
    {'name': 'Hall', 'ip': '192.168.29.249', 'user': 'abhishek', 'pass': '20112020'},
    {'name': 'Office', 'ip': '192.168.29.14', 'user': 'anuragkhaparde', 'pass': 'khapardehouse'},
    {'name': 'Outsidefront_Ground', 'ip': '192.168.29.101', 'user': 'abhishek', 'pass': '20112020'},
    {'name': 'Outside_Front_Top', 'ip': '192.168.29.13', 'user': 'abhishek', 'pass': '20112020'},
    {'name': 'Kitchen', 'ip': '192.168.29.169', 'user': 'abhishek', 'pass': '20112020'}
]

# Storage configuration
LOCAL_BACKUP = "/mnt/pve-storage/tapo_backups"
REMOTE_BACKUP = "abhishek@100.105.27.116:/mnt/warehouse/tapo_backups"  # adraca-minipc warehouse
RETENTION_DAYS = 6
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d")


def verify_pytapo():
    """Verify pytapo is available"""
    try:
        from pytapo import Tapo
        logger.info("✅ pytapo library available")
        return True
    except ImportError:
        logger.error("❌ pytapo not found. Install with: pip install pytapo")
        return False


def test_camera_connectivity():
    """Test connectivity to all cameras"""
    logger.info("=" * 60)
    logger.info("Testing camera connectivity...")
    logger.info("=" * 60)

    try:
        from pytapo import Tapo
    except ImportError:
        logger.error("pytapo library not available")
        return False

    results = {"success": 0, "failed": 0}

    for camera in CAMERAS:
        try:
            logger.info(f"Testing {camera['name']} ({camera['ip']})...", )
            tapo = Tapo(camera['ip'], camera['user'], camera['pass'])
            info = tapo.getBasicInfo()
            logger.info(f"  ✅ {camera['name']}: Connected - {info.get('model', 'Unknown model')}")
            results["success"] += 1
        except Exception as e:
            logger.error(f"  ❌ {camera['name']}: {str(e)}")
            results["failed"] += 1

    logger.info("=" * 60)
    logger.info(f"Results: {results['success']} success, {results['failed']} failed")
    logger.info("=" * 60)

    return results["failed"] == 0


def backup_camera_async(camera, date_str):
    """
    Async backup for a single camera using pytapo
    """
    try:
        from pytapo import Tapo
        from pytapo.media_stream.downloader import Downloader
    except ImportError:
        logger.error("pytapo library not available")
        return False

    camera_name = camera['name']
    camera_ip = camera['ip']

    try:
        logger.info(f"Starting backup for {camera_name} ({camera_ip})...")

        # Connect to camera
        tapo = Tapo(camera_ip, camera['user'], camera['pass'])

        # Get recordings for the specified date
        recordings = tapo.getRecordings(date_str)
        if not recordings:
            logger.info(f"  ℹ️  {camera_name}: No recordings found for {date_str}")
            return True

        logger.info(f"  📹 {camera_name}: Found {len(recordings)} recording segments")

        # Get time correction for proper timing
        time_correction = tapo.getTimeCorrection()

        # Create backup directory
        cam_dir = os.path.join(LOCAL_BACKUP, camera_name, date_str)
        os.makedirs(cam_dir, exist_ok=True)

        # Download recordings
        downloaded = 0
        for recording in recordings:
            for key in recording:
                start_time = recording[key]['startTime']
                end_time = recording[key]['endTime']
                filename = f"{start_time}_{end_time}.mp4"
                filepath = os.path.join(cam_dir, filename)

                if os.path.exists(filepath):
                    logger.debug(f"    ⏭️  Skipping existing: {filename}")
                    continue

                try:
                    logger.info(f"    ⬇️  Downloading: {filename}")
                    downloader = Downloader(tapo, start_time, end_time, time_correction, cam_dir)

                    # Run async downloader
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        async def download():
                            async for _ in downloader.download():
                                pass
                        loop.run_until_complete(download())
                    finally:
                        loop.close()

                    downloaded += 1
                    file_size = os.path.getsize(filepath) / (1024*1024)
                    logger.info(f"      ✅ {filename} ({file_size:.1f} MB)")
                except Exception as e:
                    logger.error(f"      ❌ Failed to download {filename}: {str(e)}")
                    continue

        if downloaded > 0:
            logger.info(f"✅ {camera_name}: Downloaded {downloaded} files")
            return True
        else:
            logger.info(f"ℹ️  {camera_name}: No new files to download")
            return True

    except Exception as e:
        logger.error(f"❌ {camera_name}: {str(e)}")
        return False


def backup_all_cameras():
    """Backup all cameras for today and yesterday"""
    logger.info("=" * 60)
    logger.info("🎬 Starting Tapo Camera Backup Cycle")
    logger.info("=" * 60)

    dates_to_backup = [
        (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d"),  # Yesterday
        datetime.datetime.now().strftime("%Y%m%d")  # Today
    ]

    successful = 0
    failed = 0

    for date_str in dates_to_backup:
        logger.info(f"\n📅 Backing up recordings for {date_str}...")
        for camera in CAMERAS:
            if backup_camera_async(camera, date_str):
                successful += 1
            else:
                failed += 1

    logger.info("\n" + "=" * 60)
    logger.info(f"✅ Backup cycle complete: {successful} successful, {failed} failed")
    logger.info("=" * 60)

    return failed == 0


def sync_to_warehouse():
    """Sync backups to adraca-minipc warehouse"""
    logger.info("\n" + "=" * 60)
    logger.info("🔄 Syncing to warehouse...")
    logger.info("=" * 60)

    try:
        # Using rsync for efficient sync
        cmd = [
            'rsync',
            '-avz',
            '--delete',
            f"{LOCAL_BACKUP}/",
            REMOTE_BACKUP
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=3600, text=True)

        if result.returncode == 0:
            logger.info("✅ Warehouse sync successful")
            return True
        else:
            logger.error(f"❌ Sync failed: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"❌ Sync error: {str(e)}")
        return False


def cleanup_old_backups():
    """Delete backups older than RETENTION_DAYS"""
    logger.info("\n" + "=" * 60)
    logger.info(f"🗑️  Running cleanup (keeping {RETENTION_DAYS} days)...")
    logger.info("=" * 60)

    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=RETENTION_DAYS)

    for camera in CAMERAS:
        cam_dir = os.path.join(LOCAL_BACKUP, camera['name'])
        if not os.path.exists(cam_dir):
            continue

        for date_folder in os.listdir(cam_dir):
            date_path = os.path.join(cam_dir, date_folder)
            if not os.path.isdir(date_path):
                continue

            try:
                folder_date = datetime.datetime.strptime(date_folder, "%Y%m%d")
                if folder_date < cutoff_date:
                    import shutil
                    shutil.rmtree(date_path)
                    logger.info(f"  🗑️  Deleted: {camera['name']}/{date_folder}")
            except ValueError:
                pass


def main():
    """Main execution"""
    logger.info("\n🚀 Tapo Camera Backup System Started")
    logger.info(f"Timestamp: {datetime.datetime.now()}")

    # Verify prerequisites
    if not verify_pytapo():
        logger.error("Cannot proceed without pytapo")
        return False

    # Test connectivity
    if not test_camera_connectivity():
        logger.warning("Some cameras are unreachable - continuing anyway")

    # Perform backups
    if not backup_all_cameras():
        logger.warning("Some backups failed")

    # Sync to warehouse
    if not sync_to_warehouse():
        logger.warning("Warehouse sync failed")

    # Cleanup old backups
    cleanup_old_backups()

    logger.info("\n" + "=" * 60)
    logger.info("✅ Backup cycle completed")
    logger.info("=" * 60)

    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        sys.exit(1)
