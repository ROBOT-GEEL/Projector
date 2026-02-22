import socket
import hashlib
import os
import traceback
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
    Sends a PJLink command to the projector with strict error handling.
    Returns a tuple: (success: bool, message: str)
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PROJECTOR_IP, PROJECTOR_PORT))

            # 1. Receive PJLink banner safely
            raw_banner = s.recv(1024)
            if not raw_banner:
                print("Error: Projector connected but immediately dropped without sending a banner.")
                return False, "ERROR: NO_BANNER_RECEIVED"
            
            # Use errors='replace' in case the projector sends unexpected characters
            banner = raw_banner.decode(errors='replace')

            # 2. Handle Authentication
            if "PJLINK" in banner:
                auth_required = banner.startswith("PJLINK 1")
                if auth_required and password:
                    try:
                        rand = banner.split(" ")[2].strip()
                        key = hashlib.md5((rand + password).encode()).hexdigest()
                        command = f"{key}{command}"
                    except IndexError:
                        print("Warning: Could not parse auth nonce from banner. Command may fail.")
                    except Exception as e:
                        print(f"Warning: Authentication hashing error: {e}")
                elif auth_required and not password:
                    return False, "ERROR: AUTH_REQUIRED_BUT_NO_PASSWORD_SET"

            # 3. Send the command safely
            try:
                s.sendall(command.encode())
            except Exception as e:
                print(f"Error: Connection broken while sending command to projector: {e}")
                return False, f"ERROR: SEND_FAILED ({e})"
            
            sleep(0.5)

            # 4. Receive response safely
            try:
                raw_response = s.recv(1024)
                if raw_response:
                    response = raw_response.decode(errors='replace').strip()
                    print(f"Projector Response: {response}")
                    
                    # Check for standard PJLink error codes returned by the projector
                    if "ERR1" in response:
                        return False, "ERROR: PJLINK_ERR1_UNDEFINED_COMMAND"
                    elif "ERR2" in response:
                        return False, "ERROR: PJLINK_ERR2_OUT_OF_PARAMETER"
                    elif "ERR3" in response:
                        return False, "ERROR: PJLINK_ERR3_UNAVAILABLE_TIME"
                    elif "ERR4" in response:
                        return False, "ERROR: PJLINK_ERR4_PROJECTOR_FAILURE"
                    elif "ERRA" in response:
                        return False, "ERROR: PJLINK_ERRA_AUTHENTICATION_FAILURE"
                        
                    return True, "OK"
                else:
                    print("Warning: Projector closed connection without sending a response.")
                    return False, "ERROR: NO_RESPONSE_FROM_PROJECTOR"
            except socket.timeout:
                print("Warning: Projector timed out before responding.")
                return False, "ERROR: RESPONSE_TIMEOUT"
            except Exception as e:
                print(f"Error reading response from projector: {e}")
                return False, f"ERROR: READ_RESPONSE_FAILED ({e})"

    except socket.timeout:
        print(f"Error: Connection to projector ({PROJECTOR_IP}:{PROJECTOR_PORT}) timed out.")
        return False, "ERROR: CONNECTION_TIMEOUT"
    except ConnectionRefusedError:
        print(f"Error: Projector refused connection. It may be offline or already handling a connection.")
        return False, "ERROR: CONNECTION_REFUSED_OFFLINE_OR_BUSY"
    except Exception as e:
        print(f"Error establishing connection to projector: {e}")
        return False, f"ERROR: GENERAL_CONNECTION_ERROR ({e})"


