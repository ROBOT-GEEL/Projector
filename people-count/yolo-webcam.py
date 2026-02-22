import cv2 as cv
import numpy as np
import os
import supervision as sv
import socketio
import argparse
from datetime import datetime
from ultralytics import YOLO
import json
import threading
import time
import traceback
from pathlib import Path
from dotenv import load_dotenv
import fcntl

# Initialize Socket.IO client
sio = socketio.Client(reconnection=False)

# -------------------------------------------------------
# CONFIGURATION & CONSTANTS
# -------------------------------------------------------

CONFIG_FILE = "/home/projector/Documents/zone-configuration/zones_config.json"
WARMUP_TIME = 0.05 
RETRY_DELAY = 5 # seconds between connection attempts when server is down

# -------------------------------------------------------
# LOAD ENV FILE
# -------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
env_path = SCRIPT_DIR.parent / '.env'
load_dotenv(dotenv_path=env_path)

# -------------------------------------------------------
# CLI ARGUMENTS
# -------------------------------------------------------

DEFAULT_SERVER = os.getenv('SERVER_IP', '192.168.137.100')

if DEFAULT_SERVER and not DEFAULT_SERVER.startswith('http'):
    DEFAULT_SERVER = f"http://{DEFAULT_SERVER}"

parser = argparse.ArgumentParser()
parser.add_argument("--cam-index", type=int, default=0, help="Camera index (default 0)")
parser.add_argument("--width", type=int, default=3840, help="Camera width")
parser.add_argument("--height", type=int, default=2160, help="Camera height")
parser.add_argument("--model", type=str, default="yolov8n.pt", help="Path to YOLO model")
parser.add_argument("--img-size", type=int, default=2176, help="Inference image size")
parser.add_argument("--server-url", type=str, default=DEFAULT_SERVER, help="Socket.IO server URL")
parser.add_argument("--debug", action="store_true", help="Run once without server.")
args = parser.parse_args()

# -------------------------------------------------------
# DIRECTORY SETUP & MODEL LOADING
# -------------------------------------------------------
ORIGINAL_DIR = os.path.join(str(SCRIPT_DIR), 'images/original')
RESULTS_DIR = os.path.join(str(SCRIPT_DIR), 'images/result')

# Wrap directory creation in try-except in case of permission/disk issues
try:
    os.makedirs(ORIGINAL_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)
except Exception as e:
    print(f"CRITICAL WARNING: Could not create directories. Images will not be saved. {e}")

print(f"Loading YOLO model: {args.model}...")
try:
    model = YOLO(args.model)
except Exception as e:
    print(f"FATAL ERROR: Failed to load YOLO model. Check path and memory. {e}")
    exit(1) # Only acceptable exit if the core AI model is completely missing/corrupt

camera_lock = threading.Lock()

ZONE_COLORS = {
    "A": (0, 0, 255),    # Red
    "B": (0, 255, 0),    # Green
    "C": (255, 0, 0)     # Blue
}

# -------------------------------------------------------
# ZONE LOADING
# -------------------------------------------------------
def load_zones(file_path):
    if not os.path.exists(file_path):
        print(f"WARNING: File '{file_path}' not found. Using empty zones.")
        return {}
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        zones_dict = {}
        for zone_name, points_list in data.items():
            coordinates = [[p['x'], p['y']] for p in points_list]
            zones_dict[zone_name] = np.array(coordinates, dtype=np.int32)
        return zones_dict
    except Exception as e:
        print(f"ERROR loading zones from JSON: {e}")
        return {}

# -------------------------------------------------------
# CAMERA
# -------------------------------------------------------
def capture_image():
    with camera_lock: 
        lock_file_path = f"/tmp/camera_{args.cam_index}.lock"
        lock_fd = None
        cap = None
        
        try:
            # 1. Open a lock file specific to this camera index
            lock_fd = open(lock_file_path, 'w')
            
            # 2. Acquire an exclusive lock. 
            # If another script holds it, THIS script will pause here and wait.
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            print("Camera: IPC Lock acquired. Opening...")
            
            cap = cv.VideoCapture(args.cam_index)
            if not cap.isOpened():
                print(f"Error: Cannot open camera {args.cam_index}")
                return None
            
            cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv.CAP_PROP_FRAME_WIDTH, args.width)
            cap.set(cv.CAP_PROP_FRAME_HEIGHT, args.height)
            cap.set(cv.CAP_PROP_BUFFERSIZE, 1)

            time.sleep(WARMUP_TIME)
            success, frame = cap.read()
            
            if success:
                return frame
            else:
                print("Error: Failed to read frame.")
                return None
            
        except Exception as e:
            print(f"Camera/Lock Exception: {e}")
            return None
            
        finally:
            # 3. Always release hardware first
            if cap is not None and cap.isOpened():
                try:
                    cap.release()
                    print("Camera: Closed.")
                except Exception as e:
                    print(f"Error releasing camera: {e}")
            
            # 4. Always release the IPC lock last
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                    lock_fd.close()
                    print("Camera: IPC Lock released.")
                except Exception as e:
                    print(f"Error releasing file lock: {e}")
        
