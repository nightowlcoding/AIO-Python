import os
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from collections import Counter
import threading
import hashlib
import re
import time

# --- Optional dependencies (for static analysis and runtime) ---
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

try:
    from PIL import Image, UnidentifiedImageError, ImageTk, ImageDraw, ExifTags
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pypdf
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# --- Excel Tools Logic ---
def clean_excel_filename(filename):
    name = re.sub(r'^[\d_\-\.]+', '', filename)
    base, ext = os.path.splitext(name)
    clean_base = re.sub(r'[\._\-]+', ' ', base).strip()
    clean_base = ' '.join(word.capitalize() for word in clean_base.split())
    return clean_base + ext

def sort_excel_files(folder, log=None):
    exts = {'.xls', '.xlsx', '.xlsm', '.csv'}
    count = 0
    dest_folder = os.path.join(folder, 'Excel')
    os.makedirs(dest_folder, exist_ok=True)
    for dirpath, dirnames, filenames in os.walk(folder):
        for entry in filenames:
            path = os.path.join(dirpath, entry)
            ext = os.path.splitext(entry)[1].lower()
            if ext not in exts or dirpath == dest_folder:
                continue
            new_path = os.path.join(dest_folder, entry)
            counter = 1
            base, ext2 = os.path.splitext(entry)
            while os.path.exists(new_path):
                new_path = os.path.join(dest_folder, f"{base}_{counter}{ext2}")
                counter += 1
            try:
                shutil.move(path, new_path)
                if log:
                    log(f"Moved: {entry} -> Excel/")
                count += 1
            except Exception as e:
                if log:
                    log(f"Failed to move {entry}: {e}")
    if log:
        log(f"\nMoved {count} Excel files.")
    return count

def get_excel_hash(file_path):
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return None

def scan_excel_duplicates(folder, log=None):
    exts = {'.xls', '.xlsx', '.xlsm', '.csv'}
    hash_groups = {}
    excel_files = []
    for dirpath, dirnames, filenames in os.walk(folder):
        for entry in filenames:
            ext = os.path.splitext(entry)[1].lower()
            if ext in exts:
                excel_files.append(os.path.join(dirpath, entry))
    for file_path in excel_files:
        file_hash = get_excel_hash(file_path)
        if file_hash:
            hash_groups.setdefault(file_hash, []).append(file_path)
    duplicates = {k: v for k, v in hash_groups.items() if len(v) > 1}
    if log:
        log(f"Found {len(excel_files)} Excel files to scan...")
        log(f"\nFound {len(duplicates)} groups of duplicate Excel files")
        for files in duplicates.values():
            log(f"  Duplicate group ({len(files)} files):")
            for f in files:
                log(f"    - {os.path.basename(f)}")
    return {'duplicates': duplicates, 'hash_groups': hash_groups, 'excel_files': excel_files}

def delete_excel_duplicates(duplicates, log=None):
    deleted_count = 0
    for files in duplicates.values():
        keep_file = files[0]
        if log:
            log(f"Keeping: {os.path.basename(keep_file)}")
        for duplicate_file in files[1:]:
            try:
                os.remove(duplicate_file)
                if log:
                    log(f"  Deleted: {os.path.basename(duplicate_file)}")
                deleted_count += 1
            except Exception as e:
                if log:
                    log(f"  Failed to delete {os.path.basename(duplicate_file)}: {e}")
        if log:
            log("")
    if log:
        log(f"Deleted {deleted_count} duplicate Excel files.")
    return deleted_count

def clean_excel_names(folder, log=None):
    exts = {'.xls', '.xlsx', '.xlsm', '.csv'}
    count = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        for entry in filenames:
            ext = os.path.splitext(entry)[1].lower()
            if ext not in exts:
                continue
            path = os.path.join(dirpath, entry)
            new_name = clean_excel_filename(entry)
            if new_name != entry:
                new_path = os.path.join(dirpath, new_name)
                counter = 1
                base, ext2 = os.path.splitext(new_name)
                while os.path.exists(new_path):
                    new_path = os.path.join(dirpath, f"{base}_{counter}{ext2}")
                    counter += 1
                try:
                    os.rename(path, new_path)
                    if log:
                        log(f"Renamed: {entry} -> {os.path.basename(new_path)}")
                    count += 1
                except Exception as e:
                    if log:
                        log(f"Failed to rename {entry}: {e}")
    if log:
        log(f"\nRenamed {count} Excel files.")
    return count

# --- Cleaner Logic ---
def move_files_to_root(root_folder, log=None):
    for dirpath, dirnames, filenames in os.walk(root_folder):
        if os.path.abspath(dirpath) == os.path.abspath(root_folder):
            continue
        for filename in filenames:
            src_path = os.path.join(dirpath, filename)
            base, ext = os.path.splitext(filename)
            dest_path = os.path.join(root_folder, filename)
            count = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(root_folder, f"{base}_{count}{ext}")
                count += 1
            shutil.move(src_path, dest_path)
            if log:
                log(f"Moved: {src_path} -> {dest_path}")

# --- Organizer Logic ---
EXTENSION_MAP = {
    'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.webp'},
    'videos': {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v'},
    'pdf': {'.pdf'},
    'excel': {'.xls', '.xlsx', '.xlsm', '.csv'},
    'words': {'.doc', '.docx'},
    'powerpoint': {'.ppt', '.pptx'},
}
DEFAULT_FOLDER = 'Untitled'

def _determine_folder(ext: str) -> str:
    ext = ext.lower()
    for folder, exts in EXTENSION_MAP.items():
        if ext in exts:
            return folder.capitalize()
    return DEFAULT_FOLDER

def _unique_target_path(target_dir: Path, name: str) -> Path:
    candidate = target_dir / name
    if not candidate.exists():
        return candidate
    stem = Path(name).stem
    suffix = Path(name).suffix
    counter = 1
    while True:
        new_name = f"{stem}_{counter}{suffix}"
        candidate = target_dir / new_name
        if not candidate.exists():
            return candidate
        counter += 1

