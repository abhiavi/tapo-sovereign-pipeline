import logging
from pytapo import Tapo

logging.basicConfig(level=logging.ERROR)

CAMERAS = [
    {'name': 'Bedroom', 'ip': '192.168.29.198'},
    {'name': 'Ground_Backyard', 'ip': '192.168.29.167'},
    {'name': 'Hall', 'ip': '192.168.29.249'},
    {'name': 'Office', 'ip': '192.168.29.14'},
    {'name': 'Outsidefront_Ground', 'ip': '192.168.29.101'},
    {'name': 'Outside_Front_Top', 'ip': '192.168.29.13'},
    {'name': 'Kitchen', 'ip': '192.168.29.169'}
]

def main():
    print("Testing all cameras with ramesh:10102013...")
    for cam in CAMERAS:
        try:
            print(f"Testing {cam['name']} at {cam['ip']}...")
            tapo = Tapo(cam['ip'], "ramesh", "10102013")
            info = tapo.getBasicInfo()
            print(f"✅ SUCCESS on {cam['name']}")
        except Exception as e:
            print(f"❌ Error on {cam['name']}: {e}")

if __name__ == "__main__":
    main()
