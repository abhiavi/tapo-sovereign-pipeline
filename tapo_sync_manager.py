#!/usr/bin/env python3
import os
import sys
import time
import shutil
import asyncio
import csv
from datetime import datetime, timedelta
import subprocess
import traceback
from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader

# --- Configuration ---
LOCAL_STORAGE = "/mnt/warehouse/tapo_buffer"
CLOUD_STORAGE = "/home/abhishek/gdrive-personal/Adraca_Surveillance"
OBSIDIAN_LOG = "/home/abhishek/ObsidianVault/03_Active_Projects/Tapo_Camera/Daily_Sync_Logs.md"
RETENTION_DAYS = 7
MAX_RETRIES = 3
RETRY_DELAY = 300  # 5 minutes

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

def write_log(message):
    print(message)
    with open(OBSIDIAN_LOG, "a") as f:
        f.write(message + "\n")

def append_to_index(index_path, metadata):
    """Appends metadata row to a CSV index file."""
    file_exists = os.path.isfile(index_path)
    with open(index_path, mode='a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=metadata.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(metadata)

def download_camera(camera_name, camera_ip, target_date):
    """Downloads recordings and generates metadata indexing."""
    output_dir = os.path.join(LOCAL_STORAGE, camera_name, target_date)
    os.makedirs(output_dir, exist_ok=True)
    
    index_csv_path = os.path.join(output_dir, f"metadata_index_{camera_name}_{target_date}.csv")
    
    write_log(f"    - Connecting to {camera_name} ({camera_ip})...")
    tapo = Tapo(camera_ip, "admin", CLOUD_PASS, cloudPassword=CLOUD_PASS)

    # These are native synchronous calls in pytapo
    recordings = tapo.getRecordings(target_date)
    if not recordings:
        write_log(f"    - ⚠️ No recordings found on {camera_name} for {target_date}.")
        return 0

    timeCorrection = tapo.getTimeCorrection()
    total_downloaded = 0
    write_log(f"    - Found {len(recordings)} recording blocks. Starting download sequence...")
    
    for recording in recordings:
        for key in recording:
            start_ts = recording[key]["startTime"]
            end_ts = recording[key]["endTime"]
            
            start_dt = datetime.fromtimestamp(start_ts)
            end_dt = datetime.fromtimestamp(end_ts)
            
            start_str = start_dt.strftime("%H%M%S")
            end_str = end_dt.strftime("%H%M%S")
            
            fileName = f"{camera_name}_{start_dt.strftime('%Y-%m-%d')}_{start_str}-{end_str}.mp4"
            final_path = os.path.join(output_dir, fileName)
            
            if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
                continue

            # Pytapo concatenates output_dir + fileName without os.path.join
            downloader = Downloader(
                tapo, start_ts, end_ts, timeCorrection,
                output_dir + "/", None, False, None, fileName=fileName
            )
            
            # Run the downloader's async generator inside a fresh event loop
            async def run_downloader():
                async for status in downloader.download():
                    pass
            
            asyncio.run(run_downloader())
            
            if os.path.exists(final_path):
                total_downloaded += 1
                size_mb = os.path.getsize(final_path) / (1024 * 1024)
                
                metadata = {
                    "Camera_Name": camera_name,
                    "Date": target_date,
                    "Start_Time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "End_Time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "Duration_Seconds": end_ts - start_ts,
                    "File_Size_MB": round(size_mb, 2),
                    "File_Name": fileName
                }
                append_to_index(index_csv_path, metadata)

    return total_downloaded

def sync_to_cloud(camera_name, target_date):
    """Copies downloaded files and metadata to Google Drive via rclone sync."""
    src = os.path.join(LOCAL_STORAGE, camera_name, target_date)
    # Using the remote name from rclone.conf directly
    remote_dest = f"Personal_Avi:Adraca_Surveillance/{camera_name}/{target_date}"
    
    if not os.path.exists(src):
        return False
        
    write_log(f"    - Syncing {camera_name} video + metadata to Google Drive...")
    
    try:
        # Run native rclone sync inside the container
        subprocess.run(["rclone", "sync", src, remote_dest, "--create-empty-src-dirs"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        write_log(f"    - ❌ Cloud sync failed: {e}")
        return False

def cleanup_old_files():
    """Deletes local folders older than RETENTION_DAYS."""
    write_log("\n### 🧹 Running 7-Day Local Retention Cleanup")
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    
    for cam_dir in os.listdir(LOCAL_STORAGE):
        cam_path = os.path.join(LOCAL_STORAGE, cam_dir)
        if not os.path.isdir(cam_path): continue
        
        for date_dir in os.listdir(cam_path):
            date_path = os.path.join(cam_path, date_dir)
            try:
                folder_date = datetime.strptime(date_dir, "%Y%m%d")
                if folder_date < cutoff:
                    shutil.rmtree(date_path)
                    write_log(f"- Deleted expired local backup: {cam_dir}/{date_dir}")
            except ValueError:
                pass

def main():
    target_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    os.makedirs(os.path.dirname(OBSIDIAN_LOG), exist_ok=True)
    write_log(f"\n## Tapo Synchronization Report: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    write_log(f"**Target Date Extracted:** {target_date}\n")
    
    success_count = 0
    
    for cam in CAMERAS:
        write_log(f"### Camera: {cam['name']}")
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                files_downloaded = download_camera(cam['name'], cam['ip'], target_date)
                write_log(f"    - ✅ Extracted {files_downloaded} video blocks + generated metadata index.")
                
                if sync_to_cloud(cam['name'], target_date):
                    write_log(f"    - ☁️  Cloud Sync successful.")
                    success_count += 1
                break
                
            except Exception as e:
                write_log(f"    - ❌ Error on attempt {attempt}/{MAX_RETRIES}: {str(e)}")
                traceback.print_exc()
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
    
    write_log(f"\n**Summary:** {success_count}/{len(CAMERAS)} cameras fully synchronized to Google Drive.")
    cleanup_old_files()

if __name__ == "__main__":
    main()
