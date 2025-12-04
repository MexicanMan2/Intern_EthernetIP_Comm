import logging
import time
import struct
from pycomm3 import CIPDriver
from eds_parser import parse_eds

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class EtherIPClient:
    def __init__(self, ip_address: str, eds_file: str):
        """
        Initialize EtherNet/IP client.
        """
        parsed = parse_eds(eds_file)
        self.device_info = parsed["device_info"]
        self.offsets = parsed["offsets"]
        self.ip_address = ip_address
        self.driver = None

        # Map conductivity channels to AI slots (based on documentation)
        self.channels = {
            "conductivity_ch1": "AI1",
            "temperature_ch1": "AI2",
            "conductivity_ch2": "AI5",
            "temperature_ch2": "AI6",
            "conductivity_ch3": "AI17",
            "temperature_ch3": "AI18",
            "conductivity_ch4": "AI21",
            "temperature_ch4": "AI22"
        }

    def connect(self):
        """
        Connect to EtherNet/IP device.
        """
        try:
            self.driver = CIPDriver(self.ip_address)
            if self.driver.open():
                logging.info(f"Successfully connected to EtherNet/IP device at {self.ip_address}")
            else:
                logging.error(f"Failed to connect to {self.ip_address}. Please check IP and network connectivity.")
        except Exception as e:
            logging.error(f"An exception occurred while trying to connect: {e}")
            self.driver = None

    def read_raw_input(self):
        """
        Reads the entire Input Assembly (Instance 101) as raw bytes using a generic message.
        """
        if not self.driver or not self.driver.connected:
            logging.error("Driver not connected.")
            return None
        try:
            # Service 0x0E: Get_Attribute_Single
            # Class 0x04: Assembly Object
            # Instance: 101 (Input 2 Block_AI_DI Format, for 4-channel)
            # Attribute: 3 (The data)
            result = self.driver.generic_message(
                service=0x0E,
                class_code=0x04,
                instance=101,
                attribute=3
            )
            if result and result.value:
                raw_bytes = result.value
                logging.debug(f"Raw input length: {len(raw_bytes)} bytes")
                return raw_bytes
            else:
                logging.error(f"Failed to read input assembly data: {result.error if result else 'No response'}")
                return None
        except Exception as e:
            logging.error(f"Exception while reading raw input assembly: {e}")
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

    def decode_uint(self, raw_bytes, start, end):
        """
        Decode 4 bytes (little-endian) into an unsigned integer.
        """
        try:
            return struct.unpack('<L', raw_bytes[start:end+1])[0]
        except Exception as e:
            logging.error(f"Error decoding bytes {start}-{end} as uint: {e}")
            return None

    def read_all_channels(self):
        """
        Read all measurement channels from raw input using offsets.
        """
        raw_bytes = self.read_raw_input()
        if not raw_bytes:
            return {}

        readings = {}
        for name, ai_tag in self.channels.items():
            start, end = self.offsets.get(ai_tag, (None, None))
            if start is not None and end < len(raw_bytes):
                value = self.decode_float(raw_bytes, start, end)
                readings[name] = value
            else:
                readings[name] = None
        return readings

    def read_channel_statuses(self):
        """
        Read and decode channel status words for all channels.
        Returns a dictionary with status strings.
        """
        raw_bytes = self.read_raw_input()
        if not raw_bytes:
            return {}

        statuses = {}
        status_mappings = {
            "status_ch1": "AI15",
            "status_ch2": "AI16",
            "status_ch3": "AI26",
            "status_ch4": "AI27"
        }

        for name, ai_tag in status_mappings.items():
            start, end = self.offsets.get(ai_tag, (None, None))
            if start is not None and end < len(raw_bytes):
                status_value = self.decode_uint(raw_bytes, start, end)
                if status_value == 0:
                    statuses[name] = "okay"
                else:
                    active_statuses = []
                    for bit, description in self.STATUS_ENUM.items():
                        if (status_value >> bit) & 1:
                            active_statuses.append(description)
                    statuses[name] = ", ".join(active_statuses)
            else:
                statuses[name] = None
        return statuses

    STATUS_ENUM = {
        0: "Calibration Data Warning", 1: "Calibration Data Error", 2: "Reserved",
        3: "Hold Status", 4: "Clean Status", 5: "Reserved",
        6: "Maint Required", 7: "Calibration Required", 8: "CIP Counter Expired",
        9: "SIP Counter Expired", 10: "Autoclave Counter Expired", 11: "Reserved",
        12: "Sensor Disconnected", 13: "Change Sensor/DLI Expired", 14: "Reserved", 15: "Reserved",
        16: "Sensor Status bit0", 17: "Sensor Status bit1", 18: "Sensor Status bit2",
        19: "Sensor Status bit3", 20: "Sensor Status bit4", 21: "Sensor Status bit5",
        22: "Sensor Status bit6", 23: "Sensor Status bit7", 24: "Sensor Status bit8",
        25: "Sensor Status bit9", 26: "Sensor Status bit10", 27: "Sensor Status bit11",
        28: "Sensor Status bit12", 29: "Sensor Status bit13", 30: "Sensor Status bit14",
        31: "Sensor Status bit15"
    }


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