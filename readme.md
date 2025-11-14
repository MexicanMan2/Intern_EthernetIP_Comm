# EtherNet/IP Communication Program in Python

To communicate with EtherNet/IP Sensor Devices and populate the Data via OPCUA Connection.

## EtherNet/IP Sensor Devices
1) Mettler-Toledo M800 4ch - EDS file in "./Mettler Toledo/M800_EIP_EDS/MT_M800 1P_EIP_V1.2_20200107.eds"

## OPC UA Server
Will be hosted by a PLC at: 192.168.178.230:4840

## Software Functions

1) Read EDS File and extract Configuration for the device
2) Connect to the device and make regular heatlh-checks
3) Read Data from Device
4) Optional: If neccessary, be able to set device configurations
5) Populate the Data Read via OPC UA Connection
6) Connect to OPCUA Server
7) Optional: Provide a FASTapi Endpoint for a potential frontend

## Libraries
- EtherNet/IP use pycomm3
- OPC use asyncua

## Architecture
Create a Python module structure:
/src
  ├── main.py
  ├── etherip_client.py
  ├── opcua_client.py
  ├── eds_parser.py
  ├── api.py (optional)

## Deployment
It should run in a Docker-Container in the end.
- python:3.11-slim base image.
- Install dependencies via requirements.txt.
- Health-check endpoint or container restart policy for robustness.

## FASTAPI
It is optional, I think we can go deeper later.

# First Response from Copilot

✅ Current Scope

EtherNet/IP Sensor Devices: Example device is a Mettler-Toledo M800 4ch, with an EDS file provided.
OPC UA Server: Hosted by a PLC at 192.168.178.230:4840.
Planned Functions:

Parse EDS file for device configuration.
Connect to device and perform health checks.
Read data from device.
(Optional) Set device configurations.
Push data to OPC UA server.
Connect to OPC UA server.
(Optional) Provide a FASTAPI endpoint for a frontend.

🔍 Questions to clarify:

EtherNet/IP Library: Do you plan to use pycomm3 or another library for CIP/EtherNet/IP communication?
OPC UA Integration: Should we use opcua Python library or asyncua for better performance?
Architecture: Do you want a modular design (separate classes for Device, OPC UA Client, API)?
Deployment: Should this run in Docker (similar to your previous projects)?
FASTAPI: Should the API expose real-time data or just configuration endpoints?

✅ Suggested Next Steps

Step 1: Create a Python module structure:
/src
  ├── main.py
  ├── etherip_client.py
  ├── opcua_client.py
  ├── eds_parser.py
  ├── api.py (optional)

Step 2: Implement EDS parser (basic INI-like parsing).
Step 3: Use pycomm3 for EtherNet/IP communication.
Step 4: Use opcua library to connect and publish data.
Step 5: Add health-check loop and logging.
Step 6: (Optional) Add FASTAPI for REST endpoints.

# Discussions

## Which Library to use for EtherNet/IP Communication

1. pycomm3

Pros:

Actively maintained and widely used for EtherNet/IP and CIP communication.
Supports Logix controllers and generic CIP messaging.
Simple API for reading/writing tags.
Good documentation and examples.

Cons:

Primarily focused on Rockwell/Allen-Bradley PLCs.
Limited advanced diagnostics for non-PLC devices (like sensors).

2. Alternatives

cpppo:

Python-based EtherNet/IP implementation.
More flexible for custom CIP objects and non-standard devices.
Can act as both client and server.
Cons: Less active development, harder to set up.

Custom CIP stack:

Full control over protocol.
Cons: High complexity, not recommended unless you need deep customization.

Key Differences

Ease of Use: pycomm3 is easier and faster to implement for standard devices.
Flexibility: cpppo gives more control for unusual devices or custom objects.
Community & Support: pycomm3 has better community support and documentation.

✅ Recommendation for your case:
Since you’re working with a Mettler-Toledo sensor and want to integrate with OPC UA, start with pycomm3. It’s simpler, and if the device supports standard CIP objects, it will work well. If you hit limitations (e.g., custom objects not supported), then consider cpppo.

--> Yes, we first try pycomm3

# Project Plan

✅ Phase 1: Project Setup

Create folder structure:
/src
  ├── main.py
  ├── etherip_client.py
  ├── opcua_client.py
  ├── eds_parser.py
  ├── api.py (optional)

Initialize Git repository and add .gitignore.
Create requirements.txt with:
pycomm3
asyncua

(Later: add fastapi and uvicorn if needed.)
Prepare Dockerfile (basic Python image, install dependencies).

✅ Phase 2: Core Functionality
Step 2.1 – EDS Parser

Parse the EDS file to extract device configuration (IP, tags, etc.).
Output a Python dictionary or config object.

Step 2.2 – EtherNet/IP Client

Implement etherip_client.py using pycomm3:

Connect to device.
Read tags or attributes.
Health-check loop.

Step 2.3 – OPC UA Client

Implement opcua_client.py using asyncua:

Connect to OPC UA server.
Create nodes if needed.
Publish data from EtherNet/IP client.

✅ Phase 3: Integration

main.py orchestrates:

Load config from EDS parser.
Start EtherNet/IP client.
Push data to OPC UA client.
Add logging and error handling.

✅ Phase 4: Deployment

Build Docker image.
Test container locally.
Add health-check and restart policy.

✅ Phase 5: Optional Enhancements

Add FASTAPI for REST endpoints (status, config).
Add unit tests.
Add CI/CD pipeline.


# Next Steps for User to check:
* Confirm the actual EtherNet/IP tag name for the Input Assembly (often "Input" or "O.Input" in Logix).
* Test with real device to verify offsets and values.
