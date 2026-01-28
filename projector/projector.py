import socket
import hashlib
from time import sleep

# ========================
# Projector Configuration
# ========================
PROJECTOR_IP = "192.168.138.100"
PROJECTOR_PORT = 4352  # PJLink default port
PJLINK_PASSWORD = "1234"  # Set your PJLink password here

# ========================
# Command Listener Config
# ========================
LISTEN_HOST = "0.0.0.0"   # Listen on all interfaces
LISTEN_PORT = 5050        # Port where this script listens for commands


# ========================
# Function: Send PJLink Command
# ========================
def send_pjlink_command(command, password=PJLINK_PASSWORD):
    """
    Sends a PJLink command to the projector.
    PJLink requires a %1 prefix and ends with \r.
    Handles authentication if required.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PROJECTOR_IP, PROJECTOR_PORT))

            # Receive PJLink banner
            banner = s.recv(1024).decode()

            if "PJLINK" in banner:
                # Check if authentication is required
                auth_required = banner.startswith("PJLINK 1")

                if auth_required and password:
                    # Extract random number from banner
                    rand = banner.split(" ")[2].strip()
                    key = hashlib.md5((rand + password).encode()).hexdigest()
                    command = f"{key}{command}"

            # Send the command
            s.sendall(command.encode())
            sleep(0.5)

            # Receive and print response
            response = s.recv(1024).decode()
            print(f"Response: {response}")

    except Exception as e:
        print(f"Error sending PJLink command: {e}")


# ========================
# Function: Handle Incoming Commands
# ========================
def handle_command(cmd):
    """
    Takes a received command string and sends the matching PJLink command.
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
    Listens on LISTEN_PORT for incoming text commands like PROJECTORON, PROJECTOROFF, etc.
    """
    print(f"Listening for commands on {LISTEN_HOST}:{LISTEN_PORT}...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind((LISTEN_HOST, LISTEN_PORT))
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
    start_command_listener()


