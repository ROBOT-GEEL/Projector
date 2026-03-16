# Projector Control System

An advanced, multi-component service that automates physical projector control using AI-based people counting and the PJLink protocol. It monitors predefined physical zones using a camera and YOLOv8, and triggers projector actions based on occupancy.

## Key Features

* **PJLink Integration:** Reliable control of network projectors (Power ON/OFF, AV Mute/Unmute) with MD5 authentication support.
* **AI People Counting:** Uses YOLOv8 and the `supervision` library to detect people in real-time.
* **Smart Zone Detection:** Maps detections to custom, user-defined polygonal zones (A, B, C).
* **IPC Camera Sharing:** Implements `fcntl` file-locking so the AI script and the Configuration API can safely share a single USB camera without crashing.
* **Kiosk Frontend:** A robust, auto-reconnecting web frontend for status display.

## Project Structure

The system is divided into three main backend services and a frontend interface:

* `projector/projector.py`: TCP socket server that translates incoming text commands (`PROJECTORON`, `PROJECTOROFF`, etc.) to PJLink commands and sends them to the hardware.
* `people-count/people-count.py`: The AI vision module. Captures frames, runs YOLOv8 inference, counts people per zone, and emits data via Socket.IO.
* `zone-configuration/zone-configuration.py`: A Flask REST API to capture camera frames and save zone coordinates to a JSON file.
* `browser/kiosk_master.html`: An auto-reconnecting UI that displays the projector status.

## Prerequisites

* Python 3.10+
* A connected USB Camera or webcam (default `index 0`)
* A network-connected projector supporting the PJLink protocol
* Linux environment (recommended due to `fcntl` usage for IPC locks)

## Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repository-url>
   cd <repository-folder>
   ```

2. **Set up the Virtual Environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration:**
   Copy the example environment file and configure your local settings.
   ```bash
   cp .env.example .env
   ```

## Running the Services

Because this system consists of multiple micro-services, you need to run them in separate terminal instances (or set them up as `systemd` background services). Make sure your virtual environment is activated in each terminal before running the scripts.

**1. Start the Projector Controller:**
```bash
python projector/projector.py
```
*Listens on TCP port 5050 for commands.*

**2. Start the Zone Configuration API:**
```bash
python zone-configuration/zone-configuration.py
```
*Runs on port 5051. Used by the web dashboard to calibrate the A, B, and C zones.*

**3. Start the AI Vision Module:**
```bash
python people-count/people-count.py
```
*Will load the YOLO model, acquire the camera lock, and start emitting Socket.IO events.*

## Kiosk Interface Usage

To use the kiosk dashboard, open the HTML file in a browser and append the server IP and port as a URL hash:
`file:///path/to/browser/kiosk_master.html#SERVER_IP:SERVER_PORT`

The UI will automatically poll the server and display a loading screen if the connection drops.