import logging
import time
import struct
from typing import Dict, Tuple, Optional

from pycomm3 import CIPDriver
from eds_parser import parse_eds


class EtherIPClient:
    """
    EtherNet/IP-Client, der ausschließlich **unverbundene** (UCMM) CIP-Nachrichten nutzt.
    Keine Forward-Open/connected messaging. IP kommt aus einer Config.
    """

    STATUS_ENUM: Dict[int, str] = {
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

    def __init__(self, ip_address: str, eds_file: str, timeout: float = 5.0):
        """Initialisiert den Client.

        Args:
            ip_address: IP-Adresse des Geräts.
            eds_file: Pfad zur EDS-Datei.
            timeout: Socket-Timeout (Sek.).
        """
        parsed = parse_eds(eds_file)
        self.device_info = parsed.get("device_info", {})
        self.offsets: Dict[str, Tuple[int, int]] = parsed.get("offsets", {})

        self.ip_address = ip_address
        self.timeout = timeout

        self.driver: Optional[CIPDriver] = None
        self.reconnect_attempts = 0
        self.last_reconnect_time = 0.0

        # Zuordnung der Kanäle zu AI-Slots (laut Doku/EDS)
        self.channels = {
            "conductivity_ch1": "AI1",
            "temperature_ch1": "AI2",
            "conductivity_ch2": "AI5",
            "temperature_ch2": "AI6",
            "conductivity_ch3": "AI17",
            "temperature_ch3": "AI18",
            "conductivity_ch4": "AI21",
            "temperature_ch4": "AI22",
        }

    # --- Hilfsfunktion: garantiert unverbundene CIP-Nachrichten ---
    def gm_unconnected(self, **kwargs):
        """Wrapper für generic_message(), der immer unconnected sendet."""
        if not self.driver:
            raise RuntimeError("Driver ist nicht initialisiert.")
        return self.driver.generic_message(connected=False, **kwargs)

    def connect(self) -> bool:
        """Verbindet sich mit dem Gerät mit Backoff-Strategie (nur UCMM)."""
        current_time = time.time()

        # Bereits verbunden?
        if self.driver and self.driver.connected:
            return True

        # Backoff-Delay je nach Anzahl Versuche
        if self.reconnect_attempts < 10:
            delay = 1
        elif self.reconnect_attempts < 20:
            delay = 30
        else:
            delay = 300

        if current_time - self.last_reconnect_time < delay:
            return False

        self.last_reconnect_time = current_time
        self.reconnect_attempts += 1
        logging.info(f"Attempting to connect to EtherNet/IP device at {self.ip_address} (Attempt {self.reconnect_attempts})...")

        try:
            # Keine Route/Slot/RPI, kein connected messaging
            self.driver = CIPDriver(self.ip_address, timeout=self.timeout, init_forward_open=False)
            connection_successful = self.driver.open()

            if connection_successful:
                logging.info(
                    f"Successfully connected to EtherNet/IP device at {self.ip_address} after {self.reconnect_attempts} attempts."
                )
                self.reconnect_attempts = 0
                self.last_reconnect_time = 0

                # Unconnected Verification: Identity lesen
                resp = self.gm_unconnected(
                    service=0x0E,  # Get_Attribute_Single
                    class_code=0x01,  # Identity Object
                    instance=1,
                    attribute=1,
                )
                logging.info(f"Identity/1/1 response: {resp}")
                return True

            else:
                error_message = str(self.driver.last_error) if getattr(self.driver, 'last_error', None) else ''
                logging.error(
                    f"Failed to connect to {self.ip_address} (Attempt {self.reconnect_attempts}). Error: {error_message}."
                )
                self.driver = None
                return False

        except Exception as e:
            logging.error( # Changed from logging.exception
                f"Unexpected exception while connecting to {self.ip_address} (Attempt {self.reconnect_attempts}): {e}"
            )
            self.driver = None
            return False

    def read_raw_input(self) -> Optional[bytes]:
        """Liest das komplette Input-Assembly (Instance 101, Attr 3) als Bytes via UCMM."""
        if not self.driver or not self.driver.connected:
            if not self.connect():
                logging.error("Driver not connected and failed to reconnect.")
                return None

        try:
            result = self.gm_unconnected(
                service=0x0E,           # Get_Attribute_Single
                class_code=0x04,        # Assembly Object
                instance=101,           # Input 2 Block_AI_DI Format (4-Kanal-Version)
                attribute=3             # Data
            )
            if result and getattr(result, 'value', None):
                raw_bytes = result.value
                logging.debug(f"Raw input length: {len(raw_bytes)} bytes")
                return raw_bytes
            else:
                err = getattr(result, 'error', None) if result else 'No response'
                logging.error(f"Failed to read input assembly data: {err}")
                return None
        except Exception as e:
            logging.error(f"Exception while reading raw input assembly: {e}")
            return None

    @staticmethod
    def decode_float(raw_bytes: bytes, start: int, end: int) -> Optional[float]:
        """Dekodiert 4 Bytes (little-endian) zu float.
        Erwartet genau 4 Bytes: Indizes inklusiv (start..end)."""
        try:
            segment = raw_bytes[start:end+1]
            if len(segment) != 4:
                raise ValueError(f"Float segment length must be 4, got {len(segment)}")
            return struct.unpack('<f', segment)[0]
        except Exception as e:
            logging.error(f"Error decoding bytes {start}-{end} as float: {e}")
            return None

    @staticmethod
    def decode_uint(raw_bytes: bytes, start: int, end: int) -> Optional[int]:
        """Dekodiert 4 Bytes (little-endian) zu unsigned int (32 Bit)."""
        try:
            segment = raw_bytes[start:end+1]
            if len(segment) != 4:
                raise ValueError(f"Uint segment length must be 4, got {len(segment)}")
            return struct.unpack('<L', segment)[0]
        except Exception as e:
            logging.error(f"Error decoding bytes {start}-{end} as uint: {e}")
            return None

    def read_all_channels(self) -> Dict[str, Optional[float]]:
        """Liest alle Messkanäle anhand der EDS-Offsets."""
        raw_bytes = self.read_raw_input()
        if not raw_bytes:
            return {}

        readings: Dict[str, Optional[float]] = {}
        for name, ai_tag in self.channels.items():
            start, end = self.offsets.get(ai_tag, (None, None))
            if start is not None and end is not None and end < len(raw_bytes):
                value = self.decode_float(raw_bytes, start, end)
                readings[name] = value
            else:
                readings[name] = None
        return readings

    def read_channel_statuses(self) -> Dict[str, Optional[str]]:
        """Liest und dekodiert die Status-Wörter der Kanäle."""
        raw_bytes = self.read_raw_input()
        if not raw_bytes:
            return {}

        statuses: Dict[str, Optional[str]] = {}
        status_mappings = {
            "status_ch1": "AI15",
            "status_ch2": "AI16",
            "status_ch3": "AI26",
            "status_ch4": "AI27",
        }
        for name, ai_tag in status_mappings.items():
            start, end = self.offsets.get(ai_tag, (None, None))
            if start is not None and end is not None and end < len(raw_bytes):
                status_value = self.decode_uint(raw_bytes, start, end)
                if status_value is None:
                    statuses[name] = None
                    continue
                if status_value == 0:
                    statuses[name] = "okay"
                else:
                    active = []
                    for bit, description in self.STATUS_ENUM.items():
                        if (status_value >> bit) & 1:
                            active.append(description)
                    statuses[name] = ", ".join(active) if active else "okay"
            else:
                statuses[name] = None
        return statuses

    def health_check_loop(self, interval: int = 5):
        """Endlos-Schleife: liest und loggt alle Kanäle; Strg+C zum Abbrechen."""
        logging.info("Starting data exchange loop... Press Ctrl+C to stop.")
        try:
            while True:
                readings = self.read_all_channels()
                logging.info(f"Current readings: {readings}")
                time.sleep(interval)
        except KeyboardInterrupt:
            logging.info("Health check loop interrupted by user.")
        finally:
            # Sauber schließen
            try:
                if self.driver:
                    self.driver.close()
            except Exception:
                pass