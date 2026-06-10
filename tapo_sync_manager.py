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

async def download_camera(camera_name, camera_ip, target_date):
    """Downloads recordings and generates metadata indexing."""
    output_dir = os.path.join(LOCAL_STORAGE, camera_name, target_date)
    os.makedirs(output_dir, exist_ok=True)
    
    # Path for the local metadata index (will be synced to cloud)
    index_csv_path = os.path.join(output_dir, f"metadata_index_{camera_name}_{target_date}.csv")
    
    write_log(f"    - Connecting to {camera_name} ({camera_ip})...")
    tapo = Tapo(camera_ip, "admin", CLOUD_PASS, cloudPassword=CLOUD_PASS)

    recordings = await asyncio.get_event_loop().run_in_executor(None, tapo.getRecordings, target_date)
    if not recordings:
        write_log(f"    - ⚠️ No recordings found on {camera_name} for {target_date}.")
        return 0

    timeCorrection = await asyncio.get_event_loop().run_in_executor(None, tapo.getTimeCorrection)
    total_downloaded = 0
    write_log(f"    - Found {len(recordings)} recording blocks. Starting download sequence...")
    
    for recording in recordings:
        for key in recording:
            start_ts = recording[key]["startTime"]
            end_ts = recording[key]["endTime"]
            
            # Convert Unix timestamps to human-readable format
            start_dt = datetime.fromtimestamp(start_ts)
            end_dt = datetime.fromtimestamp(end_ts)
            
            start_str = start_dt.strftime("%H%M%S")
            end_str = end_dt.strftime("%H%M%S")
            
            # Formatted string: e.g., Ground_Backyard_2026-06-10_143000-144500.mp4
            fileName = f"{camera_name}_{start_dt.strftime('%Y-%m-%d')}_{start_str}-{end_str}.mp4"
            final_path = os.path.join(output_dir, fileName)
            
            # Skip if file already exists
            if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
                continue

            downloader = Downloader(
                tapo, start_ts, end_ts, timeCorrection,
                output_dir, None, False, 50, fileName=fileName
            )
            
            async for status in downloader.download():
                pass # Silently download
            
            if os.path.exists(final_path):
                total_downloaded += 1
                size_mb = os.path.getsize(final_path) / (1024 * 1024)
                
                # Write to metadata index
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
    """Copies downloaded files and metadata to Google Drive."""
    src = os.path.join(LOCAL_STORAGE, camera_name, target_date)
    dest = os.path.join(CLOUD_STORAGE, camera_name, target_date)
    
    if not os.path.exists(src):
        return False
        
    os.makedirs(dest, exist_ok=True)
    write_log(f"    - Syncing {camera_name} video + metadata to Google Drive...")
    
    try:
        subprocess.run(["rsync", "-a", f"{src}/", dest], check=True)
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
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    success_count = 0
    
    for cam in CAMERAS:
        write_log(f"### Camera: {cam['name']}")
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                files_downloaded = loop.run_until_complete(
                    download_camera(cam['name'], cam['ip'], target_date)
                )
                write_log(f"    - ✅ Extracted {files_downloaded} video blocks + generated metadata index.")
                
                if sync_to_cloud(cam['name'], target_date):
                    write_log(f"    - ☁️  Cloud Sync successful.")
                    success_count += 1
                break
                
            except Exception as e:
                write_log(f"    - ❌ Error on attempt {attempt}/{MAX_RETRIES}: {str(e)}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
    
    loop.close()
    write_log(f"\n**Summary:** {success_count}/{len(CAMERAS)} cameras fully synchronized to Google Drive.")
    cleanup_old_files()

if __name__ == "__main__":
    main()
