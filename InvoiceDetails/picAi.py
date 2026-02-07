# picAi.py
"""
Desktop app to organize bulk pictures by faces using local AI (face_recognition).
- Select a folder of images
- Detect faces and group images by person
- Save grouped images to subfolders
"""
import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import face_recognition

class FaceOrganizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Face Organizer AI")
        self.folder_path = ''
        self.images = []
        self.face_encodings = []
        self.groups = {}
        self.setup_ui()

    def setup_ui(self):
        frame = tk.Frame(self.root)
        frame.pack(padx=10, pady=10)
        tk.Button(frame, text="Select Image Folder", command=self.select_folder).pack(fill='x')
        self.status = tk.Label(frame, text="No folder selected.")
        self.status.pack(fill='x', pady=5)
        tk.Button(frame, text="Organize by Faces", command=self.organize_faces).pack(fill='x', pady=5)

    def select_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_path = path
            self.status.config(text=f"Selected: {path}")

    def organize_faces(self):
        if not self.folder_path:
            messagebox.showerror("Error", "Please select a folder first.")
            return
        self.status.config(text="Processing images...")
        self.root.update()
        self.images = [f for f in os.listdir(self.folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        self.face_encodings = []
        self.groups = {}
        for img_name in self.images:
            img_path = os.path.join(self.folder_path, img_name)
            image = face_recognition.load_image_file(img_path)
            encodings = face_recognition.face_encodings(image)
            if not encodings:
                continue  # No face found
            matched = False
            for idx, known_encoding in enumerate(self.face_encodings):
                matches = face_recognition.compare_faces([known_encoding], encodings[0], tolerance=0.5)
                if matches[0]:
                    self.groups[idx].append(img_name)
                    matched = True
                    break
            if not matched:
                self.face_encodings.append(encodings[0])
                self.groups[len(self.face_encodings)-1] = [img_name]
        # Save to subfolders
        for idx, img_list in self.groups.items():
            group_folder = os.path.join(self.folder_path, f"person_{idx+1}")
            os.makedirs(group_folder, exist_ok=True)
            for img_name in img_list:
                shutil.copy2(os.path.join(self.folder_path, img_name), os.path.join(group_folder, img_name))
        self.status.config(text=f"Done! {len(self.groups)} people found. Images grouped.")
        messagebox.showinfo("Done", f"Organized into {len(self.groups)} groups.")

if __name__ == "__main__":
    root = tk.Tk()
    app = FaceOrganizerApp(root)
    root.mainloop()

"/Users/arnoldoramirezjr/Documents/AIO Python/.venv/bin/python" -m pip show face_recognition

brew install cmake
brew install boost
brew install boost-python3
pip install dlib
pip install face_recognition
