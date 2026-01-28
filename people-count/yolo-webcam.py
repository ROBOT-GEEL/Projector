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

# Initialize Socket.IO client
sio = socketio.Client()

# -------------------------------------------------------
# CONFIGURATION & CONSTANTS
# -------------------------------------------------------

CONFIG_FILE = "../zone-configuration/zones_config.json"
WARMUP_TIME = 0.05 

# -------------------------------------------------------
# CLI ARGUMENTS
# -------------------------------------------------------
parser = argparse.ArgumentParser()
parser.add_argument("--cam-index", type=int, default=0, help="Camera index (default 0)")
parser.add_argument("--width", type=int, default=3840, help="Camera width")
parser.add_argument("--height", type=int, default=2160, help="Camera height")
parser.add_argument("--model", type=str, default="yolov8n.pt", help="Path to YOLO model")
parser.add_argument("--img-size", type=int, default=2176, help="Inference image size")
parser.add_argument("--server-url", type=str, default="http://192.168.137.199", help="Socket.IO server URL")
parser.add_argument("--debug", action="store_true", help="Run once without server.")
args = parser.parse_args()

# -------------------------------------------------------
# DIRECTORY SETUP & MODEL LOADING
# -------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_DIR = os.path.join(SCRIPT_DIR, 'images/original')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'images/result')
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
    """
    Opens camera, warms up for 0.05s, captures frame, closes camera.
    """
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
    # 1. Capture Frame
    frame = capture_image()
    
    if frame is None:
        print("CRITICAL: No frame captured.")
        # Return empty counts if camera fails
        return {"A": 0, "B": 0, "C": 0}

    cv.imwrite(os.path.join(ORIGINAL_DIR, 'original.jpg'), frame)

    # 2. LOAD ZONES (Real-time reload)
    zones = load_zones(CONFIG_FILE)
    
    # Fallback if there is a problem reading the zones from the config file
    if not zones:
         zone_counts = {"A": 0, "B": 0, "C": 0}
    else:
         zone_counts = {k: 0 for k in zones.keys()}

    # 3. Run Inference
    print(f"[{timestamp}] Running inference...")
    results = model(frame, imgsz=args.img_size, iou=0.2, verbose=False)[0] 
    detections = sv.Detections.from_ultralytics(results)
    detections = detections[(detections.class_id == 0) & (detections.confidence > 0.2)]

    # 4. Process Zones
    annotated_frame = frame.copy()

    for zone_name, polygon in zones.items():
        color = ZONE_COLORS.get(zone_name, (255, 255, 255))
        
        if len(detections) > 0:
            centers = detections.get_anchors_coordinates(anchor=sv.Position.CENTER)
            is_inside = np.array([
                cv.pointPolygonTest(polygon, (float(p[0]), float(p[1])), False) >= 0 
                for p in centers
            ])
            zone_detections = detections[is_inside]
        else:
            zone_detections = []

        count = len(zone_detections)
        zone_counts[zone_name] = count

        # Draw Polygon & Boxes
        cv.polylines(annotated_frame, [polygon.astype(int)], isClosed=True, color=color, thickness=8)

        if len(zone_detections) > 0:
            for i in range(len(zone_detections)):
                x1, y1, x2, y2 = zone_detections.xyxy[i].astype(int)
                conf = zone_detections.confidence[i]
                cv.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3)
                cv.putText(annotated_frame, f'{conf:.2f}', (x1, y1 - 5), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Text positioning logic (safe even if zones change)
        try:
            idx = list(zones.keys()).index(zone_name)
        except ValueError:
            idx = 0
        
        text_x = idx * (args.width // 3) + 50
        cv.putText(annotated_frame, f"Zone {zone_name}: {count}", (text_x, 100), 
                   cv.FONT_HERSHEY_SIMPLEX, 2, color, 6)

    cv.imwrite(os.path.join(RESULTS_DIR, 'result.jpg'), annotated_frame)
    print(f"Counts: {zone_counts}")
    return zone_counts

# -------------------------------------------------------
# SOCKET.IO HANDLERS
# -------------------------------------------------------

@sio.event
def connect():
    print('Connected to Socket.IO server')

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