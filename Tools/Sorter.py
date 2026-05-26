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

HOME_DIR = os.path.expanduser("~")
DESKTOP_DIR = os.path.join(HOME_DIR, "Desktop")
DOWNLOADS_DIR = os.path.join(HOME_DIR, "Downloads")
DOCUMENTS_DIR = os.path.join(HOME_DIR, "Documents")

DEST_FOLDERS = {
    "Audio": os.path.join(DOCUMENTS_DIR, "Audio"),
    "Videos": os.path.join(DOCUMENTS_DIR, "Videos"),
    "PDF": os.path.join(DOCUMENTS_DIR, "PDF"),
    "Excel": os.path.join(DOCUMENTS_DIR, "Excel"),
    "CSV": os.path.join(DOCUMENTS_DIR, "CSV"),
    "Document": os.path.join(DOCUMENTS_DIR, "Document"),
    "zips": os.path.join(DOCUMENTS_DIR, "zips"),
    "Photoshop": os.path.join(DOCUMENTS_DIR, "Photoshop"),
    "Screenshots": os.path.join(DOCUMENTS_DIR, "Screenshots"),
    "Images": os.path.join(DOCUMENTS_DIR, "Images"),
    "3D printer": os.path.join(DOCUMENTS_DIR, "3D printer"),
    "Finished Projects": os.path.join(DOCUMENTS_DIR, "3D printer", "Finished Projects"),
    "untitled folder": os.path.join(DOCUMENTS_DIR, "untitled folder"),
}

DEFAULT_SOURCE_DIRS = [
    DESKTOP_DIR,
    DOWNLOADS_DIR,
    DOCUMENTS_DIR,
]

DEFAULT_EXTENSION_RULES = {
    "Audio": audio,
    "Videos": video,
    "PDF": pdf,
    "Excel": excel,
    "CSV": csv,
    "Document": doc,
    "zips": zip,
    "Photoshop": ps,
    "Images": img,
    "3D printer": d3_printer,
    "Finished Projects": finished_project,
}

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



def build_dest_folders(documents_dir):
    return {
        "Audio": os.path.join(documents_dir, "Audio"),
        "Videos": os.path.join(documents_dir, "Videos"),
        "PDF": os.path.join(documents_dir, "PDF"),
        "Excel": os.path.join(documents_dir, "Excel"),
        "CSV": os.path.join(documents_dir, "CSV"),
        "Document": os.path.join(documents_dir, "Document"),
        "zips": os.path.join(documents_dir, "zips"),
        "Photoshop": os.path.join(documents_dir, "Photoshop"),
        "Screenshots": os.path.join(documents_dir, "Screenshots"),
        "Images": os.path.join(documents_dir, "Images"),
        "3D printer": os.path.join(documents_dir, "3D printer"),
        "Finished Projects": os.path.join(documents_dir, "3D printer", "Finished Projects"),
        "untitled folder": os.path.join(documents_dir, "untitled folder"),
    }


def ensure_destinations(dest_folders):
    for folder in dest_folders.values():
        os.makedirs(folder, exist_ok=True)

def get_unique_dest(dest_folder, filename):
    name, ext = os.path.splitext(filename)
    counter = 1
    dest_path = os.path.join(dest_folder, filename)
    while os.path.exists(dest_path):
        dest_path = os.path.join(dest_folder, f"{name}_{counter}{ext}")
        counter += 1
    return dest_path


def normalize_extension_rules(extension_rules):
    normalized = {}
    for category, exts in extension_rules.items():
        valid_exts = []
        for ext in exts:
            cleaned = str(ext).strip().lower()
            if not cleaned:
                continue
            if not cleaned.startswith("."):
                cleaned = f".{cleaned}"
            valid_exts.append(cleaned)
        normalized[category] = tuple(valid_exts)
    return normalized


def categorize_file(filename, extension_rules):
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext in extension_rules.get("Audio", ()):
        return "Audio"
    if ext in extension_rules.get("Videos", ()):
        return "Videos"
    if ext in extension_rules.get("PDF", ()):
        return "PDF"
    if ext in extension_rules.get("Excel", ()):
        return "Excel"
    if ext in extension_rules.get("CSV", ()):
        return "CSV"
    if ext in extension_rules.get("Document", ()):
        return "Document"
    if ext in extension_rules.get("zips", ()):
        return "zips"
    if ext in extension_rules.get("Photoshop", ()):
        return "Photoshop"
    if ext in extension_rules.get("Images", ()):
        if "screenshot" in name.lower():
            return "Screenshots"
        return "Images"
    if ext in extension_rules.get("3D printer", ()):
        return "3D printer"
    if ext in extension_rules.get("Finished Projects", ()):
        return "Finished Projects"
    return "untitled folder"


def organize_files(source_dirs, documents_dir, extension_rules=None):
    dest_folders = build_dest_folders(documents_dir)
    ensure_destinations(dest_folders)
    normalized_rules = normalize_extension_rules(extension_rules or DEFAULT_EXTENSION_RULES)

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
        "untitled folder": 0,
    }
    errors = []

    for src_dir in source_dirs:
        if not os.path.isdir(src_dir):
            continue
        for file in os.listdir(src_dir):
            if file == ".DS_Store":
                continue
            file_path = os.path.join(src_dir, file)
            if not os.path.isfile(file_path):
                continue
            try:
                category = categorize_file(file, normalized_rules)
                dest = get_unique_dest(dest_folders[category], file)
                move_counts[category] += 1
                shutil.move(file_path, dest)
            except Exception as e:
                errors.append(f"Error moving {file}: {e}")

    return move_counts, errors


def run_default_sort():
    move_counts, errors = organize_files(DEFAULT_SOURCE_DIRS, DOCUMENTS_DIR)
    print("\nFile Move Summary:")
    for folder in move_counts:
        print(f"{move_counts[folder]} files moved to {folder}")
    for err in errors:
        print(err)


if __name__ == "__main__":
    run_default_sort()