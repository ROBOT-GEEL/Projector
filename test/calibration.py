import tkinter as tk
from tkinter import messagebox
import cv2
import time
from PIL import Image, ImageTk
import os
import math

# Define the 4K resolution (Source)
WIDTH_4K = 3840
HEIGHT_4K = 2160

# Define the Preview resolution (Display only)
# This fits nicely on most laptop/desktop screens
PREVIEW_WIDTH = 1280
PREVIEW_HEIGHT = 720

class ZoneSelectorApp:
    def __init__(self, window, window_title):
        self.window = window
        self.window.title(window_title)

        # Application State
        self.mode = "edit" 
        self.current_zone = 'A'
        self.current_image = None # Stores the FULL RES captured cv2 image
        self.photo = None # Stores the RESIZED PhotoImage for canvas
        
        # Calculate scaling factors
        self.scale_x = WIDTH_4K / PREVIEW_WIDTH
        self.scale_y = HEIGHT_4K / PREVIEW_HEIGHT
        
        # Store points: {'A': [(x,y), ...], 'B': [], 'C': []}
        # These points will always be stored in 4K RESOLUTION
        self.zones = {'A': [], 'B': [], 'C': []}
        
        # Colors for the zones for visual distinction
        self.zone_colors = {'A': "red", 'B': "green", 'C': "blue"}

        # GUI Layout
        self.top_frame = tk.Frame(window)
        self.top_frame.pack(pady=10)

        # Canvas for displaying image and drawing
        # We set the canvas to the PREVIEW size, not 4K
        self.canvas = tk.Canvas(self.top_frame, width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT, bg="black")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_canvas_click)

        # Bottom control frame
        self.bottom_frame = tk.Frame(window)
        self.bottom_frame.pack(pady=10, fill=tk.X)

        # Zone Selection Buttons Frame
        self.zone_btn_frame = tk.Frame(self.bottom_frame)
        self.zone_btn_frame.pack(pady=5)

        self.btn_zoneA = tk.Button(self.zone_btn_frame, text="Zone A (Red)", command=lambda: self.select_zone('A'), width=15)
        self.btn_zoneA.grid(row=0, column=0, padx=5)
        
        self.btn_zoneB = tk.Button(self.zone_btn_frame, text="Zone B (Green)", command=lambda: self.select_zone('B'), width=15)
        self.btn_zoneB.grid(row=0, column=1, padx=5)

        self.btn_zoneC = tk.Button(self.zone_btn_frame, text="Zone C (Blue)", command=lambda: self.select_zone('C'), width=15)
        self.btn_zoneC.grid(row=0, column=2, padx=5)

        # Utility Buttons
        self.util_btn_frame = tk.Frame(self.bottom_frame)
        self.util_btn_frame.pack(pady=10)

        self.btn_clear_zone = tk.Button(self.util_btn_frame, text="Clear Current Zone", command=self.clear_current_zone)
        self.btn_clear_zone.pack(side=tk.LEFT, padx=10)

        self.btn_save = tk.Button(self.util_btn_frame, text="Save Coordinates", command=self.save_coordinates, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
        self.btn_save.pack(side=tk.LEFT, padx=10)
        
        self.btn_reset = tk.Button(self.util_btn_frame, text="Retake Photo", command=self.reset_app)
        self.btn_reset.pack(side=tk.LEFT, padx=10)

        # Status Label
        self.status_label = tk.Label(window, text="Status: Starting camera...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Start by taking a picture immediately
        self.window.after(100, self.capture_image)
        self.update_button_styles()

    def capture_image(self):
        """ Capture a single frame from the camera immediately """
        self.status_label.config(text="Status: Waking up camera (please wait)...")
        self.window.update()

        # Try to open camera
        cap = cv2.VideoCapture(0)

        # Force MJPG and 4K resolution
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH_4K)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT_4K)
        
        if not cap.isOpened():
            messagebox.showerror("Error", "Could not open camera.")
            return

        # Sleep to allow camera sensor to power up
        time.sleep(2)

        # Warmup frames
        for _ in range(30):
            cap.read()
            
        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            self.current_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.mode = "edit"
            self.redraw_canvas()
            self.status_label.config(text="Image Captured. Select a Zone button and click 4 points.")
        else:
            messagebox.showerror("Error", "Could not read frame from camera. (Try checking lighting or USB connection)")

    def redraw_canvas(self):
        """ Draws the frozen image and overlays the zone graphics """
        if self.current_image is None:
            return

        # 1. Resize the 4K image to Preview size for display
        img_pil = Image.fromarray(self.current_image)
        img_resized = img_pil.resize((PREVIEW_WIDTH, PREVIEW_HEIGHT), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(image=img_resized)

        # 2. Draw the image
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

        # 3. Draw Zones (We must scale points DOWN to fit the preview)
        for zone_id, points in self.zones.items():
            color = self.zone_colors[zone_id]
            
            # Convert 4K points to Preview points for drawing
            display_points = []
            for p in points:
                dp_x = int(p[0] / self.scale_x)
                dp_y = int(p[1] / self.scale_y)
                display_points.append((dp_x, dp_y))
            
            # Draw points (circles)
            for dp in display_points:
                r = 4 
                self.canvas.create_oval(dp[0]-r, dp[1]-r, dp[0]+r, dp[1]+r, fill=color, outline="white")

            # Draw lines
            if len(display_points) > 1:
                self.canvas.create_line(display_points, fill=color, width=2)
            
            # Close the loop
            if len(display_points) == 4:
                self.canvas.create_line(display_points[-1], display_points[0], fill=color, width=2)

    def select_zone(self, zone_id):
        """ Change the active drawing zone """
        if self.mode != "edit":
            messagebox.showwarning("Warning", "Please Capture an image first.")
            return

        self.current_zone = zone_id
        self.update_button_styles()
        self.status_label.config(text=f"Selected Zone {zone_id}. Points: {len(self.zones[zone_id])}/4")

    def update_button_styles(self):
        btns = {'A': self.btn_zoneA, 'B': self.btn_zoneB, 'C': self.btn_zoneC}
        for z_id, btn in btns.items():
            if z_id == self.current_zone:
                btn.config(relief=tk.SUNKEN, bg="#cccccc")
            else:
                btn.config(relief=tk.RAISED, bg="#f0f0f0")

    def on_canvas_click(self, event):
        """ Handle mouse clicks on the image """
        if self.mode != "edit":
            return

        # Check if 4 points already exist
        if len(self.zones[self.current_zone]) >= 4:
            messagebox.showinfo("Limit Reached", f"Zone {self.current_zone} already has 4 points. Clear it to redraw.")
            return

        # CLICK LOGIC:
        # The event gives us coordinates in the 1280x720 canvas.
        # We must SCALE UP these coordinates to 4K (3840x2160) before saving.
        
        real_x = int(event.x * self.scale_x)
        real_y = int(event.y * self.scale_y)

        # Add point
        self.zones[self.current_zone].append((real_x, real_y))
        
        # Update status
        self.status_label.config(text=f"Selected Zone {self.current_zone}. Points: {len(self.zones[self.current_zone])}/4")
        
        # Redraw
        self.redraw_canvas()

    def clear_current_zone(self):
        if self.mode == "edit":
            self.zones[self.current_zone] = []
            self.redraw_canvas()
            self.status_label.config(text=f"Cleared Zone {self.current_zone}.")

    def sort_points_clockwise(self, points):
        """ 
        Sorts a list of (x, y) tuples in clockwise order.
        Assumption: Screen coordinates (y increases downwards). 
        In screen coords, increasing angle from centroid is clockwise.
        """
        if len(points) < 3:
            return points

        # Calculate centroid
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)

        # Sort by angle from centroid
        # atan2(y, x) gives angle. 
        # In screen coords (+X right, +Y down):
        # East = 0, South = 90, West = 180, North = -90.
        # This order (-90 -> 0 -> 90 -> 180) is naturally clockwise visually.
        def angle_from_centroid(p):
            return math.atan2(p[1] - cy, p[0] - cx)

        return sorted(points, key=angle_from_centroid)

    def save_coordinates(self):
        """ Save to text file """
        if self.mode != "edit":
            return

        # 1. Validation: Check if all zones have exactly 4 points
        missing_zones = []
        for zone_id in ['A', 'B', 'C']:
            if len(self.zones[zone_id]) != 4:
                missing_zones.append(zone_id)
        
        if missing_zones:
            messagebox.showerror("Incomplete Zones", f"You must mark 4 points for the following zones before saving:\n{', '.join(missing_zones)}")
            return

        # 2. Save
        filename = "zone_coordinates.txt"
        try:
            with open(filename, "w") as f:
                f.write("Zone Coordinates Export (4K Resolution)\n")
                f.write("=======================================\n")
                for zone_id in ['A', 'B', 'C']:
                    # Get points and sort them clockwise
                    raw_points = self.zones[zone_id]
                    sorted_points = self.sort_points_clockwise(raw_points)
                    
                    f.write(f"Zone {zone_id}: {sorted_points}\n")
            
            messagebox.showinfo("Success", f"Coordinates saved to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

    def reset_app(self):
        """ Clear everything and go back to live camera mode """
        self.zones = {'A': [], 'B': [], 'C': []}
        self.current_zone = 'A'
        self.status_label.config(text="Status: Retaking photo...")
        self.window.update() 
        self.capture_image()

    def __del__(self):
        pass

if __name__ == "__main__":
    root = tk.Tk()
    app = ZoneSelectorApp(root, "Zone Drawing Tool")
    root.mainloop()