from flask import Flask, send_file, request, jsonify
import time
import cv2
import json
import os
import fcntl
import traceback
from pathlib import Path
from dotenv import load_dotenv

# -------------------------------------------------------
# PATH CONFIGURATION (RELATIVE TO SCRIPT)
# -------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR.parent / ".env"
ZONE_IMAGE = SCRIPT_DIR / "zone_image.jpg"
CONFIG_FILE = SCRIPT_DIR / "zones_config.json"

# Load the .env file safely
try:
    load_dotenv(dotenv_path=ENV_PATH)
except Exception as e:
    print(f"Warning: Could not load .env file: {e}")

app = Flask(__name__)
PORT = int(os.getenv('ZONE_CONFIG_PORT', 5051))

# -------------------------------------------------------
# GLOBAL ERROR HANDLER
# -------------------------------------------------------
@app.errorhandler(Exception)
def handle_exception(e):
    """Catches absolutely any error that escapes the routes so the server never crashes."""
    print(f"CRITICAL FLASK ERROR: {e}")
    traceback.print_exc()
    return jsonify({"status": "error", "message": "Internal server error"}), 500

# -------------------------------------------------------
# ROUTES
# -------------------------------------------------------

@app.route('/take_picture')
def take_picture():
    WIDTH_4K = 3840
    HEIGHT_4K = 2160
    lock_file_path = "/tmp/camera_0.lock"
    lock_fd = None
    cap = None

    try:
        # 1. Acquire the IPC hardware lock
        try:
            lock_fd = open(lock_file_path, 'w')
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            print("Flask: IPC Lock acquired. Opening camera...")
        except Exception as e:
            print(f"ERROR: Could not acquire camera lock: {e}")
            return jsonify({"status": "error", "message": "Camera is busy or locked"}), 503

        # 2. Open Camera
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH_4K)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT_4K)

        if not cap.isOpened():
            print("ERROR: could not find the camera.")
            return jsonify({"status": "error", "message": "Could not find camera"}), 500

        time.sleep(0.05) # Warmup
        ret, frame = cap.read()

        if not ret or frame is None:
            print("ERROR: could not fetch the frame.")
            return jsonify({"status": "error", "message": "Could not fetch frame"}), 500

        # 3. Save Image Safely
        status = cv2.imwrite(str(ZONE_IMAGE), frame)
        if not status:
            print("Fout bij het opslaan van de foto.")
            return jsonify({"status": "error", "message": "Failed to write image to disk"}), 500

        # 4. Verify file actually exists before sending
        if not ZONE_IMAGE.exists():
            print("ERROR: File reports saved, but cannot be found on disk.")
            return jsonify({"status": "error", "message": "File missing after save"}), 500

        print("Image saved and sent!")
        return send_file(str(ZONE_IMAGE), mimetype='image/jpeg')

    except Exception as e:
        print(f"Unexpected error in /take_picture: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    finally:
        # 5. Guaranteed Cleanup (Runs even if a return statement was triggered above)
        if cap is not None and cap.isOpened():
            try:
                cap.release()
                print("Flask: Camera closed.")
            except Exception as e:
                print(f"Error closing camera: {e}")
            
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
                print("Flask: IPC Lock released.")
            except Exception as e:
                print(f"Error releasing IPC lock: {e}")


@app.route('/save_zones', methods=['POST'])
def save_zones():
    try:
        # silent=True prevents Flask from crashing if the incoming data isn't valid JSON
        data = request.get_json(silent=True) 
        
        if data is None:
            print("ERROR: Received invalid or empty JSON.")
            return jsonify({"status": "error", "message": "Invalid JSON payload"}), 400
            
        print(f"Ontvangen zones: {data}")
        
        # Save the file safely
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)
            
        return jsonify({"status": "success", "message": "Zones ontvangen"})
        
    except PermissionError:
        print("ERROR: Permission denied when writing zones_config.json")
        return jsonify({"status": "error", "message": "Permission denied writing config"}), 500
    except Exception as e:
        print(f"Error saving zones: {e}")
        return jsonify({"status": "error", "message": "Could not save zones"}), 500
    

# -------------------------------------------------------
# MAIN EXECUTION
# -------------------------------------------------------
if __name__ == '__main__':
    # Infinite loop to keep the server alive no matter what happens
    while True:
        try:
            print(f"Server gestart op poort {PORT}")
            # Run the Flask app
            app.run(host='0.0.0.0', port=PORT)
        except Exception as e:
            print(f"CRITICAL: Flask server crashed entirely: {e}")
            print("Restarting server in 5 seconds...")
            time.sleep(5)