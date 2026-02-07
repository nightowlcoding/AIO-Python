import os
import face_recognition
from shutil import move

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff', '.tif', '.heic')

def get_image_files(folder):
    return [os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f)) and f.lower().endswith(IMAGE_EXTENSIONS)]

def encode_face(image_path):
    try:
        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)
        if encodings:
            return encodings[0]
    except Exception:
        pass
    return None

def group_images_by_face(folder, output_base):
    images = get_image_files(folder)
    known_faces = []
    face_folders = []
    for img_path in images:
        encoding = encode_face(img_path)
        if encoding is None:
            # No face found, move to 'NoFace' folder
            dest = os.path.join(output_base, 'NoFace')
        else:
            matched = False
            for i, known in enumerate(known_faces):
                match = face_recognition.compare_faces([known], encoding, tolerance=0.5)[0]
                if match:
                    dest = os.path.join(output_base, f'Person_{i+1}')
                    matched = True
                    break
            if not matched:
                known_faces.append(encoding)
                dest = os.path.join(output_base, f'Person_{len(known_faces)}')
        if not os.path.exists(dest):
            os.makedirs(dest)
        move(img_path, os.path.join(dest, os.path.basename(img_path)))
