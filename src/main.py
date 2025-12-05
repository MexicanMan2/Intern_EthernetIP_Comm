import asyncio
import yaml
import logging
import signal
import sys
from etherip_client import EtherIPClient
from opcua_client import OPCUAClient



import logging.handlers
import os
from datetime import datetime

# Configure logging
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Create a logger
logger = logging.getLogger()
logger.setLevel(logging.INFO) # Set base level for the logger

# Set pycomm3 logger level to WARNING to suppress verbose INFO messages
pycomm3_logger = logging.getLogger('pycomm3')
pycomm3_logger.setLevel(logging.WARNING) # Set level back to WARNING

# Set asyncua logger level to WARNING to suppress verbose INFO messages
logging.getLogger('asyncua').setLevel(logging.WARNING)

# Create formatter
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# Create console handler and set level to INFO
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Create file handler for daily rotation
# Logs will be named like app.2025-12-05.log
fh = logging.handlers.TimedRotatingFileHandler(
    os.path.join(LOG_DIR, "app.log"),
    when="midnight",
    interval=1,
    backupCount=30, # Keep 30 days of logs
    encoding="utf-8"
)
fh.setLevel(logging.INFO) # File handler logs INFO and above
fh.setFormatter(formatter)
logger.addHandler(fh)

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
    # Connect EtherNet/IP with retry logic
    while not await asyncio.to_thread(etherip_client.connect):
        logging.info("Waiting for EtherNet/IP connection...")
        await asyncio.sleep(1) # Small delay before checking connect again (connect method has its own delays)
    
    # Initialize OPC UA client
    opc_client = OPCUAClient(opc_endpoint, node_ids)
    # Connect OPC UA with retry logic
    while not await opc_client.connect():
        logging.info("Waiting for OPC UA connection...")
        await asyncio.sleep(1) # Small delay before checking connect again (connect method has its own delays)

    logging.info("Starting data exchange loop... Press Ctrl+C to stop.")
    try:
        while not stop_event.is_set():
            # Run synchronous blocking I/O in a separate thread
            readings = await asyncio.to_thread(etherip_client.read_all_channels)
            statuses = await asyncio.to_thread(etherip_client.read_channel_statuses)
            
            all_data = {**readings, **statuses}
            logging.debug(f"Read data: {all_data}")

            # Create a list of tasks for writing to OPC UA
            write_tasks = []
            for name, value in all_data.items():
                if value is not None:
                    write_tasks.append(opc_client.write_value(name, value)) # Collect coroutines directly
            
            # Run all write tasks concurrently and check results
            if write_tasks:
                results = await asyncio.gather(*write_tasks, return_exceptions=True) # Collect results
                successful_writes = sum(1 for r in results if r is True)
                failed_writes = sum(1 for r in results if r is False)
                if successful_writes > 0:
                    logging.debug(f"Successfully wrote {successful_writes} values to OPC UA server.")
                if failed_writes > 0:
                    logging.warning(f"Failed to write {failed_writes} values to OPC UA server.")
                
            # Toggle the watchdog after a successful write cycle
            if not await opc_client.toggle_watchdog():
                logging.warning("Failed to toggle OPC UA watchdog.")

            await asyncio.sleep(1)  # Adjust interval as needed
    except Exception as e:
        logging.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        logging.info("Cleaning up...")
        # Ensure proper disconnect based on connection status
        if opc_client.client and opc_client._is_connected: # Check if still connected
            await opc_client.disconnect()
        if etherip_client.driver and etherip_client.driver.connected:
            etherip_client.driver.close()
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())