# ========================
# Function: Handle Incoming Commands
# ========================
def handle_command(cmd):
    """
    Matches received text to PJLink commands.
    Returns a tuple: (success: bool, error_message: str)
    """
    try:
        cmd = cmd.strip().upper()

        if cmd == "PROJECTORON":
            print("Turning projector ON...")
            return send_pjlink_command("%1POWR 1\r")

        elif cmd == "PROJECTOROFF":
            print("Turning projector OFF...")
            return send_pjlink_command("%1POWR 0\r")

        elif cmd == "PROJECTORSLEEP":
            print("Muting projector (sleep)...")
            return send_pjlink_command("%1AVMT 31\r")

        elif cmd == "PROJECTORNOTSLEEP":
            print("Unmuting projector (wake)...")
            return send_pjlink_command("%1AVMT 30\r")

        else:
            print(f"Unknown command received: {cmd}")
            return False, "ERROR: UNKNOWN_COMMAND"
            
    except Exception as e:
        print(f"Error parsing or handling command '{cmd}': {e}")
        return False, f"ERROR: INTERNAL_HANDLER_ERROR ({e})"


# ========================
# TCP Server to Listen for Commands
# ========================
def start_command_listener():
    """
    Listens for incoming TCP commands with automatic, quiet reconnections.
    Sends detailed error messages back to the client if the projector fails.
    """
    connection_active = False

    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind((LISTEN_IP, LISTEN_PORT))
                server_socket.listen(5)

                if not connection_active:
                    print(f"Listening for commands on {LISTEN_IP}:{LISTEN_PORT}...")
                    connection_active = True

                while True:
                    try:
                        client_socket, addr = server_socket.accept()
                        with client_socket:
                            client_socket.settimeout(5) # Prevent hanging
                            print(f"Connection from {addr}")
                            
                            try:
                                raw_data = client_socket.recv(1024)
                                
                                # If raw_data is empty, the client closed the connection cleanly
                                if not raw_data:
                                    print(f"Client {addr} disconnected before sending data.")
                                    continue
                                
                                # Use errors='replace' to prevent crashes from non-UTF8 port scanners
                                data = raw_data.decode(errors='replace').strip()
                                
                                if data:
                                    print(f"Received command: {data}")
                                    
                                    # Execute the command and capture success status and specific error message
                                    success, message = handle_command(data)
                                    
                                    try:
                                        # Send the specific outcome back to the client
                                        if success:
                                            client_socket.sendall(b"OK\n")
                                        else:
                                            # Send the detailed error message (e.g., "ERROR: CONNECTION_TIMEOUT\n")
                                            error_response = f"{message}\n".encode()
                                            client_socket.sendall(error_response)
                                    except Exception:
                                        pass # Ignore if client dropped before we could ACK
                                else:
                                    try:
                                        client_socket.sendall(b"ERROR: NO_COMMAND_PROVIDED\n")
                                    except Exception:
                                        pass

                            except socket.timeout:
                                print(f"Client {addr} timed out.")
                            except Exception as e:
                                print(f"Error reading/processing client {addr}: {e}")
                                try:
                                    client_socket.sendall(b"ERROR: CLIENT_COMMUNICATION_ERROR\n")
                                except Exception:
                                    pass # Ignore broken pipe if client is already gone
                                
                    except Exception as e:
                        # Error accepting client (often means the server socket broke)
                        print(f"Socket accept error: {e}")
                        break # Break out to recreate the server socket

        except Exception as e:
            # If the network interface goes down, bind() or listen() will fail
            if connection_active:
                print(f"Network listener error: {e}")
                print("Attempting to reconnect silently every 5 seconds...")
                connection_active = False
            
            # Wait 5 seconds before attempting to bind again
            sleep(5)


# ========================
# Main Entry Point
# ========================
if __name__ == "__main__":
    print("=== Projector Command Listener Started ===")
    print(f"Target Projector: {PROJECTOR_IP}:{PROJECTOR_PORT}")
    
    # Ultimate failsafe wrapper
    while True:
        try:
            start_command_listener()
        except KeyboardInterrupt:
            print("\nShutting down gracefully by user request.")
            break
        except Exception as e:
            print(f"Critical fatal error at top level: {e}")
            print(traceback.format_exc())
            sleep(5)