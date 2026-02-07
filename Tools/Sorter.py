# organize the desktop, downloads, and documents folders    
# moves images, videos, screenshots, and audio files
# into corresponding folders
import os
import shutil


audio = (".3ga", ".aac", ".ac3", ".aif", ".aiff",
         ".alac", ".amr", ".ape", ".au", ".dss",
         ".flac", ".flv", ".m4a", ".m4b", ".m4p",
         ".mp3", ".mpga", ".ogg", ".oga", ".mogg",
         ".opus", ".qcp", ".tta", ".voc", ".wav",
         ".wma", ".wv")

video = (".webm", ".MTS", ".M2TS", ".TS", ".mov",
         ".mp4", ".m4p", ".m4v", ".mxf", ".MOV")

img = (".jpg", ".jpeg", ".jfif", ".pjpeg", ".pjp", ".png",
       ".gif", ".webp", ".svg", ".apng", ".avif", ".JPG", ".HEIC", ".heic")

pdf = (".pdf",)

excel = (".xlsx",)

csv = (".csv",)

doc = (".doc", ".docx")

zip = (".zip",)

ps = (".psd",)

# 3D printer file formats
d3_printer = (".stl",)
finished_project = (".3mf",)

def is_audio(file):
    return os.path.splitext(file)[1] in audio

def is_video(file):
    return os.path.splitext(file)[1] in video
def is_screenshot(file):
    name, ext = os.path.splitext(file)
    return (ext in img) and "screenshot" in name.lower()

def is_image(file):
    return os.path.splitext(file)[1] in img

def is_pdf(file):
    return os.path.splitext(file)[1] in pdf

def is_excel(file):
    return os.path.splitext(file)[1] in excel

def is_csv(file):
    return os.path.splitext(file)[1] in csv

def is_doc(file):
    return os.path.splitext(file)[1] in doc

def is_zip(file):
    return os.path.splitext(file)[1] in zip

def is_ps(file):
    return os.path.splitext(file)[1] in ps

def is_3dprinter(file):
    return os.path.splitext(file)[1] in d3_printer

def is_finished_project(file):
    return os.path.splitext(file)[1] in finished_project



# List of source directories to organize
source_dirs = [
    "/Users/arnoldoramirezjr/Desktop",
    "/Users/arnoldoramirezjr/Downloads",
    "/Users/arnoldoramirezjr/Documents"
]

# Ensure all destination folders exist
destinations = [
    "/Users/arnoldoramirezjr/Documents/Audio",
    "/Users/arnoldoramirezjr/Documents/Videos",
    "/Users/arnoldoramirezjr/Documents/PDF",
    "/Users/arnoldoramirezjr/Documents/Excel",
    "/Users/arnoldoramirezjr/Documents/CSV",
    "/Users/arnoldoramirezjr/Documents/Document",
    "/Users/arnoldoramirezjr/Documents/zips",
    "/Users/arnoldoramirezjr/Documents/Photoshop",
    "/Users/arnoldoramirezjr/Documents/Screenshots",
    "/Users/arnoldoramirezjr/Documents/Images",
    "/Users/arnoldoramirezjr/Documents/3D printer",
    "/Users/arnoldoramirezjr/Documents/3D printer/Finished Projects",
    "/Users/arnoldoramirezjr/Documents/untitled folder"
]

for folder in destinations:
    os.makedirs(folder, exist_ok=True)

def get_unique_dest(dest_folder, filename):
    name, ext = os.path.splitext(filename)
    counter = 1
    dest_path = os.path.join(dest_folder, filename)
    while os.path.exists(dest_path):
        dest_path = os.path.join(dest_folder, f"{name}_{counter}{ext}")
        counter += 1
    return dest_path


# Add counters for each destination folder
move_counts = {
    "Audio": 0,
    "Videos": 0,
    "PDF": 0,
    "Excel": 0,
    "CSV": 0,
    "Document": 0,
    "zips": 0,
    "Photoshop": 0,
    "Screenshots": 0,
    "Images": 0,
    "3D printer": 0,
    "Finished Projects": 0,
    "untitled folder": 0
}

for src_dir in source_dirs:
    for file in os.listdir(src_dir):
        if file == '.DS_Store':
            continue
        file_path = os.path.join(src_dir, file)
        if not os.path.isfile(file_path):
            continue
        try:
            if is_audio(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/Audio", file)
                move_counts["Audio"] += 1
            elif is_video(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/Videos", file)
                move_counts["Videos"] += 1
            elif is_pdf(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/PDF", file)
                move_counts["PDF"] += 1
            elif is_excel(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/Excel", file)
                move_counts["Excel"] += 1
            elif is_csv(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/CSV", file)
                move_counts["CSV"] += 1
            elif is_doc(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/Document", file)
                move_counts["Document"] += 1
            elif is_zip(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/zips", file)
                move_counts["zips"] += 1
            elif is_ps(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/Photoshop", file)
                move_counts["Photoshop"] += 1
            elif is_image(file):
                if is_screenshot(file):
                    dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/Screenshots", file)
                    move_counts["Screenshots"] += 1
                else:
                    dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/Images", file)
                    move_counts["Images"] += 1
            elif is_3dprinter(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/3D printer", file)
                move_counts["3D printer"] += 1
            elif is_finished_project(file):
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/3D printer/Finished Projects", file)
                move_counts["Finished Projects"] += 1
            else:
                dest = get_unique_dest("/Users/arnoldoramirezjr/Documents/untitled folder", file)
                move_counts["untitled folder"] += 1
            shutil.move(file_path, dest)
        except Exception as e:
            print(f"Error moving {file}: {e}")

# Print summary
print("\nFile Move Summary:")
for folder in move_counts:
    print(f"{move_counts[folder]} files moved to {folder}")