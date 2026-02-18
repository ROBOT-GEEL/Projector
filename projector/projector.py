import socket
import hashlib
import os
from time import sleep
from pathlib import Path
from dotenv import load_dotenv

# ========================
# Projector Configuration
# ========================

SCRIPT_DIR = Path(__file__).resolve().parent
env_path = SCRIPT_DIR.parent / '.env'
load_dotenv(dotenv_path=env_path)

PROJECTOR_IP = os.getenv('PROJECTOR_IP', "192.168.138.100")
PROJECTOR_PORT = int(os.getenv('PROJECTOR_PORT', 4352))
PJLINK_PASSWORD = os.getenv('PJLINK_PASSWORD')

# ========================
# Command Listener Config
# ========================

LISTEN_IP = "0.0.0.0" 
LISTEN_PORT = int(os.getenv('LISTEN_PORT', 5050))

# ========================
# Function: Send PJLink Command
# ========================
def send_pjlink_command(command, password=PJLINK_PASSWORD):
    """
    Sends a PJLink command to the projector.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PROJECTOR_IP, PROJECTOR_PORT))

            # Receive PJLink banner
            banner = s.recv(1024).decode()

            if "PJLINK" in banner:
                # Check if authentication is required (PJLINK 1 indicates auth)
                auth_required = banner.startswith("PJLINK 1")

                if auth_required and password:
                    # Extract random number (nonce) from banner for MD5 hash
                    try:
                        rand = banner.split(" ")[2].strip()
                        key = hashlib.md5((rand + password).encode()).hexdigest()
                        command = f"{key}{command}"
                    except IndexError:
                        print("Warning: Could not parse auth nonce from banner.")

            # Send the command
            s.sendall(command.encode())
            sleep(0.5)

            # Receive and print response
            response = s.recv(1024).decode()
            print(f"Projector Response: {response.strip()}")

    except Exception as e:
        print(f"Error sending PJLink command: {e}")


# ========================
# Function: Handle Incoming Commands
# ========================
def handle_command(cmd):
    """
    Matches received text to PJLink commands.
    """
    cmd = cmd.strip().upper()

    if cmd == "PROJECTORON":
        print("Turning projector ON...")
        send_pjlink_command("%1POWR 1\r")

    elif cmd == "PROJECTOROFF":
        print("Turning projector OFF...")
        send_pjlink_command("%1POWR 0\r")

    elif cmd == "PROJECTORSLEEP":
        print("Muting projector (sleep)...")
        send_pjlink_command("%1AVMT 31\r")

    elif cmd == "PROJECTORNOTSLEEP":
        print("Unmuting projector (wake)...")
        send_pjlink_command("%1AVMT 30\r")

    else:
        print(f"Unknown command received: {cmd}")


# ========================
# TCP Server to Listen for Commands
# ========================
def start_command_listener():
    """
    Listens for incoming TCP commands.
    """
    print(f"Listening for commands on {LISTEN_IP}:{LISTEN_PORT}...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((LISTEN_IP, LISTEN_PORT))
        server_socket.listen(5)

        while True:
            client_socket, addr = server_socket.accept()
            with client_socket:
                print(f"Connection from {addr}")
                try:
                    data = client_socket.recv(1024).decode().strip()
                    if data:
                        print(f"Received command: {data}")
                        handle_command(data)
                        client_socket.sendall(b"OK\n")
                    else:
                        client_socket.sendall(b"NO COMMAND\n")
                except Exception as e:
                    print(f"Error handling client {addr}: {e}")
                    client_socket.sendall(b"ERROR\n")


# ========================
# Main Entry Point
# ========================
if __name__ == "__main__":
    print("=== Projector Command Listener Started ===")
    print(f"Target Projector: {PROJECTOR_IP}:{PROJECTOR_PORT}")
    start_command_listener()