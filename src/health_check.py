import yaml
import socket
import asyncio
import sys
from asyncua import Client

# Load config.yaml
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

opcua_endpoint = config["opcua"]["endpoint"]
ethernetip_ip = config["ethernetip"]["ip_address"]

async def check_opcua():
    """Check OPC UA connectivity by attempting to connect and disconnect."""
    try:
        client = Client(opcua_endpoint)
        await client.connect()
        await client.disconnect()
        return True
    except Exception as e:
        print(f"OPC UA check failed: {e}")
        return False

def check_ethernetip():
    """Check EtherNet/IP connectivity by opening a TCP socket on port 44818."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ethernetip_ip, 44818))  # EtherNet/IP standard port
        s.close()
        return True
    except Exception as e:
        print(f"EtherNet/IP check failed: {e}")
        return False

async def main():
    opcua_ok = await check_opcua()
    ethernetip_ok = check_ethernetip()

    if opcua_ok and ethernetip_ok:
        print("Health check passed: OPC UA and EtherNet/IP are reachable.")
        sys.exit(0)
    else:
        print("Health check failed.")
        sys.exit(1)

if __name__ == "__main__":
