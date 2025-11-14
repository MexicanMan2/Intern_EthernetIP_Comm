import configparser
from pathlib import Path

def parse_eds(file_path: str) -> dict:
    """
    Parse EDS file and return device configuration including assembly info and offsets.
    """
    config = configparser.ConfigParser(strict=False)
    config.optionxform = str  # preserve case
    config.read(file_path)

    device_info = {
        "Vendor": config.get("Device", "Vendor", fallback="Unknown"),
        "ProductName": config.get("Device", "Product Name", fallback="Unknown"),
        "Revision": config.get("Device", "Revision", fallback="Unknown"),
        "IPAddress": "192.168.178.237"
    }

    # Extract Assembly info
    assemblies = {}
    for section in config.sections():
        if section.startswith("Assembly"):
            assemblies[section] = dict(config.items(section))

    # Calculate offsets for AI slots (4 bytes per slot)
    # Assume Input Assembly size is given in EDS or default to 128 bytes for 4-channel block
    input_size = int(assemblies.get("Assembly 100", {}).get("Size", 128))  # Example: Assembly 100 = Input
    slot_size = 4  # bytes per AI slot
    num_slots = input_size // slot_size

    offsets = {}
    for i in range(1, num_slots + 1):
        start = (i - 1) * slot_size
        end = start + slot_size - 1
        offsets[f"AI{i}"] = (start, end)

    return {
        "device_info": device_info,
        "assemblies": assemblies,
        "offsets": offsets
    }

if __name__ == "__main__":
    eds_file = Path("./eds_files/MT_M800_1P_EIP_V1.2_20200107.eds")
    parsed = parse_eds(str(eds_file))
    print("Device Info:", parsed["device_info"])
    print("Assemblies:", parsed["assemblies"])
    print("Offsets:", parsed["offsets"])