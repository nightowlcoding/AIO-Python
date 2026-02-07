#!/usr/bin/env python
# encoding: utf-8
"""
facesort_simple.py

Simple face detection and sorting application with GUI.
Uses face_recognition library for face detection and recognition.
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import os
import shutil
from pathlib import Path
import sys

try:
    import face_recognition
    import numpy as np
    from PIL import Image
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install required packages:")
    print("pip install face-recognition pillow")


class FaceSortGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FaceSort - Sort Photos by Face Recognition")
        self.root.geometry("900x750")
        
        # Variables
        self.source_dir = tk.StringVar()
        self.output_dir = tk.StringVar(value="./facesort_output")
        self.tolerance = tk.DoubleVar(value=0.6)
        self.copy_files = tk.BooleanVar(value=True)
        self.model = tk.StringVar(value="hog")
        
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
        ttk.Label(options_frame, text="Detection Model:").grid(row=opt_row, column=0, sticky=tk.W, pady=5)
        model_combo = ttk.Combobox(options_frame, textvariable=self.model, width=20,
                                   values=["hog", "cnn"])
        model_combo.grid(row=opt_row, column=1, sticky=tk.W, padx=5)
        ttk.Label(options_frame, text="(hog=faster, cnn=more accurate)").grid(row=opt_row, column=2, sticky=tk.W, padx=5)
        opt_row += 1
        
        # Tolerance
        ttk.Label(options_frame, text="Recognition Tolerance:").grid(row=opt_row, column=0, sticky=tk.W, pady=5)
        tolerance_frame = ttk.Frame(options_frame)
        tolerance_frame.grid(row=opt_row, column=1, sticky=tk.W, padx=5)
        ttk.Scale(tolerance_frame, from_=0.3, to=0.8, variable=self.tolerance, 
                 orient=tk.HORIZONTAL, length=150).pack(side=tk.LEFT)
        ttk.Label(tolerance_frame, textvariable=self.tolerance).pack(side=tk.LEFT, padx=5)
        ttk.Label(options_frame, text="(lower = stricter)").grid(row=opt_row, column=2, sticky=tk.W, padx=5)
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
        
        # Convert to absolute path
        output_path = os.path.abspath(output_path)
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
            self.log_message(f"Model: {self.model.get()}")
            self.log_message(f"Tolerance: {self.tolerance.get():.2f}")
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
            
            # Dictionary to store known face encodings
            known_faces = []
            person_counter = 0
            processed_count = 0
            no_face_count = 0
            
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
                    self.log_message(f"[{idx + 1}/{len(image_files)}] {filename}")
                    
                    # Load image and detect faces
                    try:
                        image = face_recognition.load_image_file(image_path)
                        face_locations = face_recognition.face_locations(image, model=self.model.get())
                        
                        if not face_locations:
                            self.log_message(f"  → No faces detected")
                            no_face_count += 1
                            continue
                        
                        # Get face encodings
                        face_encodings = face_recognition.face_encodings(image, face_locations)
                        
                        # Process each detected face
                        for face_encoding in face_encodings:
                            if self.stop_flag:
                                break
                            
                            # Try to find matching person
                            person_id = None
                            
                            if known_faces:
                                # Compare with known faces
                                matches = face_recognition.compare_faces(
                                    [kf['encoding'] for kf in known_faces],
                                    face_encoding,
                                    tolerance=self.tolerance.get()
                                )
                                
                                # Find best match
                                if True in matches:
                                    face_distances = face_recognition.face_distance(
                                        [kf['encoding'] for kf in known_faces],
                                        face_encoding
                                    )
                                    best_match_index = np.argmin(face_distances)
                                    if matches[best_match_index]:
                                        person_id = known_faces[best_match_index]['person_id']
                                        self.log_message(f"  → Matched with Person {person_id}")
                            
                            # If no match found, create new person
                            if person_id is None:
                                person_id = person_counter
                                person_counter += 1
                                known_faces.append({
                                    'person_id': person_id,
                                    'encoding': face_encoding
                                })
                                self.log_message(f"  → New person detected: Person {person_id}")
                            
                            # Copy/Move image to person folder
                            try:
                                person_folder = os.path.abspath(os.path.join(self.output_dir.get(), f"Person_{person_id}"))
                                os.makedirs(person_folder, exist_ok=True)
                                
                                dest_path = os.path.join(person_folder, filename)
                                
                                # Handle duplicate filenames
                                counter = 1
                                while os.path.exists(dest_path):
                                    name, ext = os.path.splitext(filename)
                                    dest_path = os.path.join(person_folder, f"{name}_{counter}{ext}")
                                    counter += 1
                                
                                # Use absolute paths for both source and destination
                                abs_image_path = os.path.abspath(image_path)
                                abs_dest_path = os.path.abspath(dest_path)
                                
                                if self.copy_files.get():
                                    shutil.copy2(abs_image_path, abs_dest_path)
                                    self.log_message(f"  → Copied to {os.path.basename(person_folder)}")
                                else:
                                    shutil.move(abs_image_path, abs_dest_path)
                                    self.log_message(f"  → Moved to {os.path.basename(person_folder)}")
                                
                                processed_count += 1
                            except PermissionError as pe:
                                self.log_message(f"  → Permission Error: Cannot access file. Try copying instead of moving, or check folder permissions.")
                            except Exception as file_error:
                                self.log_message(f"  → File Error: {str(file_error)}")
                            
                            break  # Only process first face in image
                    
                    except Exception as e:
                        self.log_message(f"  → Error: {str(e)}")
                        continue
                
                except Exception as e:
                    self.log_message(f"  → Error processing image: {str(e)}")
                    continue
            
            # Summary
            self.log_message("\n" + "=" * 80)
            self.log_message(f"✓ Face sorting completed!")
            self.log_message(f"Total images scanned: {len(image_files)}")
            self.log_message(f"Images with faces sorted: {processed_count}")
            self.log_message(f"Images without faces: {no_face_count}")
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


def main():
    root = tk.Tk()
    app = FaceSortGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