def organize_folder(folder, log=None):
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")
    
    counts = Counter()
    for entry in folder.iterdir():
        if entry.is_dir():
            continue
        ext = entry.suffix.lower()
        dest_folder_name = _determine_folder(ext)
        dest_folder = folder / dest_folder_name
        
        # Create destination folder if it doesn't exist
        # Handle case where a file with the same name exists
        if dest_folder.exists() and not dest_folder.is_dir():
            # A file exists with this name, rename it
            old_file = dest_folder
            counter = 1
            new_name = f"{dest_folder.name}_{counter}{dest_folder.suffix}"
            new_path = dest_folder.parent / new_name
            while new_path.exists():
                counter += 1
                new_name = f"{dest_folder.name}_{counter}{dest_folder.suffix}"
                new_path = dest_folder.parent / new_name
            old_file.rename(new_path)
            if log:
                log(f"Renamed conflicting file: {dest_folder.name} -> {new_name}")
        
        dest_folder.mkdir(exist_ok=True)
        
        target = _unique_target_path(dest_folder, entry.name)
        try:
            shutil.move(str(entry), str(target))
            counts[dest_folder_name] += 1
            if log:
                log(f"Moved: {entry.name} -> {dest_folder_name}/")
        except Exception as e:
            if log:
                log(f"Failed to move {entry.name}: {e}")
            counts['errors'] += 1
    return counts

# --- Sorter Logic ---
def sort_files(folder, log=None):
    return organize_folder(folder, log)

