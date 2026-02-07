import os
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic')

def get_image_files(folder):
    return [os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(IMAGE_EXTENSIONS)]

def delete_file(filepath):
    try:
        os.remove(filepath)
        return True
    except Exception as e:
        return False

def move_file(filepath, dest_folder):
    import shutil
    try:
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)
        dest_path = os.path.join(dest_folder, os.path.basename(filepath))
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while os.path.exists(dest_path):
            dest_path = f"{base}_{counter}{ext}"
            counter += 1
        shutil.move(filepath, dest_path)
        return True
    except Exception as e:
        return False
