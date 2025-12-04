import asyncio
import logging
from asyncua import Client, ua

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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

    async def connect(self):
        """
        Connect to OPC UA server and resolve node references.
        """
        try:

            await self.client.connect()
            logging.info(f"Connected to OPC UA server at {self.endpoint}")
            # Resolve node references and query data types
            for name, node_id in self.node_ids.items():
                node = self.client.get_node(node_id)
                self.nodes[name] = node
                
                # Query and store the expected DataType
                try:
                    # Read the DataType attribute (AttributeId.DataType = 6)
                    # The value of this attribute is the NodeId of the DataType node
                    datatype_nodeid = await node.read_attribute(ua.AttributeIds.DataType)
                    # Get the actual DataType object from the server
                    datatype = await self.client.get_node(datatype_nodeid.Value.Value).read_data_type_as_variant_type()
                    self.node_datatypes[name] = datatype
                    logging.debug(f"Node {name} ({node_id}) expects DataType: {datatype}")
                except Exception as dt_e:
                    logging.warning(f"Could not determine DataType for node {name} ({node_id}): {dt_e}. Will infer from Python type.")
                    self.node_datatypes[name] = None # Fallback to inference
                    
            logging.info(f"Resolved {len(self.nodes)} OPC UA nodes.")
        except Exception as e:
            logging.error(f"Failed to connect to OPC UA server: {e}")

    async def write_value(self, name: str, value):
        """
        Write a value to an OPC UA node with an explicit data type.
        """
        try:
            node = self.nodes.get(name)
            if node:
                expected_datatype = self.node_datatypes.get(name)
                
                if expected_datatype:
                    # Use the queried DataType
                    variant = ua.Variant(value, expected_datatype)
                elif isinstance(value, float):
                    variant = ua.Variant(value, ua.VariantType.Float)
                elif isinstance(value, str):
                    variant = ua.Variant(value, ua.VariantType.String)
                elif isinstance(value, bool):
                    variant = ua.Variant(value, ua.VariantType.Boolean)
                else:
                    variant = ua.Variant(value) # Fallback to inference
                
                await node.write_value(ua.DataValue(variant))
                logging.debug(f"Updated {name} with value {value}")
            else:
                logging.error(f"Node {name} not found in mapping.")
        except Exception as e:
            logging.error(f"Error writing to node {name}: {e}")

    async def toggle_watchdog(self):
        """
        Toggles the watchdog node between True and False.
        """
        self.watchdog_state = not self.watchdog_state
        await self.write_value("watchdog", self.watchdog_state)
        logging.info(f"Toggled watchdog to {self.watchdog_state}")

    async def disconnect(self):
        """
        Disconnect from OPC UA server.
        """
        try:
            await self.client.disconnect()
            logging.info("Disconnected from OPC UA server.")
        except Exception as e:
            logging.error(f"Error during OPC UA disconnect: {e}")

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