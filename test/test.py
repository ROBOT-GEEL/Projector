import cv2
import time

def test_camera_warmup():
    print("Camera openen...")
    cap = cv2.VideoCapture(0)

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))

    # Set resolution
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        print("ERROR: Kan camera niet vinden.")
        return

    # --- FOTO 1: DIRECT (Koud) ---
    print("Directe foto nemen...")
    ret, frame_direct = cap.read()
    
    if ret:
        cv2.imwrite("1_direct_koud.jpg", frame_direct)
        print(" -> '1_direct_koud.jpg' opgeslagen.")
    else:
        print("Fout bij lezen frame 1.")

    # --- WACHTEN (Warmup) ---
    print("0.1 seconden wachten op auto-exposure/witbalans...")
    time.sleep(0.05)

    # Tip: Soms zit er nog een oud frame in de buffer. 
    # We lezen 1x een 'dummy' frame om de buffer te legen voor de zekerheid.
    cap.grab() 

    # --- FOTO 2: NA WACHTEN (Opwarmd) ---
    print("Tweede foto nemen...")
    ret, frame_warm = cap.read()

    if ret:
        cv2.imwrite("2_na_wachten.jpg", frame_warm)
        print(" -> '2_na_wachten.jpg' opgeslagen.")
    else:
        print("Fout bij lezen frame 2.")

    # Opruimen
    cap.release()
    print("Klaar! Vergelijk de twee afbeeldingen.")

if __name__ == "__main__":
    test_camera_warmup()