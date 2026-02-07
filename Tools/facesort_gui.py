                        #!/usr/bin/env python
# encoding: utf-8
"""
facesort_gui.py

Face detection and sorting application with GUI.
Uses DeepFace and RetinaFace to detect faces in images and sort them by person.
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import shutil
from pathlib import Path
from datetime import datetime
import sys

try:
    from deepface import DeepFace
    from retinaface import RetinaFace
    import cv2
    import numpy as np
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install required packages:")
    print("pip install deepface retina-face opencv-python")


class FaceSortGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FaceSort - Sort Photos by Face Recognition")
        self.root.geometry("900x750")
        
        # Variables
        self.source_dir = tk.StringVar()
        self.output_dir = tk.StringVar(value="./facesort_output")
        self.model_name = tk.StringVar(value="VGG-Face")
        self.distance_metric = tk.StringVar(value="cosine")
        self.detector_backend = tk.StringVar(value="retinaface")
        self.threshold = tk.DoubleVar(value=0.6)
        self.copy_files = tk.BooleanVar(value=True)
        
        self.is_running = False
        self.stop_flag = False
        
        self.create_widgets()
        
    def create_widgets(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        row = 0
        
        # Title
        title = ttk.Label(main_frame, text="FaceSort - Sort Photos by Face Recognition", 
                         font=('Helvetica', 16, 'bold'))
        title.grid(row=row, column=0, columnspan=3, pady=(0, 10))
        row += 1
        
        subtitle = ttk.Label(main_frame, text="Automatically organize photos by detecting and recognizing faces", 
                            font=('Helvetica', 10), foreground='gray')
        subtitle.grid(row=row, column=0, columnspan=3, pady=(0, 20))
        row += 1
        
        # Source Directory
        ttk.Label(main_frame, text="Source Directory:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.source_dir, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_source).grid(row=row, column=2, sticky=tk.W)
        row += 1
        
        # Output Directory
        ttk.Label(main_frame, text="Output Directory:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_dir, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=5)
        ttk.Button(main_frame, text="Browse", command=self.browse_output).grid(row=row, column=2, sticky=tk.W)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=15)
        row += 1
        
        # Options Frame
        options_frame = ttk.LabelFrame(main_frame, text="Recognition Options", padding="10")
        options_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        opt_row = 0
        
        # Model Selection
        ttk.Label(options_frame, text="Recognition Model:").grid(row=opt_row, column=0, sticky=tk.W, pady=5)
        model_combo = ttk.Combobox(options_frame, textvariable=self.model_name, width=20,
                                   values=["VGG-Face", "Facenet", "Facenet512", "OpenFace", 
                                          "DeepFace", "DeepID", "ArcFace", "Dlib", "SFace"])
        model_combo.grid(row=opt_row, column=1, sticky=tk.W, padx=5)
        opt_row += 1
        
        # Distance Metric
        ttk.Label(options_frame, text="Distance Metric:").grid(row=opt_row, column=0, sticky=tk.W, pady=5)
        metric_combo = ttk.Combobox(options_frame, textvariable=self.distance_metric, width=20,
                                    values=["cosine", "euclidean", "euclidean_l2"])
        metric_combo.grid(row=opt_row, column=1, sticky=tk.W, padx=5)
        opt_row += 1
        
        # Detector Backend
        ttk.Label(options_frame, text="Face Detector:").grid(row=opt_row, column=0, sticky=tk.W, pady=5)
        detector_combo = ttk.Combobox(options_frame, textvariable=self.detector_backend, width=20,
                                      values=["retinaface", "mtcnn", "opencv", "ssd", "dlib"])
        detector_combo.grid(row=opt_row, column=1, sticky=tk.W, padx=5)
        opt_row += 1
        
        # Threshold
        ttk.Label(options_frame, text="Recognition Threshold:").grid(row=opt_row, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(options_frame)
        threshold_frame.grid(row=opt_row, column=1, sticky=tk.W, padx=5)
        ttk.Scale(threshold_frame, from_=0.3, to=0.9, variable=self.threshold, 
                 orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT)
        ttk.Label(threshold_frame, textvariable=self.threshold).pack(side=tk.LEFT, padx=5)
        ttk.Label(threshold_frame, text="(lower = stricter)").pack(side=tk.LEFT)
        opt_row += 1
        
        # Copy vs Move
        ttk.Checkbutton(options_frame, text="Copy files (keep originals)", 
                       variable=self.copy_files).grid(row=opt_row, column=0, columnspan=2, sticky=tk.W, pady=5)
        
        # Buttons Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=15)
        row += 1
        
        self.start_button = ttk.Button(button_frame, text="Start Face Sorting", 
                                       command=self.start_sorting, width=20)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_sorting, 
                                      state=tk.DISABLED, width=15)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log, width=15).pack(side=tk.LEFT, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        # Status label
        self.status_label = ttk.Label(main_frame, text="Ready", foreground='green')
        self.status_label.grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=5)
        row += 1
        
        # Output/Log area
        log_label = ttk.Label(main_frame, text="Processing Log:")
        log_label.grid(row=row, column=0, sticky=tk.W, pady=(10, 5))
        row += 1
        
        self.output_text = scrolledtext.ScrolledText(main_frame, height=15, width=80, wrap=tk.WORD)
        self.output_text.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        main_frame.rowconfigure(row, weight=1)
        
        # Redirect stdout
        sys.stdout = TextRedirector(self.output_text, "stdout")
        
        # Initial message
        self.log_message("Welcome to FaceSort!")
        self.log_message("Select a source directory containing images with faces to begin.")
        self.log_message("Supported formats: jpg, jpeg, png, bmp")
        self.log_message("-" * 80)
        
    def browse_source(self):
        directory = filedialog.askdirectory(title="Select Source Directory with Images")
        if directory:
            self.source_dir.set(directory)
    
    def browse_output(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_dir.set(directory)
    
    def clear_log(self):
        self.output_text.delete(1.0, tk.END)
    
    def log_message(self, message):
        self.output_text.insert(tk.END, message + "\n")
        self.output_text.see(tk.END)
        self.output_text.update_idletasks()
    
    def update_status(self, message, color='black'):
        self.status_label.config(text=message, foreground=color)
        self.root.update_idletasks()
    
    def start_sorting(self):
        # Validate inputs
        if not self.source_dir.get():
            messagebox.showerror("Error", "Please select a source directory")
            return
        
        if not os.path.exists(self.source_dir.get()):
            messagebox.showerror("Error", "Source directory does not exist")
            return
        
        # Create output directory if it doesn't exist
        output_path = self.output_dir.get()
        if not output_path:
            output_path = os.path.join(os.path.dirname(self.source_dir.get()), "facesort_output")
            self.output_dir.set(output_path)
        
        # Disable start button and enable stop button
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.is_running = True
        self.stop_flag = False
        
        # Run in a separate thread
        thread = threading.Thread(target=self.sort_faces_thread, daemon=True)
        thread.start()
    
    def stop_sorting(self):
        self.stop_flag = True
        self.update_status("Stopping...", 'orange')
        self.log_message("\n⚠ Stop requested. Finishing current operation...")
    
    def sort_faces_thread(self):
        try:
            self.update_status("Processing...", 'blue')
            self.log_message("\n" + "=" * 80)
            self.log_message(f"Starting face sorting process")
            self.log_message(f"Source: {self.source_dir.get()}")
            self.log_message(f"Output: {self.output_dir.get()}")
            self.log_message(f"Model: {self.model_name.get()}")
            self.log_message(f"Detector: {self.detector_backend.get()}")
            self.log_message("=" * 80 + "\n")
            
            # Get all image files
            supported_formats = ['.jpg', '.jpeg', '.png', '.bmp']
            image_files = []
            
            for root, dirs, files in os.walk(self.source_dir.get()):
                for file in files:
                    if Path(file).suffix.lower() in supported_formats:
                        image_files.append(os.path.join(root, file))
            
            if not image_files:
                self.log_message("✗ No image files found in the source directory!")
                self.update_status("No images found", 'red')
                return
            
            self.log_message(f"Found {len(image_files)} images to process\n")
            
            # Create output directory
            os.makedirs(self.output_dir.get(), exist_ok=True)
            
            # Dictionary to store face encodings and their associated person ID
            known_faces = []
            person_counter = 0
            processed_count = 0
            
            # Process each image
            for idx, image_path in enumerate(image_files):
                if self.stop_flag:
                    break
                
                try:
                    # Update progress
                    progress = ((idx + 1) / len(image_files)) * 100
                    self.progress['value'] = progress
                    self.update_status(f"Processing image {idx + 1}/{len(image_files)}", 'blue')
                    
                    filename = os.path.basename(image_path)
                    self.log_message(f"[{idx + 1}/{len(image_files)}] Processing: {filename}")
                    
                    # Detect faces in the image
                    try:
                        faces = RetinaFace.detect_faces(image_path)
                        
                        if not faces or isinstance(faces, dict) and len(faces) == 0:
                            self.log_message(f"  → No faces detected")
                            continue
                        
                        # Process each detected face
                        for face_key in faces.keys():
                            if self.stop_flag:
                                break
                            
                            # Get face region
                            face_data = faces[face_key]
                            facial_area = face_data['facial_area']
                            
                            # Try to find matching person
                            person_id = None
                            
                            try:
                                # Use DeepFace to verify against known faces
                                matched = False
                                
                                for known_face in known_faces:
                                    try:
                                        result = DeepFace.verify(
                                            img1_path=image_path,
                                            img2_path=known_face['image_path'],
                                            model_name=self.model_name.get(),
                                            distance_metric=self.distance_metric.get(),
                                            detector_backend=self.detector_backend.get(),
                                            enforce_detection=False
                                        )
                                        
                                        if result['verified']:
                                            person_id = known_face['person_id']
                                            matched = True
                                            self.log_message(f"  → Matched with Person {person_id}")
                                            break
                                    except:
                                        continue
                                
                                # If no match found, create new person
                                if not matched:
                                    person_id = person_counter
                                    person_counter += 1
                                    known_faces.append({
                                        'person_id': person_id,
                                        'image_path': image_path
                                    })
                                    self.log_message(f"  → New person detected: Person {person_id}")
                                
                            except Exception as e:
                                # If verification fails, treat as new person
                                person_id = person_counter
                                person_counter += 1
                                known_faces.append({
                                    'person_id': person_id,
                                    'image_path': image_path
                                })
                                self.log_message(f"  → New person detected: Person {person_id}")
                            
                            # Copy/Move image to person folder
                            if person_id is not None:
                                person_folder = os.path.join(self.output_dir.get(), f"Person_{person_id}")
                                os.makedirs(person_folder, exist_ok=True)
                                
                                dest_path = os.path.join(person_folder, filename)
                                
                                # Handle duplicate filenames
                                counter = 1
                                while os.path.exists(dest_path):
                                    name, ext = os.path.splitext(filename)
                                    dest_path = os.path.join(person_folder, f"{name}_{counter}{ext}")
                                    counter += 1
                                
                                if self.copy_files.get():
                                    shutil.copy2(image_path, dest_path)
                                else:
                                    shutil.move(image_path, dest_path)
                                
                                processed_count += 1
                    
                    except Exception as e:
                        self.log_message(f"  → Error detecting faces: {str(e)}")
                        continue
                
                except Exception as e:
                    self.log_message(f"  → Error processing image: {str(e)}")
                    continue
            
            # Summary
            self.log_message("\n" + "=" * 80)
            self.log_message(f"✓ Face sorting completed!")
            self.log_message(f"Total images processed: {processed_count}")
            self.log_message(f"Unique persons found: {person_counter}")
            self.log_message(f"Output directory: {self.output_dir.get()}")
            self.log_message("=" * 80)
            
            self.update_status("Completed successfully!", 'green')
            
        except Exception as e:
            self.log_message(f"\n✗ Error: {str(e)}")
            import traceback
            self.log_message(traceback.format_exc())
            self.update_status("Error occurred", 'red')
        
        finally:
            self.root.after(0, self.finish_sorting)
    
    def finish_sorting(self):
        self.progress['value'] = 0
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.is_running = False


class TextRedirector:
    """Redirect stdout/stderr to a tkinter Text widget"""
    def __init__(self, widget, tag="stdout"):
        self.widget = widget
        self.tag = tag

    def write(self, str_text):
        self.widget.insert(tk.END, str_text)
        self.widget.see(tk.END)
        self.widget.update_idletasks()

    def flush(self):
        pass


def main():
    root = tk.Tk()
    app = FaceSortGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
