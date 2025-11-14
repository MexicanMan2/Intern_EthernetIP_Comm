import asyncio
import yaml
import logging
import signal
import sys
from etherip_client import EtherIPClient
from opcua_client import OPCUAClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Graceful shutdown handler
stop_event = asyncio.Event()

def shutdown_handler(sig, frame):
    logging.info("Shutdown signal received. Stopping...")
    stop_event.set()

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

async def main():
    # Load configuration
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    opc_endpoint = config["opcua"]["endpoint"]
    node_ids = config["opcua"]["nodes"]
    eds_file = config["ethernetip"]["eds_file"]

    # Initialize EtherNet/IP client
    etherip_client = EtherIPClient(eds_file)
    etherip_client.connect()

    # Initialize OPC UA client
    opc_client = OPCUAClient(opc_endpoint, node_ids)
    await opc_client.connect()

    logging.info("Starting data exchange loop...")
    try:
        while not stop_event.is_set():
            readings = etherip_client.read_all_channels()
            logging.info(f"EtherNet/IP readings: {readings}")

            # Push readings to OPC UA
            for name, value in readings.items():
                await opc_client.write_value(name, value)

            await asyncio.sleep(2)  # Adjust interval as needed
    except Exception as e:
        logging.error(f"Error in main loop: {e}")
    finally:
        logging.info("Cleaning up...")
        await opc_client.disconnect()
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())