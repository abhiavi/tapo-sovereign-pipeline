import asyncio
import logging
from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader

logging.basicConfig(level=logging.DEBUG)

IP = "192.168.29.198" # Bedroom

# Cloud credentials
CLOUD_USER = "khaaprde.abhishek@gmail.com"
CLOUD_PASS = "Summer123!"

def main():
    print("Testing Bedroom camera with correct credentials...")
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
            
            # Patch the device credentials for downloading
            tapo.cloudPassword = "10102013" # The new local device password
            
            # Monkey patch HttpMediaSession
            import pytapo.media_stream.session
            original_init = pytapo.media_stream.session.HttpMediaSession.__init__
            
            def new_init(self, ip, cloud_password, super_secret_key, encryptionMethod, **kwargs):
                # Force username to be ramesh
                kwargs['username'] = 'ramesh'
                original_init(self, ip, cloud_password, super_secret_key, encryptionMethod, **kwargs)
                
            pytapo.media_stream.session.HttpMediaSession.__init__ = new_init
            
            downloader = Downloader(tapo, start_time, end_time, time_correction, ".")
            
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
