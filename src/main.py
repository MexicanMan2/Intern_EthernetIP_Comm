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

# New helper function for the main loop logic
async def _run_main_loop(etherip_client: EtherIPClient, opc_client: OPCUAClient, stop_event: asyncio.Event):
    """Helper function to run the main data exchange loop."""
    try:
        while not stop_event.is_set():
            # Run synchronous blocking I/O in a separate thread
            readings = await asyncio.to_thread(etherip_client.read_all_channels)
            
            if stop_event.is_set(): # Added check after first blocking call
                break

            statuses = await asyncio.to_thread(etherip_client.read_channel_statuses)
            
            if stop_event.is_set(): # Added check after second blocking call
                break
            
            all_data = {**readings, **statuses}
            logging.debug(f"Read data: {all_data}")

            write_tasks = []
            for name, value in all_data.items():
                if value is not None:
                    write_tasks.append(opc_client.write_value(name, value))
            
            if write_tasks:
                results = await asyncio.gather(*write_tasks, return_exceptions=True)
                successful_writes = sum(1 for r in results if r is True)
                failed_writes = sum(1 for r in results if r is False)
                if successful_writes > 0:
                    logging.debug(f"Successfully wrote {successful_writes} values to OPC UA server.")
                if failed_writes > 0:
                    logging.warning(f"Failed to write {failed_writes} values to OPC UA server.")
                
            if stop_event.is_set(): # Added check before watchdog toggle
                break

            if not await opc_client.toggle_watchdog():
                logging.warning("Failed to toggle OPC UA watchdog.")

            # This sleep is responsive to cancellation, no need for check after it
            await asyncio.sleep(1) 
    except asyncio.CancelledError:
        logging.info("Data exchange loop task cancelled.")
    except Exception as e:
        logging.error(f"Error in data exchange loop: {e}", exc_info=True)


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
        await asyncio.sleep(1) # Small delay before checking connect again (connect method has its own delays)
    
    # Initialize OPC UA client
    opc_client = OPCUAClient(opc_endpoint, node_ids)
    # Connect OPC UA with retry logic
    while not await opc_client.connect():
        await asyncio.sleep(1) # Small delay before checking connect again (connect method has its own delays)

    logging.info("Starting data exchange loop... Press Ctrl+C to stop.")
    
    # Create the main data exchange loop as a cancellable task
    main_task = asyncio.create_task(_run_main_loop(etherip_client, opc_client, stop_event)) # New helper function

    try:
        # Wait until stop_event is set (from signal handler)
        await stop_event.wait() 
    except asyncio.CancelledError:
        logging.info("Main task cancelled (likely due to signal).")
    except Exception as e:
        logging.error(f"Error in main loop: {e}", exc_info=True)
    finally:
        logging.info("Cleaning up...")
        # Ensure the main task is truly cancelled and finished
        if not main_task.done():
            main_task.cancel()
            try:
                await main_task # Await cancellation to propagate
            except asyncio.CancelledError:
                pass # Expected during cancellation

        # Ensure proper disconnect based on connection status
        # This part remains mostly the same, as we're explicitly disconnecting clients
        if opc_client.client and opc_client._is_connected:
            await opc_client.disconnect()
        if etherip_client.driver and etherip_client.driver.connected:
            etherip_client.driver.close()
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())