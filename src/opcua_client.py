import asyncio
import logging
from asyncua import Client, ua
import time


class OPCUAClient:
    def __init__(self, endpoint: str, node_ids: dict):
        """
        Initialize OPC UA client with endpoint and node mapping.
        """
        self.endpoint = endpoint
        self.node_ids = node_ids
        self.client = Client(url=self.endpoint)
        self.nodes = {}
        self.node_datatypes = {} # New: Store expected data types
        self.watchdog_state = False
        self.reconnect_attempts = 0
        self.last_reconnect_time = 0
        self._is_connected = False # Custom connection state variable

    async def connect(self):
        """
        Connect to OPC UA server with retry logic.
        """
        current_time = time.time()
        # Only attempt reconnect if enough time has passed based on the reconnect strategy
        if self._is_connected: # Check using our custom variable
            return True

        # Calculate delay based on reconnect_attempts
        if self.reconnect_attempts < 10:
            delay = 1 # 1 second for first 10 attempts
        elif self.reconnect_attempts < 20:
            delay = 30 # 30 seconds for next 10 attempts
        else:
            delay = 300 # 5 minutes thereafter

        if current_time - self.last_reconnect_time < delay:
            # Not enough time has passed for next retry
            return False

        self.last_reconnect_time = current_time
        self.reconnect_attempts += 1

        logging.info(f"Attempting to connect to OPC UA server at {self.endpoint} (Attempt {self.reconnect_attempts})...")

        try:
            await self.client.connect()
            logging.info(f"Connected to OPC UA server at {self.endpoint} after {self.reconnect_attempts} attempts.")
            self._is_connected = True # Set custom variable to True on success
            
            # Resolve node references and query data types
            for name, node_id in self.node_ids.items():
                node = self.client.get_node(node_id)
                self.nodes[name] = node
                
                # Query and store the expected DataType
                try:
                    expected_variant_type = await node.read_data_type_as_variant_type()
                    self.node_datatypes[name] = expected_variant_type
                    logging.debug(f"Node {name} ({node_id}) expects VariantType: {expected_variant_type}")
                except Exception as dt_e:
                    logging.warning(f"Could not determine expected VariantType for node {name} ({node_id}): {dt_e}. Will infer from Python type at write time.")
                    self.node_datatypes[name] = None
                    
            logging.info(f"Resolved {len(self.nodes)} OPC UA nodes.")
            self.reconnect_attempts = 0 # Reset on success
            self.last_reconnect_time = 0
            return True
        except Exception as e:
            logging.error(f"Failed to connect to OPC UA server at {self.endpoint} (Attempt {self.reconnect_attempts}): {e}. Next attempt in {delay} seconds.")
            self._is_connected = False # Set custom variable to False on failure
            return False

    async def write_value(self, name: str, value):
        """
        Write a value to an OPC UA node with an explicit data type, ensuring connection is active.
        """
        # Ensure connection is active. The connect method handles its own retry logic.
        if not self._is_connected: # Check using our custom variable
            logging.warning(f"OPC UA client not connected. Attempting to reconnect before writing to {name}.")
            if not await self.connect(): # self.connect() handles the delays and retries
                logging.error(f"Failed to establish/reconnect OPC UA server. Cannot write to {name}.")
                return False

        try:
            node = self.nodes.get(name)
            if node:
                expected_variant_type = self.node_datatypes.get(name)
                typed_value = value # Default to original value

                # Apply type conversion based on expected_variant_type
                if expected_variant_type == ua.VariantType.Boolean:
                    typed_value = bool(value)
                elif expected_variant_type in (ua.VariantType.Int16, ua.VariantType.Int32, ua.VariantType.Int64, ua.VariantType.UInt16, ua.VariantType.UInt32, ua.VariantType.UInt64):
                    typed_value = int(value)
                elif expected_variant_type in (ua.VariantType.Float, ua.VariantType.Double):
                    typed_value = float(value)
                elif expected_variant_type == ua.VariantType.String:
                    typed_value = str(value)
                else: # Fallback to original type inference if type is unknown or None
                    if expected_variant_type is None: # Only warn if we explicitly failed to get type
                        logging.warning(f"No specific VariantType determined for node {name}. Inferring from Python type.")

                # If expected_variant_type is None, ua.Variant will infer.
                variant = ua.Variant(typed_value, expected_variant_type if expected_variant_type else None)
                
                await node.write_value(ua.DataValue(variant))
                logging.debug(f"Updated {name} with value {typed_value} (original: {value}) as VariantType: {expected_variant_type}")
                return True # Indicate success
            else:
                logging.error(f"Node {name} not found in mapping.")
                return False # Indicate failure
        except Exception as e:
            # If a write fails even when is_connected was True, it might mean the connection just dropped.
            # Disconnect to force a reconnect attempt on next cycle.
            logging.error(f"Error writing to node {name}: {e}. Disconnecting to force reconnect.")
            try:
                await self.client.disconnect()
            except Exception as disconnect_e:
                logging.warning(f"Error during forced disconnect: {disconnect_e}")
            self._is_connected = False # Set custom variable to False on failure
            return False


    async def toggle_watchdog(self):
        """
        Toggles the watchdog node between True and False.
        Returns True if successful, False otherwise.
        """
        self.watchdog_state = not self.watchdog_state
        success = await self.write_value("watchdog", self.watchdog_state)
        if success:
            logging.debug(f"Toggled watchdog to {self.watchdog_state}")
        else:
            logging.error(f"Failed to toggle watchdog to {self.watchdog_state}")
        return success


    async def disconnect(self):
        """
        Disconnect from OPC UA server.
        """
        try:
            await self.client.disconnect()
            self._is_connected = False # Set custom variable to False on disconnect
            logging.info("Disconnected from OPC UA server.")
        except Exception as e:
            logging.error(f"Error during OPC UA disconnect: {e}")
            self._is_connected = False # Also set to False if disconnect fails

# For standalone testing
async def main():
    node_ids = {
        "conductivity_ch1": 'ns=2;s="Conductivity_Ch1"',
        "conductivity_ch2": 'ns=2;s="Conductivity_Ch2"',
        "conductivity_ch3": 'ns=2;s="Conductivity_Ch3"',
        "conductivity_ch4": 'ns=2;s="Conductivity_Ch4"',
    }

    opc_client = OPCUAClient("opc.tcp://192.168.178.230:4840", node_ids)
    await opc_client.connect()

    # Test writing values
    for i in range(5):
        for name in node_ids.keys():
            await opc_client.write_value(name, i * 1.23)
        await asyncio.sleep(2)

    await opc_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())