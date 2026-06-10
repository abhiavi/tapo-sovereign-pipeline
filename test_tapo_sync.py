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

def main():
    print("Testing Kitchen camera...")
    try:
        tapo = Tapo(IP, CLOUD_USER, CLOUD_PASS)
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
            
            # Now patch the password that will be used for download
            tapo.cloudPassword = "10102013"
            tapo.password = "10102013"
            
            downloader = Downloader(tapo, start_time, end_time, time_correction, ".")
            
            # Run downloader
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def download():
                    async for _ in downloader.download():
                        pass
                loop.run_until_complete(download())
            finally:
                loop.close()
            
            print("✅ Download successful!")
        else:
            print("No recordings today")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
