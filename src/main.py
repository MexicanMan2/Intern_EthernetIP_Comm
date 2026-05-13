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

async def connect_with_retry(connect_func, client_name, max_attempts=10, initial_delay=5):
    """
    Attempts to connect using the provided async connect_func with exponential backoff.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            logging.info(f"Attempting to connect to {client_name} (Attempt {attempt})...")
            if asyncio.iscoroutinefunction(connect_func):
                connected = await connect_func()
            else:
                # Assuming synchronous connect_func like EtherIPClient's connect needs to be run in a thread
                connected = await asyncio.to_thread(connect_func)

            if connected:
                logging.info(f"Successfully connected to {client_name} after {attempt} attempts.")
                return True
        except Exception as e:
            logging.error(f"Unexpected exception while connecting to {client_name} (Attempt {attempt}): {e}")

        if attempt < max_attempts:
            delay = initial_delay * (2 ** (attempt - 1))
            logging.info(f"Retrying {client_name} in {delay} seconds...")
            try:
                # Wait for the delay OR for the stop_event to be set
                await asyncio.wait_for(stop_event.wait(), timeout=delay)
                # If we get here, the stop_event was set during the delay
                logging.info(f"Stop event received during retry-wait for {client_name}. Aborting connection attempts.")
                return False # Abort connection attempts
            except asyncio.TimeoutError:
                # This is the normal path, the sleep delay finished without a stop signal
                pass
    logging.error(f"Failed to connect to {client_name} after {max_attempts} attempts. Giving up.")
    return False

# New helper function for the main loop logic
async def _run_main_loop(etherip_client: EtherIPClient, opc_client: OPCUAClient, stop_event: asyncio.Event):
    """Helper function to run the main data exchange loop with robust error handling."""
    
    etherip_error_count = 0
    max_consecutive_etherip_errors = 5
    base_sleep_delay = 1 # seconds

    try:
        while not stop_event.is_set():
            current_sleep_delay = base_sleep_delay

            # --- EtherNet/IP Read Operations ---
            try:
                readings = await asyncio.to_thread(etherip_client.read_all_channels)
                statuses = await asyncio.to_thread(etherip_client.read_channel_statuses)
                all_data = {**readings, **statuses}
                logging.debug(f"Read data: {all_data}")
                etherip_error_count = 0 # Reset error count on success
            except Exception as e:
                etherip_error_count += 1
                logging.error(f"Error reading from EtherNet/IP device (consecutive errors: {etherip_error_count}): {e}", exc_info=False)
                # If too many errors, increase sleep delay
                if etherip_error_count >= max_consecutive_etherip_errors:
                    current_sleep_delay = base_sleep_delay * (2 ** (etherip_error_count // max_consecutive_etherip_errors))
                    logging.warning(f"Persistent EtherNet/IP errors. Increasing loop delay to {current_sleep_delay}s.")
                
                await asyncio.sleep(current_sleep_delay) # Wait before retrying EtherNet/IP
                continue # Skip the rest of the loop if EtherNet/IP read failed


            # --- OPC UA Write Operations ---
            write_tasks = []
            for name, value in all_data.items():
                if value is not None:
                    write_tasks.append(opc_client.write_value(name, value))
            
            if write_tasks:
                # asyncio.gather will run writes concurrently. write_value handles its own reconnections and logging.
                results = await asyncio.gather(*write_tasks, return_exceptions=True)
                successful_writes = sum(1 for r in results if r is True)
                failed_writes = sum(1 for r in results if r is False) # opc_client.write_value returns True/False
                
                if successful_writes > 0:
                    logging.debug(f"Successfully wrote {successful_writes} values to OPC UA server.")
                if failed_writes > 0:
                    logging.warning(f"Failed to write {failed_writes} values to OPC UA server.")
                
            # --- OPC UA Watchdog Toggle ---
            if opc_client._is_connected: # Only try to toggle if OPC UA client thinks it's connected
                try:
                    if not await opc_client.toggle_watchdog():
                        logging.warning("Failed to toggle OPC UA watchdog.")
                except Exception as e:
                    logging.error(f"Error toggling OPC UA watchdog: {e}", exc_info=False)
            else:
                logging.debug("Skipping OPC UA watchdog toggle as client is not connected.")
            
            await asyncio.sleep(current_sleep_delay) # Use adjusted delay

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
    etherip_connected = await connect_with_retry(etherip_client.connect, "EtherNet/IP device", max_attempts=10, initial_delay=5)
    if not etherip_connected:
        logging.error("Failed to establish EtherNet/IP connection. Exiting.")
        return # Exit if critical connection fails
    
    # Initialize OPC UA client
    opc_client = OPCUAClient(opc_endpoint, node_ids)
    # Connect OPC UA with retry logic
    opcua_connected = await connect_with_retry(opc_client.connect, "OPC UA server", max_attempts=10, initial_delay=5)
    if not opcua_connected:
        logging.error("Failed to establish OPC UA connection. Exiting.")
        return # Exit if critical connection fails

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
            await asyncio.to_thread(etherip_client.driver.close)
        logging.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())