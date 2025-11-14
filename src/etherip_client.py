import logging
import time
import struct
from pycomm3 import CIPDriver
from eds_parser import parse_eds

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class EtherIPClient:
    def __init__(self, eds_file: str):
        """
        Initialize EtherNet/IP client using EDS file for configuration.
        """
        parsed = parse_eds(eds_file)
        self.device_info = parsed["device_info"]
        self.offsets = parsed["offsets"]
        self.ip_address = self.device_info["IPAddress"]
        self.driver = None

        # Map conductivity channels to AI slots (based on documentation)
        self.channels = {
            "conductivity_ch1": "AI1",
            "conductivity_ch2": "AI5",
            "conductivity_ch3": "AI21",
            "conductivity_ch4": "AI25"
        }

    def connect(self):
        """
        Connect to EtherNet/IP device.
        """
        try:
            self.driver = CIPDriver(self.ip_address)
            logging.info(f"Connected to EtherNet/IP device at {self.ip_address}")
        except Exception as e:
            logging.error(f"Failed to connect: {e}")

    def read_raw_input(self):
        """
        Reads the entire Input Assembly as raw bytes.
        Replace 'Input' with actual assembly tag name from device.
        """
        if not self.driver:
            logging.error("Driver not connected.")
            return None
        try:
            result = self.driver.read_tag("Input")  # Placeholder tag name
            raw_bytes = result.value
            if isinstance(raw_bytes, (bytes, bytearray)):
                logging.debug(f"Raw input length: {len(raw_bytes)} bytes")
                return raw_bytes
            else:
                logging.error("Unexpected data type for raw input.")
                return None
        except Exception as e:
            logging.error(f"Error reading raw input: {e}")
            return None

    def decode_float(self, raw_bytes, start, end):
        """
        Decode 4 bytes (little-endian) into a float.
        """
        try:
            return struct.unpack('<f', raw_bytes[start:end+1])[0]
        except Exception as e:
            logging.error(f"Error decoding bytes {start}-{end}: {e}")
            return None

    def read_all_channels(self):
        """
        Read all conductivity channels from raw input using offsets.
        """
        raw_bytes = self.read_raw_input()
        if not raw_bytes:
            return {}

        readings = {}
        for name, ai_tag in self.channels.items():
            start, end = self.offsets.get(ai_tag, (None, None))
            if start is not None:
                value = self.decode_float(raw_bytes, start, end)
                readings[name] = value
            else:
                readings[name] = None
        return readings

    def health_check_loop(self, interval=5):
        """
        Continuous loop to read and log all channels.
        """
        while True:
            readings = self.read_all_channels()
            logging.info(f"Current readings: {readings}")
            time.sleep(interval)

if __name__ == "__main__":
    eds_file = "./eds_files/MT_M800_1P_EIP_V1.2_20200107.eds"
    client = EtherIPClient(eds_file)
    client.connect()
    client.health_check_loop()