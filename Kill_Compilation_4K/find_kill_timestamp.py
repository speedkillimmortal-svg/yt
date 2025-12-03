
import cv2
import easyocr
import sys

def find_first_kill(video_path):
    print(f"Scanning {video_path} for 'ENEMY DOWNED'...")
    reader = easyocr.Reader(['en'])
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print("Error opening video")
        return None

    fps = cap.get(cv2.CAP_PROP_FPS)
    sec = 0.0
    interval = 1.0 # Check every 1 second
    
    while True:
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ret, frame = cap.read()
        if not ret:
            break
            
        h, w = frame.shape[:2]
        # ROI: top-right HUD (same as in compile_kills_1.25x.py)
        x1, x2 = int(w * 0.70), w
        y1, y2 = 0, int(h * 0.30)
        
        region = frame[y1:y2, x1:x2]
        
        # Resize for speed (same as original script)
        region_small = cv2.resize(region, None, fx=0.5, fy=0.5)
        
        try:
            text_list = reader.readtext(region_small, detail=0)
            text = " ".join(text_list).strip().upper()
            
            if "ENEMY DOWNED" in text:
                print(f"FOUND 'ENEMY DOWNED' at {sec} seconds")
                return sec, frame
        except Exception as e:
            pass
            
        sec += interval
        if sec > 600: # Stop after 10 minutes to save time
            print("Scanned 10 minutes, no kill found.")
            break
            
    cap.release()
    return None, None

if __name__ == "__main__":
    video = "input.webm"
    timestamp, frame = find_first_kill(video)
    
    if timestamp is not None:
        # Save the frame for debugging/cropping
        cv2.imwrite("kill_frame.jpg", frame)
        print(f"Saved kill_frame.jpg at {timestamp}s")
        
        # Crop to the text area
        # We need to find the text bounding box more precisely now
        reader = easyocr.Reader(['en'])
        h, w = frame.shape[:2]
        x1, x2 = int(w * 0.70), w
        y1, y2 = 0, int(h * 0.30)
        region = frame[y1:y2, x1:x2]
        
        results = reader.readtext(region)
        for (bbox, text, prob) in results:
            if "ENEMY DOWNED" in text.upper():
                # bbox is [[x1,y1], [x2,y1], [x2,y2], [x1,y2]] relative to region
                # We want to crop this specific area from the region
                (tl, tr, br, bl) = bbox
                tx1 = int(tl[0])
                ty1 = int(tl[1])
                tx2 = int(br[0])
                ty2 = int(br[1])
                
                # Add some padding
                pad = 5
                tx1 = max(0, tx1 - pad)
                ty1 = max(0, ty1 - pad)
                tx2 = min(region.shape[1], tx2 + pad)
                ty2 = min(region.shape[0], ty2 + pad)
                
                template = region[ty1:ty2, tx1:tx2]
                cv2.imwrite("enemy_downed_template.png", template)
                print("Generated enemy_downed_template.png")
                break
