import cv2 as cv
import numpy as np
import os
import supervision as sv
import socketio
import atexit
import argparse
from datetime import datetime
from ultralytics import YOLO

# Initialize Socket.IO client (Only used if --debug is not set)
sio = socketio.Client()

# -------------------------------------------------------
# CONFIGURATION & SETUP
# -------------------------------------------------------

# CLI Arguments
parser = argparse.ArgumentParser()
parser.add_argument("--cam-index", type=int, default=0, help="Camera index (default 0)")
parser.add_argument("--width", type=int, default=3840, help="Camera width")
parser.add_argument("--height", type=int, default=2160, help="Camera height")
parser.add_argument("--model", type=str, default="yolov8n.pt", help="Path to YOLO model")
parser.add_argument("--img-size", type=int, default=2176, help="Inference image size")
parser.add_argument("--server-url", type=str, default="http://192.168.50.73", help="Socket.IO server URL")
parser.add_argument("--debug", action="store_true", help="Run once without server in a single-shot detection mode.")
args = parser.parse_args()

# Directory Setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_DIR = os.path.join(SCRIPT_DIR, 'images/original')
RESULTS_DIR = os.path.join(SCRIPT_DIR, 'images/result')
os.makedirs(ORIGINAL_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# Load Model
print(f"Loading YOLO model: {args.model}...")
model = YOLO(args.model)

# Zone Definitions (Polygons)
# We use a single dictionary to map Zone Name -> Polygon Coordinates
ZONES = {
    "A": np.array([(512, 1945), (794, 1401), (2188, 1497), (2260, 2022)]),
    "B": np.array([(794, 1401), (1139, 1030), (2240, 1088), (2188, 1497)]),
    "C": np.array([(1139, 1030), (1300, 710), (2150, 774), (2240, 1088)])
}

# Visual Settings
ZONE_COLORS = {
    "A": (0, 0, 255),    # Red
    "B": (0, 255, 0),    # Green
    "C": (255, 0, 0)     # Blue
}

# -------------------------------------------------------
# CAMERA INITIALIZATION
# -------------------------------------------------------

def initialize_camera():
    """Initializes a single camera for all zones."""
    print(f"Opening camera index {args.cam_index}...")
    
    # Use default backend (V4L2 on Linux)
    cap = cv.VideoCapture(args.cam_index) 
    
    if not cap.isOpened():
        raise IOError(f"Cannot open camera with index {args.cam_index}")
    
    # Use the MJPG format to make 4K possible
    cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*'MJPG'))

    # Set resolution
    cap.set(cv.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv.CAP_PROP_BUFFERSIZE, 1)
    
    # Warm up camera
    cv.waitKey(100)
    return cap

# Global camera object
camera = initialize_camera()

# Ensure camera is released on exit
def exit_handler():
    print("Releasing camera...")
    if camera.isOpened():
        camera.release()
    cv.destroyAllWindows()

atexit.register(exit_handler)

# -------------------------------------------------------
# CORE LOGIC
# -------------------------------------------------------

