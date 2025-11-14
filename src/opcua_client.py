import asyncio
import logging
from asyncua import Client

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

    async def connect(self):
        """
        Connect to OPC UA server and resolve node references.
        """
        try:
            await self.client.connect()
            logging.info(f"Connected to OPC UA server at {self.endpoint}")
            # Resolve node references
            for name, node_id in self.node_ids.items():
                self.nodes[name] = self.client.get_node(node_id)
            logging.info(f"Resolved {len(self.nodes)} OPC UA nodes.")
        except Exception as e:
            logging.error(f"Failed to connect to OPC UA server: {e}")

    async def write_value(self, name: str, value: float):
        """
        Write a value to an OPC UA node.
        """
        try:
            node = self.nodes.get(name)
            if node:
                await node.write_value(value)
                logging.debug(f"Updated {name} with value {value}")
            else:
                logging.error(f"Node {name} not found in mapping.")
        except Exception as e:
            logging.error(f"Error writing to node {name}: {e}")

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