# --- PDF Scanner Logic ---
def get_pdf_hash(pdf_path):
    try:
        with open(pdf_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return None

def extract_pdf_metadata(pdf_path):
    if not PDF_AVAILABLE:
        return None
    try:
        reader = pypdf.PdfReader(pdf_path)
        metadata = reader.metadata
        if metadata:
            return {
                'title': metadata.get('/Title', ''),
                'author': metadata.get('/Author', ''),
                'subject': metadata.get('/Subject', ''),
                'pages': len(reader.pages)
            }
    except Exception:
        pass
    return None

def extract_pdf_text_preview(pdf_path, max_chars=500):
    if not PDF_AVAILABLE:
        return ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        if len(reader.pages) > 0:
            text = reader.pages[0].extract_text()
            if text:
                return text[:max_chars].strip()
    except Exception:
        pass
    return ""

def clean_pdf_name(pdf_path, metadata=None):
    if metadata and metadata.get('title'):
        title = metadata['title'].strip()
        title = re.sub(r'[<>:"/\\|?*]', '', title)
        title = re.sub(r'\s+', ' ', title)
        title = title[:100]
        if title:
            return f"{title}.pdf"
    return os.path.basename(pdf_path)

def scan_pdfs_for_duplicates(folder, log=None):
    if not PDF_AVAILABLE:
        if log:
            log("ERROR: pypdf library not installed. Run: pip install pypdf")
        return {}
    
    folder = Path(folder)
    pdf_files = list(folder.glob('*.pdf'))
    
    if log:
        log(f"Found {len(pdf_files)} PDF files to scan...")
    
    hash_groups = {}
    pdf_info = {}
    
    for pdf_path in pdf_files:
        if log:
            log(f"Processing: {pdf_path.name}")
        
        file_hash = get_pdf_hash(str(pdf_path))
        metadata = extract_pdf_metadata(str(pdf_path))
        text_preview = extract_pdf_text_preview(str(pdf_path))
        
        pdf_info[str(pdf_path)] = {
            'hash': file_hash,
            'metadata': metadata,
            'text_preview': text_preview,
            'size': pdf_path.stat().st_size,
            'clean_name': clean_pdf_name(str(pdf_path), metadata)
        }
        
        if file_hash:
            if file_hash not in hash_groups:
                hash_groups[file_hash] = []
            hash_groups[file_hash].append(str(pdf_path))
    
    duplicates = {k: v for k, v in hash_groups.items() if len(v) > 1}
    
    if log:
        log(f"\nFound {len(duplicates)} groups of duplicate PDFs")
        for hash_val, files in duplicates.items():
            log(f"  Duplicate group ({len(files)} files):")
            for f in files:
                log(f"    - {Path(f).name}")
    
    return {
        'pdf_info': pdf_info,
        'duplicates': duplicates,
        'hash_groups': hash_groups
    }

# --- Movie Renamer Logic ---
def clean_movie_filename(filename):
    name = re.sub(r'^[\d_\-\.]+', '', filename)
    base, ext = os.path.splitext(name)

    already_ok = re.match(r'^.+ \((19|20)\d{2}\)( [\w\d]+)?$', base)
    if already_ok:
        return name

    year_match = re.search(r'(19|20)\d{2}', base)
    year = year_match.group(0) if year_match else ''
    quality_match = re.search(r'(4K|2160p|1080p|720p|480p)', base, re.IGNORECASE)
    quality = quality_match.group(0) if quality_match else ''

    clean_base = base
    if year:
        clean_base = re.sub(re.escape(year), '', clean_base)
    if quality:
        clean_base = re.sub(re.escape(quality), '', clean_base, flags=re.IGNORECASE)
    clean_base = re.sub(r'[\._\-]+', ' ', clean_base).strip()
    clean_base = ' '.join(word.capitalize() for word in clean_base.split())

    parts = [clean_base]
    if year:
        parts.append(f'({year})')
    if quality:
        parts.append(quality)
    new_base = ' '.join([p for p in parts if p and p != '()' and p != '() ' and p != ' ()'])
    new_name = new_base.strip() + ext
    return new_name

def rename_movies_in_folder(folder, log=None):
    exts = {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v'}
    count = 0
    for dirpath, dirnames, filenames in os.walk(folder):
        for entry in filenames:
            path = os.path.join(dirpath, entry)
            ext = os.path.splitext(entry)[1].lower()
            if ext not in exts:
                continue
            new_name = clean_movie_filename(entry)
            if new_name != entry:
                new_path = os.path.join(dirpath, new_name)
                counter = 1
                base, ext2 = os.path.splitext(new_name)
                while os.path.exists(new_path):
                    new_path = os.path.join(dirpath, f"{base}_{counter}{ext2}")
                    counter += 1
                try:
                    os.rename(path, new_path)
                    if log:
                        rel_dir = os.path.relpath(dirpath, folder)
                        rel_dir = '' if rel_dir == '.' else rel_dir + '/'
                        log(f"Renamed: {rel_dir}{entry} -> {os.path.basename(new_path)}")
                    count += 1
                except Exception as e:
                    if log:
                        rel_dir = os.path.relpath(dirpath, folder)
                        rel_dir = '' if rel_dir == '.' else rel_dir + '/'
                        log(f"Failed to rename {rel_dir}{entry}: {e}")
    if log:
        log(f"\nRenamed {count} movie files.")
    return count

# --- Photo Sorter Utils ---
def get_image_files(folder):
    if not PIL_AVAILABLE:
        return []
    exts = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.webp'}
    images = []
    for entry in os.listdir(folder):
        path = os.path.join(folder, entry)
        if os.path.isfile(path) and os.path.splitext(entry)[1].lower() in exts:
            images.append(path)
    return images

def move_file(src, dest_folder):
    try:
        filename = os.path.basename(src)
        dest_path = os.path.join(dest_folder, filename)
        counter = 1
        base, ext = os.path.splitext(filename)
        while os.path.exists(dest_path):
            dest_path = os.path.join(dest_folder, f"{base}_{counter}{ext}")
            counter += 1
        shutil.move(src, dest_path)
        return True
    except Exception:
        return False

def delete_file(path):
    try:
        os.remove(path)
        return True
    except Exception:
        return False

# --- GUI ---
class FileOrganizerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AIO File Organizer")
        self.geometry("900x600")
        self.configure(bg="#23272a")
        self.folder = tk.StringVar()
        self.status_var = tk.StringVar()
        self.style = ttk.Style(self)
        self._setup_modern_style()
        self.create_widgets()

    def _setup_modern_style(self):
        self.style.theme_use('clam')
        self.style.configure('.',
            background="#23272a",
            foreground="#f5f6fa",
            font=("Segoe UI", 11)
        )
        self.style.configure('TFrame', background="#23272a")
        self.style.configure('TLabel', background="#23272a", foreground="#f5f6fa", font=("Segoe UI", 11))
        self.style.configure('TNotebook', background="#2c2f33", borderwidth=0)
        self.style.configure('TNotebook.Tab', background="#36393f", foreground="#f5f6fa", font=("Segoe UI", 11, "bold"), padding=[20, 8])
        self.style.map('TNotebook.Tab',
            background=[('selected', '#23272a'), ('active', '#40444b')],
            foreground=[('selected', '#f5f6fa'), ('active', '#f5f6fa')]
        )
        self.style.configure('TButton',
            background="#40444b",
            foreground="#f5f6fa",
            font=("Segoe UI", 11, "bold"),
            borderwidth=0,
            padding=[12, 6]
        )
        self.style.map('TButton',
            background=[('active', '#5865f2'), ('pressed', '#23272a')],
            foreground=[('active', '#f5f6fa'), ('pressed', '#f5f6fa')]
        )
        self.style.configure('TEntry',
            fieldbackground="#2c2f33",
            foreground="#f5f6fa",
            borderwidth=0,
            font=("Segoe UI", 11)
        )
        self.style.configure('Horizontal.TScrollbar', background="#23272a", troughcolor="#2c2f33")
        self.option_add("*TCombobox*Listbox.font", ("Segoe UI", 11))
        self.option_add("*TCombobox*Listbox.background", "#23272a")
        self.option_add("*TCombobox*Listbox.foreground", "#f5f6fa")

    def set_status(self, msg):
        self.status_var.set(msg)
        self.status_bar.update_idletasks()

    def clear_status(self):
        self.status_var.set("")
        self.status_bar.update_idletasks()

    def create_widgets(self):
        tab_control = ttk.Notebook(self, style='TNotebook')
        self.tab_filedump = ttk.Frame(tab_control, style='TFrame')
        self.tab_sorter = ttk.Frame(tab_control, style='TFrame')
        self.tab_organizer = ttk.Frame(tab_control, style='TFrame')
        self.tab_photo_sorter = ttk.Frame(tab_control, style='TFrame')
        self.tab_pdf_scanner = ttk.Frame(tab_control, style='TFrame')
        self.tab_movie_renamer = ttk.Frame(tab_control, style='TFrame')
        self.tab_excel_tools = ttk.Frame(tab_control, style='TFrame')
        
        tab_control.add(self.tab_filedump, text='File Dump')
        tab_control.add(self.tab_sorter, text='Sorter')
        tab_control.add(self.tab_organizer, text='Organizer')
        tab_control.add(self.tab_photo_sorter, text='Photo Sorter')
        tab_control.add(self.tab_pdf_scanner, text='PDF Scanner')
        tab_control.add(self.tab_movie_renamer, text='Movie Renamer')
        tab_control.add(self.tab_excel_tools, text='Excel Tools')
        tab_control.pack(expand=1, fill='both', padx=0, pady=0)

        self.status_bar = ttk.Label(self, textvariable=self.status_var, relief='sunken', anchor='w', background="#2c2f33", foreground="#f5f6fa", font=("Segoe UI", 10))
        self.status_bar.pack(side='bottom', fill='x')
        self.status_var.set("")

        # File Dump tab
        self.dump_source_folder = tk.StringVar()
        self.dump_dest_folder = tk.StringVar()
        frm_dump = ttk.Frame(self.tab_filedump)
        frm_dump.pack(pady=10, anchor='w', fill='x')
        ttk.Label(frm_dump, text="Source Folder:").pack(side='left')
        entry_dump_source = ttk.Entry(frm_dump, textvariable=self.dump_source_folder, width=35)
        entry_dump_source.pack(side='left', padx=5)
        ttk.Button(frm_dump, text="Browse", command=self.browse_dump_source).pack(side='left', padx=5)
        ttk.Label(frm_dump, text="Destination Folder:").pack(side='left', padx=(20,0))
        entry_dump_dest = ttk.Entry(frm_dump, textvariable=self.dump_dest_folder, width=35)
        entry_dump_dest.pack(side='left', padx=5)
        ttk.Button(frm_dump, text="Browse", command=self.browse_dump_dest).pack(side='left', padx=5)

        # Progress bar and time estimate
        self.dump_progress = ttk.Progressbar(self.tab_filedump, orient='horizontal', length=400, mode='determinate')
        self.dump_progress.pack(pady=5)
        self.dump_progress_label = ttk.Label(self.tab_filedump, text="Ready to move files...")
        self.dump_progress_label.pack(pady=2)

        self.dump_log = tk.Text(self.tab_filedump, height=18, 
                                bg="#2c2f33", fg="#f5f6fa", 
                                insertbackground="#f5f6fa")
        self.dump_log.pack(fill='both', expand=True)
        ttk.Button(self.tab_filedump, text="Move all files to destination", command=self.run_filedump).pack(pady=5)

        # Sorter tab
        frm_sorter = ttk.Frame(self.tab_sorter)
        frm_sorter.pack(pady=10, anchor='w', fill='x')
        ttk.Label(frm_sorter, text="Target Folder:").pack(side='left')
        entry_sorter = ttk.Entry(frm_sorter, textvariable=self.folder, width=50)
        entry_sorter.pack(side='left', padx=5)
        ttk.Button(frm_sorter, text="Browse", command=self.browse_folder).pack(side='left')

        self.sorter_log = tk.Text(self.tab_sorter, height=20)
        self.sorter_log.pack(fill='both', expand=True)
        ttk.Button(self.tab_sorter, text="Sort files (by type)", command=self.run_sorter).pack(pady=5)

        # Organizer tab
        self.organizer_source_folder = tk.StringVar()
        self.organizer_dest_folder = tk.StringVar()
        frm_organizer = ttk.Frame(self.tab_organizer)
        frm_organizer.pack(pady=10, anchor='w', fill='x')
        ttk.Label(frm_organizer, text="Source Folder:").pack(side='left')
        entry_organizer_source = ttk.Entry(frm_organizer, textvariable=self.organizer_source_folder, width=35)
        entry_organizer_source.pack(side='left', padx=5)
        ttk.Button(frm_organizer, text="Browse", command=self.browse_organizer_source).pack(side='left', padx=5)
        ttk.Label(frm_organizer, text="Destination Folder:").pack(side='left', padx=(20,0))
        entry_organizer_dest = ttk.Entry(frm_organizer, textvariable=self.organizer_dest_folder, width=35)
        entry_organizer_dest.pack(side='left', padx=5)
        ttk.Button(frm_organizer, text="Browse", command=self.browse_organizer_dest).pack(side='left', padx=5)

        self.organizer_progress = ttk.Progressbar(self.tab_organizer, orient='horizontal', length=400, mode='determinate')
        self.organizer_progress.pack(pady=2)

        self.organizer_log = tk.Text(self.tab_organizer, height=20)
        self.organizer_log.pack(fill='both', expand=True)
        ttk.Button(self.tab_organizer, text="Organize folders", command=self.run_organizer).pack(pady=5)

        # Photo Sorter tab
        self.photo_folder = tk.StringVar()
        frm_photo = ttk.Frame(self.tab_photo_sorter)
        frm_photo.pack(pady=10, anchor='w', fill='x')
        ttk.Label(frm_photo, text="Photo Folder:").pack(side='left')
        entry_photo = ttk.Entry(frm_photo, textvariable=self.photo_folder, width=50)
        entry_photo.pack(side='left', padx=5)
        ttk.Button(frm_photo, text="Browse", command=self.browse_photo_folder).pack(side='left', padx=5)
        ttk.Button(frm_photo, text="Load Images", command=self.load_images).pack(side='left', padx=5)

        self.photo_canvas = tk.Canvas(self.tab_photo_sorter, width=400, height=400, bg='gray')
        self.photo_canvas.pack(pady=10)
        btn_frame_photo = ttk.Frame(self.tab_photo_sorter)
        btn_frame_photo.pack()
        ttk.Button(btn_frame_photo, text="Move...", command=self.move_current_image).pack(side='left', padx=5)
        ttk.Button(btn_frame_photo, text="Delete", command=self.delete_current_image).pack(side='left', padx=5)
        ttk.Button(btn_frame_photo, text="Skip", command=self.next_image).pack(side='left', padx=5)

        self.photo_status = ttk.Label(self.tab_photo_sorter, text="No images loaded.")
        self.photo_status.pack()

        self.images_list = []
        self.current_image_index = 0
        self.current_image_tk = None

        # PDF Scanner tab
        frm_pdf = ttk.Frame(self.tab_pdf_scanner)
        frm_pdf.pack(pady=10, anchor='w', fill='x')
        ttk.Label(frm_pdf, text="Target Folder:").pack(side='left')
        entry_pdf = ttk.Entry(frm_pdf, textvariable=self.folder, width=50)
        entry_pdf.pack(side='left', padx=5)
        ttk.Button(frm_pdf, text="Browse", command=self.browse_folder).pack(side='left')

        self.pdf_log = tk.Text(self.tab_pdf_scanner, height=15, wrap='word')
        self.pdf_log.pack(fill='both', expand=True, pady=5)
        btn_frame_pdf = ttk.Frame(self.tab_pdf_scanner)
        btn_frame_pdf.pack(pady=5)
        ttk.Button(btn_frame_pdf, text="Scan for Duplicates", command=self.scan_pdf_duplicates).pack(side='left', padx=5)
        ttk.Button(btn_frame_pdf, text="Clean PDF Names", command=self.clean_pdf_names).pack(side='left', padx=5)
        ttk.Button(btn_frame_pdf, text="Delete Duplicates", command=self.delete_pdf_duplicates).pack(side='left', padx=5)
        
        self.pdf_results = None

        # Movie Renamer tab
        frm_movie = ttk.Frame(self.tab_movie_renamer)
        frm_movie.pack(pady=10, anchor='w', fill='x')
        ttk.Label(frm_movie, text="Target Folder:").pack(side='left')
        entry_movie = ttk.Entry(frm_movie, textvariable=self.folder, width=50)
        entry_movie.pack(side='left', padx=5)
        ttk.Button(frm_movie, text="Browse", command=self.browse_folder).pack(side='left')

        self.movie_log = tk.Text(self.tab_movie_renamer, height=15, wrap='word')
        self.movie_log.pack(fill='both', expand=True, pady=5)
        btn_frame_movie = ttk.Frame(self.tab_movie_renamer)
        btn_frame_movie.pack(pady=5)
        ttk.Button(btn_frame_movie, text="Rename Movies", command=self.rename_movies).pack(side='left', padx=5)

        # Excel Tools tab
        frm_excel = ttk.Frame(self.tab_excel_tools)
        frm_excel.pack(pady=10, anchor='w', fill='x')
        ttk.Label(frm_excel, text="Target Folder:").pack(side='left')
        entry_excel = ttk.Entry(frm_excel, textvariable=self.folder, width=50)
        entry_excel.pack(side='left', padx=5)
        ttk.Button(frm_excel, text="Browse", command=self.browse_folder).pack(side='left')

        self.excel_log = tk.Text(self.tab_excel_tools, height=15, wrap='word')
        self.excel_log.pack(fill='both', expand=True, pady=5)
        btn_frame_excel = ttk.Frame(self.tab_excel_tools)
        btn_frame_excel.pack(pady=5)
        ttk.Button(btn_frame_excel, text="Sort Excel Files", command=self.sort_excel).pack(side='left', padx=5)
        ttk.Button(btn_frame_excel, text="Find Duplicates", command=self.find_excel_duplicates).pack(side='left', padx=5)
        ttk.Button(btn_frame_excel, text="Rename Excel Files", command=self.rename_excel_files).pack(side='left', padx=5)
        ttk.Button(btn_frame_excel, text="Delete Duplicates", command=self.delete_excel_duplicates).pack(side='left', padx=5)

    # Browser Methods
    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder.set(folder)

    def browse_dump_source(self):
        folder = filedialog.askdirectory()
        if folder:
            self.dump_source_folder.set(folder)

    def browse_dump_dest(self):
        folder = filedialog.askdirectory()
        if folder:
            self.dump_dest_folder.set(folder)

    def browse_organizer_source(self):
        folder = filedialog.askdirectory()
        if folder:
            self.organizer_source_folder.set(folder)

    def browse_organizer_dest(self):
        folder = filedialog.askdirectory()
        if folder:
            self.organizer_dest_folder.set(folder)

    def browse_photo_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.photo_folder.set(folder)

    # File Dump Methods
    def run_filedump(self):
        source = self.dump_source_folder.get()
        dest = self.dump_dest_folder.get()
        if not source or not dest:
            messagebox.showerror("Error", "Please select both source and destination folders.")
            return
        if os.path.abspath(source) == os.path.abspath(dest):
            messagebox.showerror("Error", "Source and destination folders must be different.")
            return
        self.dump_log.delete(1.0, tk.END)
        self.dump_progress.config(value=0)
        self.dump_progress_label.config(text="Scanning files...")
        self.set_status("Scanning files to move...")
        threading.Thread(target=self._run_filedump, args=(source, dest), daemon=True).start()

    def _run_filedump(self, source, dest):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_dump_log_insert(m))
            except RuntimeError:
                pass
        
        def update_progress(current, total, elapsed_time):
            try:
                percent = int((current / total) * 100) if total else 0
                self.after(0, lambda: self.dump_progress.config(value=percent))
                
                # Calculate time estimate
                if current > 0 and elapsed_time > 0:
                    avg_time_per_file = elapsed_time / current
                    remaining_files = total - current
                    estimated_seconds = avg_time_per_file * remaining_files
                    
                    # Format time
                    if estimated_seconds < 60:
                        time_str = f"{int(estimated_seconds)}s remaining"
                    elif estimated_seconds < 3600:
                        minutes = int(estimated_seconds / 60)
                        seconds = int(estimated_seconds % 60)
                        time_str = f"{minutes}m {seconds}s remaining"
                    else:
                        hours = int(estimated_seconds / 3600)
                        minutes = int((estimated_seconds % 3600) / 60)
                        time_str = f"{hours}h {minutes}m remaining"
                    
                    self.after(0, lambda: self.dump_progress_label.config(
                        text=f"Moving files: {current}/{total} ({percent}%) - {time_str}"
                    ))
                else:
                    self.after(0, lambda: self.dump_progress_label.config(
                        text=f"Moving files: {current}/{total} ({percent}%)"
                    ))
            except RuntimeError:
                pass
        
        try:
            self._move_files_to_folder(source, dest, log, update_progress)
            log("\nAll files moved to destination.")
            try:
                self.after(0, lambda: self.dump_progress_label.config(text="Complete!"))
                self.after(0, lambda: self.set_status("File Dump complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.dump_progress_label.config(text="Error occurred"))
                self.after(0, lambda: self.set_status("Error during file dump."))
            except RuntimeError:
                pass

    def _safe_dump_log_insert(self, msg):
        try:
            if self.winfo_exists():
                self.dump_log.insert(tk.END, msg + '\n')
                self.dump_log.see(tk.END)
        except Exception:
            pass

    def _move_files_to_folder(self, source_folder, dest_folder, log=None, progress_callback=None):
        allowed_exts = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.webp',
            '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v',
            '.xls', '.xlsx', '.xlsm', '.csv',
            '.psd', '.psb',
            '.obj', '.fbx', '.stl', '.3ds', '.dae', '.blend', '.gltf', '.glb', '.ply', '.3mf',
            '.doc', '.docx', '.pdf', '.txt', '.zip', '.rar', '.7z',
        }
        
        os.makedirs(dest_folder, exist_ok=True)
        
        # First pass: collect all files to move
        if log:
            log("Scanning source folder recursively...")
        
        files_to_move = []
        for dirpath, dirnames, filenames in os.walk(source_folder):
            # Skip destination folder if it's inside source
            if os.path.abspath(dirpath).startswith(os.path.abspath(dest_folder)):
                continue
            
            for filename in filenames:
                # Skip hidden files
                if filename.startswith('.'):
                    continue
                
                ext = os.path.splitext(filename)[1].lower()
                
                # Skip Python files and files not in allowed extensions
                if ext == '.py' or (ext and ext not in allowed_exts):
                    continue
                
                src_path = os.path.join(dirpath, filename)
                
                # Skip if file doesn't exist (may have been moved already)
                if not os.path.exists(src_path):
                    continue
                
                files_to_move.append((src_path, filename))
        
        total_files = len(files_to_move)
        if log:
            log(f"Found {total_files} files to move.\n")
        
        if total_files == 0:
            if log:
                log("No files found to move.")
            return
        
        # Second pass: move all collected files
        moved_count = 0
        skipped_count = 0
        error_count = 0
        start_time = time.time()
        
        for index, (src_path, filename) in enumerate(files_to_move, 1):
            # Check again if file still exists
            if not os.path.exists(src_path):
                if log:
                    log(f"Skipped (already moved): {filename}")
                skipped_count += 1
                continue
            
            base, ext = os.path.splitext(filename)
            dest_path = os.path.join(dest_folder, filename)
            count = 1
            while os.path.exists(dest_path):
                dest_path = os.path.join(dest_folder, f"{base}_{count}{ext}")
                count += 1
            
            try:
                shutil.move(src_path, dest_path)
                moved_count += 1
                if log and moved_count % 10 == 0:  # Log every 10 files to avoid spam
                    log(f"Moved {moved_count}/{total_files} files...")
            except PermissionError as e:
                if log:
                    log(f"Permission denied: {filename}")
                error_count += 1
            except FileNotFoundError as e:
                if log:
                    log(f"File not found (may have been moved): {filename}")
                skipped_count += 1
            except Exception as e:
                if log:
                    log(f"Failed to move {filename}: {e}")
                error_count += 1
            
            # Update progress
            if progress_callback:
                elapsed = time.time() - start_time
                progress_callback(index, total_files, elapsed)
        
        # Final summary
        if log:
            log(f"\n=== Summary ===")
            log(f"Total files found: {total_files}")
            log(f"Successfully moved: {moved_count}")
            if skipped_count > 0:
                log(f"Skipped: {skipped_count}")
            if error_count > 0:
                log(f"Errors: {error_count}")

    # Photo Sorter Methods
    def load_images(self):
        folder = self.photo_folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a photo folder.")
            return
        if not PIL_AVAILABLE:
            messagebox.showerror("Error", "PIL/Pillow is not installed. Run: pip install Pillow")
            return
        self.images_list = get_image_files(folder)
        if not self.images_list:
            messagebox.showinfo("Info", "No image files found in this folder.")
            return
        self.current_image_index = 0
        self.display_current_image()

    def display_current_image(self):
        if not self.images_list or self.current_image_index >= len(self.images_list):
            self.photo_canvas.delete("all")
            self.photo_status.config(text="No more images.")
            return
        
        img_path = self.images_list[self.current_image_index]
        try:
            img = Image.open(img_path)
            img.thumbnail((400, 400), Image.Resampling.LANCZOS)
            self.current_image_tk = ImageTk.PhotoImage(img)
            self.photo_canvas.delete("all")
            self.photo_canvas.create_image(200, 200, image=self.current_image_tk)
            self.photo_status.config(
                text=f"Image {self.current_image_index + 1} of {len(self.images_list)}: {os.path.basename(img_path)}"
            )
        except Exception as e:
            self.photo_canvas.delete("all")
            self.photo_status.config(text=f"Error loading image: {e}")

    def move_current_image(self):
        if not self.images_list or self.current_image_index >= len(self.images_list):
            return
        dest_folder = filedialog.askdirectory(title="Select destination folder")
        if not dest_folder:
            return
        img_path = self.images_list[self.current_image_index]
        if move_file(img_path, dest_folder):
            self.images_list.pop(self.current_image_index)
            if self.current_image_index >= len(self.images_list):
                self.current_image_index = max(0, len(self.images_list) - 1)
            self.display_current_image()
        else:
            messagebox.showerror("Error", "Failed to move the image.")

    def delete_current_image(self):
        if not self.images_list or self.current_image_index >= len(self.images_list):
            return
        img_path = self.images_list[self.current_image_index]
        if messagebox.askyesno("Confirm Delete", f"Delete {os.path.basename(img_path)}?"):
            if delete_file(img_path):
                self.images_list.pop(self.current_image_index)
                if self.current_image_index >= len(self.images_list):
                    self.current_image_index = max(0, len(self.images_list) - 1)
                self.display_current_image()
            else:
                messagebox.showerror("Error", "Failed to delete the image.")

    def next_image(self):
        if not self.images_list:
            return
        self.current_image_index += 1
        if self.current_image_index >= len(self.images_list):
            self.current_image_index = 0
        self.display_current_image()

    # Sorter Methods
    def run_sorter(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        self.sorter_log.delete(1.0, tk.END)
        self.set_status("Sorting files by type...")
        threading.Thread(target=self._run_sorter, args=(folder,), daemon=True).start()

    def _run_sorter(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_sorter_log_insert(m))
            except RuntimeError:
                pass
        try:
            log("Sorting files by type...\n")
            counts = sort_files(folder, log)
            log(f"\n=== Summary ===")
            for category, count in counts.items():
                if category != 'errors':
                    log(f"{category}: {count} files")
            if counts.get('errors', 0) > 0:
                log(f"Errors: {counts['errors']}")
            try:
                self.after(0, lambda: self.set_status("Sorting complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during sorting."))
            except RuntimeError:
                pass

    def _safe_sorter_log_insert(self, msg):
        try:
            if self.winfo_exists():
                self.sorter_log.insert(tk.END, msg + '\n')
                self.sorter_log.see(tk.END)
        except Exception:
            pass

    # Organizer Methods
    def run_organizer(self):
        source_folder = self.organizer_source_folder.get()
        dest_folder = self.organizer_dest_folder.get()
        if not source_folder or not dest_folder:
            messagebox.showerror("Error", "Please select both source and destination folders.")
            return
        if os.path.abspath(source_folder) == os.path.abspath(dest_folder):
            messagebox.showerror("Error", "Source and destination folders must be different.")
            return
        self.organizer_log.delete(1.0, tk.END)
        self.organizer_progress.config(value=0)
        self.set_status("Organizing folders...")
        threading.Thread(target=self._run_organizer, args=(source_folder, dest_folder), daemon=True).start()

    def _run_organizer(self, source_folder, dest_folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_organizer_log_insert(m))
            except RuntimeError:
                pass
        
        def update_progress(current, total, elapsed_time):
            try:
                percent = int((current / total) * 100) if total else 0
                self.after(0, lambda: self.organizer_progress.config(value=percent))
            except RuntimeError:
                pass
        
        try:
            log("Moving files from source to destination and organizing...\n")
            # FIX: Remove the lambda wrapper - pass update_progress directly
            self._move_files_to_folder(source_folder, dest_folder, log, update_progress)
            log("\nOrganizing files by type...")
            counts = organize_folder(dest_folder, log)
            log(f"\n=== Summary ===")
            for category, count in counts.items():
                if category != 'errors':
                    log(f"{category}: {count} files")
            if counts.get('errors', 0) > 0:
                log(f"Errors: {counts['errors']}")
            try:
                self.after(0, lambda: self.organizer_progress.config(value=100))
                self.after(0, lambda: self.set_status("Organization complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during organization."))
            except RuntimeError:
                pass

    def _safe_organizer_log_insert(self, msg):
        try:
            if self.winfo_exists():
                self.organizer_log.insert(tk.END, msg + '\n')
                self.organizer_log.see(tk.END)
        except Exception:
            pass

    # Excel Tools Methods
    def sort_excel(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        self.excel_log.delete(1.0, tk.END)
        self.set_status("Sorting Excel files...")
        threading.Thread(target=self._sort_excel, args=(folder,), daemon=True).start()

    def _sort_excel(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_excel_log_insert(m))
            except RuntimeError:
                pass
        try:
            log("Sorting Excel files into 'Excel' folder...\n")
            sort_excel_files(folder, log)
            try:
                self.after(0, lambda: self.set_status("Excel sorting complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during Excel sorting."))
            except RuntimeError:
                pass

    def _safe_excel_log_insert(self, msg):
        try:
            if self.winfo_exists():
                self.excel_log.insert(tk.END, msg + '\n')
                self.excel_log.see(tk.END)
        except Exception:
            pass

    def find_excel_duplicates(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        self.excel_log.delete(1.0, tk.END)
        self.set_status("Scanning for Excel duplicates...")
        threading.Thread(target=self._find_excel_duplicates, args=(folder,), daemon=True).start()

    def _find_excel_duplicates(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_excel_log_insert(m))
            except RuntimeError:
                pass
        try:
            log("Scanning for duplicate Excel files...\n")
            scan_excel_duplicates(folder, log)
            try:
                self.after(0, lambda: self.set_status("Excel duplicate scan complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during Excel duplicate scan."))
            except RuntimeError:
                pass

    def rename_excel_files(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        self.excel_log.delete(1.0, tk.END)
        self.set_status("Renaming Excel files...")
        threading.Thread(target=self._rename_excel_files, args=(folder,), daemon=True).start()

    def _rename_excel_files(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_excel_log_insert(m))
            except RuntimeError:
                pass
        try:
            log("Renaming Excel files...\n")
            clean_excel_names(folder, log)
            try:
                self.after(0, lambda: self.set_status("Excel renaming complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during Excel renaming."))
            except RuntimeError:
                pass

    def delete_excel_duplicates(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        self.excel_log.delete(1.0, tk.END)
        self.set_status("Deleting duplicate Excel files...")
        threading.Thread(target=self._delete_excel_duplicates, args=(folder,), daemon=True).start()

    def _delete_excel_duplicates(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_excel_log_insert(m))
            except RuntimeError:
                pass
        try:
            scan_results = scan_excel_duplicates(folder, log)
            duplicates = scan_results['duplicates']
            num_duplicates = sum(len(files) - 1 for files in duplicates.values())
            if not duplicates:
                log("No duplicate Excel files found.")
                try:
                    self.after(0, lambda: self.set_status("No Excel duplicates to delete."))
                except RuntimeError:
                    pass
                return
            if not messagebox.askyesno("Confirm Delete",
                                       f"This will delete {num_duplicates} duplicate Excel files.\n"
                                       "The first file in each group will be kept.\n\nContinue?"):
                try:
                    self.after(0, lambda: self.set_status("Excel duplicate deletion cancelled."))
                except RuntimeError:
                    pass
                return
            deleted_count = delete_excel_duplicates(duplicates, log)
            try:
                self.after(0, lambda: self.set_status(f"Deleted {deleted_count} duplicate Excel files."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during Excel duplicate deletion."))
            except RuntimeError:
                pass

    # Movie Renamer Methods
    def rename_movies(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        self.movie_log.delete(1.0, tk.END)
        self.set_status("Renaming movie files...")
        threading.Thread(target=self._rename_movies, args=(folder,), daemon=True).start()

    def _rename_movies(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_movie_log_insert(m))
            except RuntimeError:
                pass
        try:
            log("Renaming movie files in folder...\n")
            rename_movies_in_folder(folder, log)
            try:
                self.after(0, lambda: self.set_status("Movie renaming complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during movie renaming."))
            except RuntimeError:
                pass

    def _safe_movie_log_insert(self, msg):
        try:
            if self.winfo_exists():
                self.movie_log.insert(tk.END, msg + '\n')
                self.movie_log.see(tk.END)
        except Exception:
            pass

    # PDF Scanner Methods
    def scan_pdf_duplicates(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        self.pdf_log.delete(1.0, tk.END)
        self.set_status("Scanning PDFs for duplicates...")
        threading.Thread(target=self._scan_pdf_duplicates, args=(folder,), daemon=True).start()

    def _scan_pdf_duplicates(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_pdf_log_insert(m))
            except RuntimeError:
                pass
        try:
            log("Scanning PDFs for duplicates...\n")
            self.pdf_results = scan_pdfs_for_duplicates(folder, log)
            log("\nScan complete!")
            try:
                self.after(0, lambda: self.set_status("PDF duplicate scan complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during PDF duplicate scan."))
            except RuntimeError:
                pass

    def _safe_pdf_log_insert(self, msg):
        try:
            if self.winfo_exists():
                self.pdf_log.insert(tk.END, msg + '\n')
                self.pdf_log.see(tk.END)
        except Exception:
            pass

    def clean_pdf_names(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        self.pdf_log.delete(1.0, tk.END)
        self.set_status("Cleaning PDF names...")
        threading.Thread(target=self._clean_pdf_names, args=(folder,), daemon=True).start()

    def _clean_pdf_names(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_pdf_log_insert(m))
            except RuntimeError:
                pass
        try:
            log("Cleaning PDF names based on metadata...\n")
            if not self.pdf_results:
                self.pdf_results = scan_pdfs_for_duplicates(folder, log)
            renamed_count = 0
            for pdf_path, info in self.pdf_results['pdf_info'].items():
                old_name = os.path.basename(pdf_path)
                new_name = info['clean_name']
                cleaned_name = re.sub(r'(_1)+', '', os.path.splitext(new_name)[0]) + '.pdf'
                if not cleaned_name.strip('.pdf'):
                    cleaned_name = new_name
                if old_name != cleaned_name:
                    new_path = os.path.join(os.path.dirname(pdf_path), cleaned_name)
                    counter = 1
                    while os.path.exists(new_path) and new_path != pdf_path:
                        name_without_ext = os.path.splitext(cleaned_name)[0]
                        new_path = os.path.join(os.path.dirname(pdf_path), f"{name_without_ext}_{counter}.pdf")
                        counter += 1
                    try:
                        os.rename(pdf_path, new_path)
                        log(f"Renamed: {old_name} -> {os.path.basename(new_path)}")
                        renamed_count += 1
                    except Exception as e:
                        log(f"Failed to rename {old_name}: {e}")
            log(f"\nRenamed {renamed_count} PDF files.")
            try:
                self.after(0, lambda: self.set_status("PDF renaming complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during PDF renaming."))
            except RuntimeError:
                pass

    def delete_pdf_duplicates(self):
        folder = self.folder.get()
        if not folder:
            messagebox.showerror("Error", "Please select a folder.")
            return
        if not self.pdf_results or not self.pdf_results.get('duplicates'):
            messagebox.showwarning("Warning", "Please scan for duplicates first.")
            return
        num_duplicates = sum(len(files) - 1 for files in self.pdf_results['duplicates'].values())
        if not messagebox.askyesno("Confirm Delete", 
                                   f"This will delete {num_duplicates} duplicate PDF files.\n"
                                   "The first file in each group will be kept.\n\n"
                                   "Continue?"):
            return
        self.pdf_log.delete(1.0, tk.END)
        self.set_status("Deleting duplicate PDFs...")
        threading.Thread(target=self._delete_pdf_duplicates, args=(folder,), daemon=True).start()

    def _delete_pdf_duplicates(self, folder):
        def log(msg):
            try:
                self.after(0, lambda m=msg: self._safe_pdf_log_insert(m))
            except RuntimeError:
                pass
        try:
            log("Deleting duplicate PDFs...\n")
            deleted_count = 0
            for hash_val, files in self.pdf_results['duplicates'].items():
                keep_file = files[0]
                log(f"Keeping: {os.path.basename(keep_file)}")
                for duplicate_file in files[1:]:
                    try:
                        os.remove(duplicate_file)
                        log(f"  Deleted: {os.path.basename(duplicate_file)}")
                        deleted_count += 1
                    except Exception as e:
                        log(f"  Failed to delete {os.path.basename(duplicate_file)}: {e}")
                log("")
            log(f"Deleted {deleted_count} duplicate PDF files.")
            self.pdf_results = None
            try:
                self.after(0, lambda: self.set_status("PDF duplicate deletion complete."))
            except RuntimeError:
                pass
        except Exception as e:
            log(f"Error: {e}")
            try:
                self.after(0, lambda: self.set_status("Error during PDF duplicate deletion."))
            except RuntimeError:
                pass


if __name__ == "__main__":
    app = FileOrganizerGUI()
    app.mainloop()