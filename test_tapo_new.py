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

async def main():
    print("Testing Kitchen camera...")
    try:
        # Don't use device_username since it's not patched properly
        tapo = Tapo(IP, CLOUD_USER, CLOUD_PASS)
        print("✅ Cloud Auth Success")
        
        # Manually patch the media session password directly for testing
        # Default username is 'admin', which is hardcoded in unpatched pytapo
        
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
            tapo.cloudPassword = "10102013" # The new local device password you set
            tapo.password = "10102013"
            
            downloader = Downloader(tapo, start_time, end_time, time_correction, ".")
            
            # Re-patch the Downloader's session if needed
            # Downloader uses tapo.cloudPassword internally
            
            async for _ in downloader.download():
                pass
            print("✅ Download successful!")
        else:
            print("No recordings today")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
