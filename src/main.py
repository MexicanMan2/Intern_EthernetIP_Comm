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
    eth_ip = config["ethernetip"]["ip_address"]
    eds_file = config["ethernetip"]["eds_file"]

    # Initialize EtherNet/IP client
    etherip_client = EtherIPClient(ip_address=eth_ip, eds_file=eds_file)
    # The connect call is synchronous and should be run in an executor
    await asyncio.to_thread(etherip_client.connect)

    if not etherip_client.driver or not etherip_client.driver.connected:
        logging.error("Could not connect to EtherNet/IP device. Exiting.")
        return

    # Initialize OPC UA client
    opc_client = OPCUAClient(opc_endpoint, node_ids)
    await opc_client.connect()

    logging.info("Starting data exchange loop... Press Ctrl+C to stop.")
    try:
        while not stop_event.is_set():
            # Run synchronous blocking I/O in a separate thread
            readings = await asyncio.to_thread(etherip_client.read_all_channels)
            statuses = await asyncio.to_thread(etherip_client.read_channel_statuses)
            
            all_data = {**readings, **statuses}
            logging.info(f"Read data: {all_data}")

            # Create a list of tasks for writing to OPC UA
            write_tasks = []
            for name, value in all_data.items():
                if value is not None:
                    task = opc_client.write_value(name, value)
                    write_tasks.append(task)
            
            # Run all write tasks concurrently
            if write_tasks:
                await asyncio.gather(*write_tasks)
                logging.info(f"Wrote {len(write_tasks)} values to OPC UA server.")

            # Toggle the watchdog after a successful write cycle
            await opc_client.toggle_watchdog()

            await asyncio.sleep(1)  # Adjust interval as needed
    except Exception as e:
        logging.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        logging.info("Cleaning up...")
        if opc_client.client and opc_client.client.uaclient:
            await opc_client.disconnect()
        if etherip_client.driver and etherip_client.driver.connected:
            etherip_client.driver.close()
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())