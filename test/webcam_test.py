import cv2

# Define the 4K resolution
WIDTH_4K = 3840
HEIGHT_4K = 2160

cap = cv2.VideoCapture(0)

# Set the resolution
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH_4K)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT_4K)

# Check the actual resolution
actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

print(f"Resolution: {int(actual_width)}x{int(actual_height)} pixels, press 'q' to quit.")

if not cap.isOpened():
    print("ERROR: could not find the camera, exiting...")
    exit()

# Show the camera feed, WINDOW_NORMAL makes the viewing window rescalable
NAME_WINDOW = '4K Camera Feed'
cv2.namedWindow(NAME_WINDOW, cv2.WINDOW_NORMAL)

while True:
    # Read the frame
    ret, frame = cap.read()

    if not ret:
        print("ERROR: could not fetch the frame, exiting...")
        break

    # Show the frame in the above defined window
    cv2.imshow(NAME_WINDOW, frame)

    # Exit if 'q' is pressed
    if cv2.waitKey(1) == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
