"""
A simple OPC UA server for testing purposes.
It creates nodes for conductivity, temperature, and status for 4 channels.
"""
import asyncio
import logging
from asyncua import Server, ua

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def main():
    _logger = logging.getLogger(__name__)
    # setup our server
    server = Server()
    await server.init()
    server.set_endpoint("opc.tcp://0.0.0.0:4840")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])

    # setup our own namespace
    uri = "http://examples.freeopcua.github.io"
    idx = await server.register_namespace(uri)

    # get Objects node, this is where we should put our nodes
    objects = server.get_objects_node()

    # --- Create Node Structure ---
    # Create a main object for our device
    device_obj = await objects.add_object(idx, "M800_Device")

    # Define the nodes to be created
    node_definitions = {
        # Channel 1
        "Conductivity_Ch1": ua.Variant(0.0, ua.VariantType.Float),
        "Temperature_Ch1": ua.Variant(0.0, ua.VariantType.Float),
        "Status_Ch1": ua.Variant("okay", ua.VariantType.String),
        # Channel 2
        "Conductivity_Ch2": ua.Variant(0.0, ua.VariantType.Float),
        "Temperature_Ch2": ua.Variant(0.0, ua.VariantType.Float),
        "Status_Ch2": ua.Variant("okay", ua.VariantType.String),
        # Channel 3
        "Conductivity_Ch3": ua.Variant(0.0, ua.VariantType.Float),
        "Temperature_Ch3": ua.Variant(0.0, ua.VariantType.Float),
        "Status_Ch3": ua.Variant("okay", ua.VariantType.String),
        # Channel 4
        "Conductivity_Ch4": ua.Variant(0.0, ua.VariantType.Float),
        "Temperature_Ch4": ua.Variant(0.0, ua.VariantType.Float),
        "Status_Ch4": ua.Variant("okay", ua.VariantType.String),
        "WATCHDOG": ua.Variant(False, ua.VariantType.Boolean),
    }

    _logger.info("Creating OPC UA nodes...")
    for name, variant in node_definitions.items():
        new_var = await device_obj.add_variable(f"ns={idx};s={name}", name, variant)
        await new_var.set_writable(True)
        _logger.info(f"  - Created node: ns={idx};s={name}")


    _logger.info("Starting OPC UA server at opc.tcp://0.0.0.0:4840")
    async with server:
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped.")
