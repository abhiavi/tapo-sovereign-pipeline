import logging
from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader
import asyncio

logging.basicConfig(level=logging.DEBUG)

IP = "192.168.29.169" # Kitchen

# Cloud credentials
CLOUD_USER = "abhishek"
CLOUD_PASS = "20112020"

def main():
    print("Testing Kitchen camera with abhishek:20112020...")
    try:
        tapo = Tapo(IP, CLOUD_USER, CLOUD_PASS)
        print("✅ Cloud Auth Success")
        
        recordings = tapo.getRecordings("20260610")
        print(f"✅ Found recordings: {recordings}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