# -------------------------------------------------------
# CORE LOGIC   
# -------------------------------------------------------
def count_people(timestamp):
    # Default safe fallback
    zone_counts = {"A": 0, "B": 0, "C": 0}
    
    try:
        frame = capture_image()
        if frame is None:
            return zone_counts

        # Safe file writing
        try:
            cv.imwrite(os.path.join(ORIGINAL_DIR, 'original.jpg'), frame)
        except Exception as e:
            print(f"Warning: Could not save original frame: {e}")

        zones = load_zones(CONFIG_FILE)
        # Update zone counts dictionary dynamically based on actual zones
        zone_counts = {k: 0 for k in (zones.keys() if zones else ["A", "B", "C"])}
        
        results = model(frame, imgsz=args.img_size, iou=0.2, verbose=False)[0] 
        detections = sv.Detections.from_ultralytics(results)
        detections = detections[(detections.class_id == 0) & (detections.confidence > 0.2)]

        annotated_frame = frame.copy()
        for zone_name, polygon in zones.items():
            color = ZONE_COLORS.get(zone_name, (255, 255, 255))
            if len(detections) > 0:
                centers = detections.get_anchors_coordinates(anchor=sv.Position.CENTER)
                is_inside = np.array([cv.pointPolygonTest(polygon, (float(p[0]), float(p[1])), False) >= 0 for p in centers])
                zone_detections = detections[is_inside]
            else:
                zone_detections = []
            
            count = len(zone_detections)
            zone_counts[zone_name] = count
            
            # Safe drawing
            try:
                cv.polylines(annotated_frame, [polygon.astype(int)], True, color, 8)
                if len(zone_detections) > 0:
                    for i in range(len(zone_detections)):
                        x1, y1, x2, y2 = zone_detections.xyxy[i].astype(int)
                        cv.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3)
            except Exception as e:
                 print(f"Warning: Error during frame annotation: {e}")

        # Safe file writing
        try:
            cv.imwrite(os.path.join(RESULTS_DIR, 'result.jpg'), annotated_frame)
        except Exception as e:
            print(f"Warning: Could not save result frame: {e}")

    except Exception as e:
        print(f"ERROR in count_people core logic: {e}")
        traceback.print_exc() # Print full stack trace for debugging without crashing
        
    return zone_counts

# -------------------------------------------------------
# SOCKET.IO HANDLERS
# -------------------------------------------------------

@sio.event
def connect(): # This is handled by the main loop to print connection status, so we can leave it empty here.
    pass

@sio.event
def disconnect():
    pass

@sio.event
def count_people_event(data):
    # Entire event must be wrapped to prevent background thread crashes
    try:
        print(f"\n--- EVENT RECEIVED: {data} ---")
        counts = count_people(datetime.now())
        results_list = [counts.get(z, 0) for z in ["A", "B", "C"]]
        data['results'] = results_list
        print(f"Emitting results: {results_list}")
        sio.emit('count_people_answer', data)
    except Exception as e:
        print(f"ERROR in count_people_event: {e}")
        # Always attempt to emit back an empty response so the server doesn't hang waiting
        try:
            data['results'] = [0, 0, 0]
            sio.emit('count_people_answer', data)
        except Exception as emit_err:
            print(f"Failed to emit fallback answer: {emit_err}")

# -------------------------------------------------------
# MAIN EXECUTION
# -------------------------------------------------------

if __name__ == '__main__':
    if args.debug:
        print("\n=== DEBUG MODE ===", flush=True)
        print(f"Using server URL: {args.server_url}", flush=True)
        count_people(datetime.now()) # You can safely remove datetime.now() if you remove the parameter
        try:
            os.system(f'xdg-open "{os.path.join(RESULTS_DIR, "result.jpg")}"') 
        except:
            pass
    else:
        is_first_failure = True
        
        while True:
            # Only announce the attempt if we aren't already in a silent failure loop
            if is_first_failure:
                print(f'Attempting to connect to {args.server_url}...', flush=True)
                
            try:
                sio.connect(args.server_url)
                print(f'Connection successful ({args.server_url})', flush=True)
                
                # Reset the flag because we are connected. 
                is_first_failure = True 
                
                # Because reconnection=False, this will exit immediately if the server drops
                sio.wait() 
                
                # If we reach this exact line, sio.wait() finished naturally (server dropped)
                if is_first_failure:
                    print("Disconnected from server. Retrying...", flush=True)
                    print(f"Network down. Retrying silently every {RETRY_DELAY} seconds...", flush=True)
                    is_first_failure = False
                    
            except Exception as e:
                # Catch connection failures (e.g., server offline)
                if is_first_failure:
                    print(f"Socket connection error: {e}", flush=True)
                    print(f"Network down. Retrying silently every {RETRY_DELAY} seconds...", flush=True)
                    is_first_failure = False
                    
            finally:
                # CRITICAL: Always forcefully clear the internal client state. 
                # This prevents zombie threads and "already connected" exceptions on the next loop.
                try:
                    sio.disconnect()
                except:
                    pass
            
            # Sleep for exactly 5 seconds before looping back up to try again
            time.sleep(RETRY_DELAY)