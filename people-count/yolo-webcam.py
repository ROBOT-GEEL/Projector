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
from pathlib import Path
from dotenv import load_dotenv

# Initialize Socket.IO client
sio = socketio.Client()

# -------------------------------------------------------
# CONFIGURATION & CONSTANTS
# -------------------------------------------------------

CONFIG_FILE = "/home/projector/Documents/zone-configuration/zones_config.json"
WARMUP_TIME = 0.05 

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

# add 'http://' to the server ip 
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
os.makedirs(ORIGINAL_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

print(f"Loading YOLO model: {args.model}...")
model = YOLO(args.model)

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
    """
    Reads the JSON file and converts coordinate lists 
    into a dictionary of NumPy arrays suitable for OpenCV.
    """
    if not os.path.exists(file_path):
        print(f"ERROR: File '{file_path}' not found. Using empty zones.")
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
        print(f"ERROR loading zones: {e}")
        return {}

# -------------------------------------------------------
# CAMERA
# -------------------------------------------------------

def capture_image():
    with camera_lock:
        print("Camera: Opening...")
        try:
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
            cap.release()
            print("Camera: Closed.")

            if success:
                return frame
            else:
                print("Error: Failed to read frame.")
                return None
            
        except Exception as e:
            print(f"Camera Exception: {e}")
            if 'cap' in locals() and cap.isOpened():
                cap.release()
            return None
        
# -------------------------------------------------------
# CORE LOGIC   
# -------------------------------------------------------

def count_people(timestamp):
    frame = capture_image()
    
    if frame is None:
        return {"A": 0, "B": 0, "C": 0}

    cv.imwrite(os.path.join(ORIGINAL_DIR, 'original.jpg'), frame)

    zones = load_zones(CONFIG_FILE)
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
        cv.polylines(annotated_frame, [polygon.astype(int)], True, color, 8)
        
        if len(zone_detections) > 0:
            for i in range(len(zone_detections)):
                x1, y1, x2, y2 = zone_detections.xyxy[i].astype(int)
                cv.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3)

    cv.imwrite(os.path.join(RESULTS_DIR, 'result.jpg'), annotated_frame)
    return zone_counts

# -------------------------------------------------------
# SOCKET.IO HANDLERS
# -------------------------------------------------------

@sio.event
def connect():
    print(f'Connected to server at {args.server_url}')

@sio.event
def disconnect():
    print('Disconnected from server')

@sio.event
def count_people_event(data):
    print(f"\n--- EVENT RECEIVED: {data} ---")
    counts = count_people(datetime.now())
    results_list = [counts.get(z, 0) for z in ["A", "B", "C"]]
    data['results'] = results_list
    print(f"Emitting results: {results_list}")
    sio.emit('count_people_answer', data)

# -------------------------------------------------------
# MAIN EXECUTION
# -------------------------------------------------------

if __name__ == '__main__':
    if args.debug:
        print("\n=== DEBUG MODE ===")
        print(f"Using server URL: {args.server_url}")
        count_people(datetime.now())
        try:
            os.system(f'xdg-open "{os.path.join(RESULTS_DIR, "result.jpg")}"') 
        except:
            pass
    else:
        print(f'Attempting to connect to {args.server_url}...')
        try:
            sio.connect(args.server_url, retry=True)
            sio.wait()
        except Exception as e:
            print(f"Connection failed: {e}")