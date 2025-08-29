# MIMO-and-RIS-control-code

Python code for beam steering MIMO antennas and controlling Reflective Intelligent Surfaces (RIS) using TMYTEK hardware. This guide explains setup, running the main code, local host/server configuration, and usage of the main test functions.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Directory Structure](#directory-structure)
3. [Installation](#installation)
4. [Setting Up Local Host and Server](#setting-up-local-host-and-server)
5. [Running the Main Code](#running-the-main-code)
6. [Using Test Functions](#using-test-functions)

   * [testBBoard](#testbboard)
   * [testRIS](#testris)
   * [testPD](#testpd)
7. [Example Workflow](#example-workflow)
8. [Logging](#logging)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

* **Python 3.12 (64-bit)**
* Windows OS (recommended)
* TMYTEK hardware and drivers
* Required Python packages:

  * `psutil`
  * `pyserial`
  * `ft4222`
  * `tftpy`
  * `numpy`
  * `matplotlib`
  * `requests`

---

## Directory Structure

* `main.py` — Main entry point for device control and testing
* `lib/tlkcore/` — TMYTEK Python library modules
* `CustomBatchBeams.csv` — Example beam configuration file
* `logging.conf` / `logging_abs.conf` — Logging configuration files
* `tlk_core_log/` — Log files

---

## Installation

1. Clone the repository and navigate to the project folder.
2. Install dependencies:

   ```sh
   pip install -r requirements.txt
   ```
3. Ensure TMYTEK hardware and drivers are installed and connected.

---

## Setting Up Local Host and Server

Some test functions require a TCP socket connection between a server (device controller) and a client (measurement PC or GUI).

### Server Setup

* The server is started automatically by functions like `testBBoard` and `testRIS`.
* **Server IP:** `0.0.0.0` (binds to all interfaces)
* **Port:** `5003`
* No manual setup is needed; just run the main script.

### Client Setup

On the measurement PC, connect to the server using the device's IP and port. Example Python client code:

```python
import socket

HOST = '192.168.137.1'  # Replace with server IP
PORT = 5003

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    while True:
        data = s.recv(1024)
        print("Received:", data.decode())
        # Send measurement result (e.g., power value)
        s.sendall(b"-20.5")
```

---

## Running the Main Code

To start device scanning and testing, run:

```sh
python main.py
```

---

## Using Test Functions

### testBBoard(sn, service)

**Purpose:**

* Configure and test a beamforming board (BBoard), including RF mode, frequency, AAKit selection, and beam steering.

**Socket Role:**

* Acts as a server, sends theta to client, receives power measurement.

**User Input:**

* Prompts for theta angle.

**Steps:**

1. Configures the BBoard device and sets up the socket server.
2. Prompts the user for theta angle.
3. Sends theta to the client and receives power measurement.
4. Logs and displays results.
5. Called automatically for BBoard devices during main execution.

---

### testRIS(sn, service)

**Purpose:**

* Sweeps RIS reflection angles (theta, phi) to find optimal configuration for received power.

**Socket Role:**

* Acts as a server, sends phi to client, receives power measurement.

**User Input:**

* Prompts for incident theta and phi.

**Steps:**

1. Configures the RIS device and sets up the socket server.
2. Prompts the user for incident angles.
3. Sends phi to the client and receives power measurement.
4. Logs and displays results.
5. Called automatically for RIS devices during main execution.

---

### testPD(sn, service)

**Purpose:**

* Calibrates, reads voltage/power, reboots device, and plots power vs. theta in real-time.

**Socket Role:**

* Acts as a client, connects to a server (measurement PC) to receive theta and send power.

**Steps:**

1. Applies calibration configurations to the device.
2. Performs multiple voltage and power readings.
3. Tests device reboot functionality.
4. Connects to external socket server to fetch theta data in real-time.
5. Launches real-time power plotting UI.
6. Called automatically for PD devices during main execution.

---

## Example Workflow

1. Connect hardware and ensure drivers are installed.
2. Start the main script on the control PC:

   ```sh
   python main.py
   ```
3. Start the measurement client on a separate PC, connecting to the control PC's IP and port.
4. Follow prompts in the terminal for device-specific tests (e.g., enter theta for BBoard, incident angles for RIS).
5. View real-time plots and logs as the tests run.

---

## Logging

* Logs are saved in the `tlk_core_log/` directory.
* Configure logging via `logging.conf` or `logging_abs.conf`.

---

## Troubleshooting

* Ensure all dependencies are installed.
* Check device connections and IP addresses.
* Review logs for error messages.
