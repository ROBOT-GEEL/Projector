import cv2 as cv
import time

def vind_maximale_resolutie_mjpg(camera_index=0):
    """
    Test systematisch bekende hoge resoluties, nu met geforceerde MJPG-codec.
    """
    
    # Lijst van hoge resoluties (Breedte, Hoogte) - aflopend
    resoluties_om_te_testen = [
        (3840, 2160),  # 4K / UHD
        (2560, 1440),  # QHD
        (1920, 1080),  # Full HD
        (1280, 720)    # HD
    ]
    
    gevonden_resolutie = None

    print(f"Start 4K-test voor camera index {camera_index} (met MJPG)...")

    for w, h in resoluties_om_te_testen:
        print(f"  -> Testen van {w}x{h}...")
        
        cap = cv.VideoCapture(camera_index)
        
        if not cap.isOpened():
            print(f"Fout: Kan camera met index {camera_index} niet openen.")
            return

        # STAP 1: Stel de MJPG-codec in (CRUCIAAL)
        cap.set(cv.CAP_PROP_FOURCC, cv.VideoWriter_fourcc(*'MJPG'))
        
        # STAP 2: Probeer de resolutie in te stellen
        cap.set(cv.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv.CAP_PROP_FRAME_HEIGHT, h)
        
        time.sleep(0.1)

        # STAP 3: Lees de werkelijke ingestelde resolutie terug
        werkelijke_w = int(cap.get(cv.CAP_PROP_FRAME_WIDTH))
        werkelijke_h = int(cap.get(cv.CAP_PROP_FRAME_HEIGHT))
        
        cap.release()
        
        # Controleer of de werkelijke resolutie dicht bij de gewenste resolutie ligt.
        if abs(werkelijke_w - w) <= 5 and abs(werkelijke_h - h) <= 5:
            gevonden_resolutie = (werkelijke_w, werkelijke_h)
            break
        
    print("\n" + "="*60)
    if gevonden_resolutie:
        print(f"🎉 De Maximale Resolutie (met MJPG) is: {gevonden_resolutie[0]}x{gevonden_resolutie[1]}")
    else:
        print("❌ De camera accepteert 4K niet, zelfs niet met geforceerde MJPG. De max is waarschijnlijk 1920x1080.")
    print("="*60)


if __name__ == "__main__":
    vind_maximale_resolutie_mjpg(camera_index=0)
