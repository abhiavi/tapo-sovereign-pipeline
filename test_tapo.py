import asyncio
import logging
from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader

logging.basicConfig(level=logging.DEBUG)

# Camera IP
IP = "192.168.29.169" # Kitchen

# Cloud credentials
CLOUD_USER = "ramesh"
CLOUD_PASS = "10102013"

# Device credentials to test
DEVICE_USER = "abhishek"
DEVICE_PASS = "20112020"

async def main():
    print("Testing Kitchen camera...")
    print(f"Cloud: {CLOUD_USER}:{CLOUD_PASS}, Device: {DEVICE_USER}:{DEVICE_PASS}")
    try:
        tapo = Tapo(IP, CLOUD_USER, CLOUD_PASS, device_username=DEVICE_USER, device_password=DEVICE_PASS)
        print("✅ Cloud Auth Success")
        
        recordings = tapo.getRecordings("20260610")
        print(f"✅ Found recordings: {recordings}")
        
        if recordings:
            for key in recordings[0]:
                start_time = recordings[0][key]['startTime']
                end_time = recordings[0][key]['endTime']
                break
                
            print(f"Attempting to download segment: {start_time} - {end_time}")
            time_correction = tapo.getTimeCorrection()
            
            downloader = Downloader(tapo, start_time, end_time, time_correction, ".")
            
            async for _ in downloader.download():
                pass
            print("✅ Download successful!")
        else:
            print("No recordings today")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