def count_people(timestamp):
    """
    Captures a frame, runs YOLO, counts people per zone, and saves images.
    Returns a dictionary: {'A': count, 'B': count, 'C': count}
    """
    zone_counts = {k: 0 for k in ZONES.keys()}

    # 1. Capture Frame
    # Read twice to clear buffer and get the latest frame
    camera.read() 
    success, frame = camera.read()
    
    if not success:
        print("Error: Failed to read frame from camera.")
        return zone_counts

    # Save original raw image
    cv.imwrite(os.path.join(ORIGINAL_DIR, 'original.jpg'), frame)

    # 2. Run Inference (Once for the whole frame)
    print(f"[{timestamp}] Running inference...")
    # Passing the frame as a list helps ensure the result is a list of results
    results = model(frame, imgsz=args.img_size, iou=0.2, verbose=False)[0] 
    
    # Convert to Supervision detections
    detections = sv.Detections.from_ultralytics(results)
    
    # Filter: Keep only 'person' class (ID 0) with confidence > 0.2
    detections = detections[(detections.class_id == 0) & (detections.confidence > 0.2)]

    # 3. Process Zones & Annotate
    annotated_frame = frame.copy()
    
    # Draw vertical dividers (Visual aid for the 3 sections)
    col_width = args.width // 3
    cv.line(annotated_frame, (col_width, 0), (col_width, args.height), (255, 255, 255), 4)
    cv.line(annotated_frame, (col_width * 2, 0), (col_width * 2, args.height), (255, 255, 255), 4)

    # Loop through each zone to filter detections and draw
    for zone_name, polygon in ZONES.items():
        color = ZONE_COLORS[zone_name]
        
        # Check which detections are inside this zone's polygon
        if len(detections) > 0:
            # Calculate centers of bounding boxes
            centers = detections.get_anchors_coordinates(anchor=sv.Position.CENTER)
            
            # Check if center point is inside polygon
            # cv.pointPolygonTest returns positive if inside, negative if outside
            is_inside = np.array([
                cv.pointPolygonTest(polygon, (float(p[0]), float(p[1])), False) >= 0 
                for p in centers
            ])
            
            zone_detections = detections[is_inside]
        else:
            zone_detections = []

        count = len(zone_detections)
        zone_counts[zone_name] = count

        # Draw Polygon
        cv.polylines(annotated_frame, [polygon.astype(int)], isClosed=True, color=color, thickness=8)

        # Draw Bounding Boxes for people in this zone
        if len(zone_detections) > 0:
            for i in range(len(zone_detections)):
                x1, y1, x2, y2 = zone_detections.xyxy[i].astype(int)
                conf = zone_detections.confidence[i]
                
                # Box
                cv.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3)
                
                # Label
                label = f'{conf:.2f}'
                (w, h), _ = cv.getTextSize(label, cv.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv.rectangle(annotated_frame, (x1, y1 - h - 10), (x1 + w, y1), color, -1)
                cv.putText(annotated_frame, label, (x1, y1 - 5), cv.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Draw Zone Statistics on screen
        zone_idx = list(ZONES.keys()).index(zone_name)
        text_x = zone_idx * col_width + 20
        text_y = 60
        
        cv.putText(annotated_frame, f"Zone {zone_name}", (text_x, text_y), 
                   cv.FONT_HERSHEY_SIMPLEX, 2, color, 6)
        cv.putText(annotated_frame, f"Count: {count}", (text_x, text_y + 80), 
                   cv.FONT_HERSHEY_SIMPLEX, 2, color, 6)

    # 4. Save Result
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
    """
    Triggered by the server. 
    Expects data: {'quizId': x, 'questionId': y}
    """
    print(f"\nReceived event: {data}")
    quiz_id = data.get('quizId')
    question_id = data.get('questionId')
    
    print(f'Starting count for Quiz {quiz_id}, Question {question_id}')
    
    # Perform detection
    counts = count_people(datetime.now())
    
    # Format results as a list [Count A, Count B, Count C]
    results_list = [counts[z] for z in ["A", "B", "C"]]
    data['results'] = results_list
    
    # Send back to server
    print(f"Emitting results: {results_list}")
    sio.emit('count_people_answer', data)

# -------------------------------------------------------
# MAIN EXECUTION
# -------------------------------------------------------

if __name__ == '__main__':
    if args.debug:
        # --- SINGLE DETECTION DEBUG MODE ---
        print("\n" + "="*40)
        print("  DEBUG MODE: Single Detection Activated")
        print("="*40 + "\n")
        
        # Run detection exactly once
        counts = count_people(datetime.now())

        # --- OPEN RESULT IMAGE ---
        result_path = os.path.join(RESULTS_DIR, 'result.jpg')
        print(f"Opening image: {result_path}...")
        
        # Open the result image
        os.system(f'xdg-open "{result_path}"')
            
    else:
        # --- NORMAL SERVER CONNECTION MODE ---
        print(f'Attempting to connect to {args.server_url}...')
        try:
            sio.connect(args.server_url, retry=True)
            sio.wait() # Keep script running
        except Exception as e:
            print(f"Connection failed: {e}")
            exit_handler()