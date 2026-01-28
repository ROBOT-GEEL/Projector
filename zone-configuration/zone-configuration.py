from flask import Flask, send_file, request, jsonify # type: ignore
import time
import cv2
import json

app = Flask(__name__)

FILE_NAME = "zone_image.jpg"

@app.route('/take_picture')
def take_picture():
    # Define the 4K resolution
    WIDTH_4K = 3840
    HEIGHT_4K = 2160

    cap = cv2.VideoCapture(0)

    # Set the resolution
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH_4K)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT_4K)

    if not cap.isOpened():
        print("ERROR: could not find the camera, exiting...")
        exit()
    pass 

    ret, frame = cap.read()

    if not ret:
        print("ERROR: could not fetch the frame, exiting...")
        exit()

    status = cv2.imwrite(FILE_NAME, frame)

    if status:
        print("Foto succesvol opgeslagen!")
    else:
        print("Fout bij het opslaan van de foto.")

    # Send the file to the browser
    return send_file(FILE_NAME, mimetype='image/jpeg')


@app.route('/save_zones', methods=['POST'])
def save_zones():
    data = request.json  # The data that we need to store
    
    print(f"Ontvangen zones: {data}")
    
    # Save the file
    with open('zones_config.json', 'w') as f:
        json.dump(data, f)

    # Return succes
    return jsonify({"status": "success", "message": "Zones ontvangen"})
    
    

if __name__ == '__main__':
    # Listen on port 5000
    app.run(host='0.0.0.0', port=5000)