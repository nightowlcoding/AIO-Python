import os
import shutil
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, send_file
from collections import Counter
import hashlib
import re
import time
import threading
from datetime import datetime
import json

# --- Optional dependencies ---
try:
    import pypdf
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    from PIL import Image, UnidentifiedImageError
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

# Global variables for tracking operations
operation_status = {}
operation_logs = {}

# --- Helper Functions ---
EXTENSION_MAP = {
    'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.webp'},
    'videos': {'.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v'},
    'pdf': {'.pdf'},
    'excel': {'.xls', '.xlsx', '.xlsm', '.csv'},
    'words': {'.doc', '.docx'},
    'powerpoint': {'.ppt', '.pptx'},
}
DEFAULT_FOLDER = 'Untitled'

def log_operation(operation_id, message):
    if operation_id not in operation_logs:
        operation_logs[operation_id] = []
    operation_logs[operation_id].append({
        'timestamp': datetime.now().isoformat(),
        'message': message
    })

def update_operation_status(operation_id, status, progress=None, message=None):
    operation_status[operation_id] = {
        'status': status,
        'progress': progress,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }

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

def organize_folder(folder, operation_id=None):
    folder = Path(folder)
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")
    
    counts = Counter()
    entries = [e for e in folder.iterdir() if not e.is_dir()]
    total = len(entries)
    
    for idx, entry in enumerate(entries, 1):
        ext = entry.suffix.lower()
        dest_folder_name = _determine_folder(ext)
        dest_folder = folder / dest_folder_name
        
        if dest_folder.exists() and not dest_folder.is_dir():
            old_file = dest_folder
            counter = 1
            new_name = f"{dest_folder.name}_{counter}{dest_folder.suffix}"
            new_path = dest_folder.parent / new_name
            while new_path.exists():
                counter += 1
                new_name = f"{dest_folder.name}_{counter}{dest_folder.suffix}"
                new_path = dest_folder.parent / new_name
            old_file.rename(new_path)
            if operation_id:
                log_operation(operation_id, f"Renamed conflicting file: {dest_folder.name} -> {new_name}")
        
        dest_folder.mkdir(exist_ok=True)
        target = _unique_target_path(dest_folder, entry.name)
        
        try:
            shutil.move(str(entry), str(target))
            counts[dest_folder_name] += 1
            if operation_id:
                log_operation(operation_id, f"Moved: {entry.name} -> {dest_folder_name}/")
                update_operation_status(operation_id, 'processing', int((idx / total) * 100), 
                                      f"Processing {idx}/{total} files")
        except Exception as e:
            if operation_id:
                log_operation(operation_id, f"Failed to move {entry.name}: {e}")
            counts['errors'] += 1
    
    return counts

def clean_excel_filename(filename):
    name = re.sub(r'^[\d_\-\.]+', '', filename)
    base, ext = os.path.splitext(name)
    clean_base = re.sub(r'[\._\-]+', ' ', base).strip()
    clean_base = ' '.join(word.capitalize() for word in clean_base.split())
    return clean_base + ext

def sort_excel_files(folder, operation_id=None):
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
                if operation_id:
                    log_operation(operation_id, f"Moved: {entry} -> Excel/")
                count += 1
            except Exception as e:
                if operation_id:
                    log_operation(operation_id, f"Failed to move {entry}: {e}")
    
    if operation_id:
        log_operation(operation_id, f"Moved {count} Excel files.")
    return count

def get_excel_hash(file_path):
    try:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return None

def scan_excel_duplicates(folder, operation_id=None):
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
    
    if operation_id:
        log_operation(operation_id, f"Found {len(excel_files)} Excel files to scan...")
        log_operation(operation_id, f"Found {len(duplicates)} groups of duplicate Excel files")
    
    return {'duplicates': duplicates, 'hash_groups': hash_groups, 'excel_files': excel_files}

def clean_excel_names(folder, operation_id=None):
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
                    if operation_id:
                        log_operation(operation_id, f"Renamed: {entry} -> {os.path.basename(new_path)}")
                    count += 1
                except Exception as e:
                    if operation_id:
                        log_operation(operation_id, f"Failed to rename {entry}: {e}")
    
    if operation_id:
        log_operation(operation_id, f"Renamed {count} Excel files.")
    return count

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
    new_base = ' '.join([p for p in parts if p and p != '()'])
    new_name = new_base.strip() + ext
    return new_name

def rename_movies_in_folder(folder, operation_id=None):
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
                    if operation_id:
                        log_operation(operation_id, f"Renamed: {entry} -> {os.path.basename(new_path)}")
                    count += 1
                except Exception as e:
                    if operation_id:
                        log_operation(operation_id, f"Failed to rename {entry}: {e}")
    
    if operation_id:
        log_operation(operation_id, f"Renamed {count} movie files.")
    return count

def move_all_files_to_folder(source_folder, dest_folder, operation_id=None):
    """Extract all files from source folder (including subdirectories) and move to destination folder."""
    allowed_exts = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.heic', '.webp',
        '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.flv', '.m4v',
        '.xls', '.xlsx', '.xlsm', '.csv',
        '.psd', '.psb',
        '.obj', '.fbx', '.stl', '.3ds', '.dae', '.blend', '.gltf', '.glb', '.ply', '.3mf',
        '.doc', '.docx', '.pdf', '.txt', '.zip', '.rar', '.7z',
    }
    
    # Create destination and check permissions
    try:
        os.makedirs(dest_folder, exist_ok=True)
        # Test write permission
        test_file = os.path.join(dest_folder, '.permission_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
    except PermissionError:
        if operation_id:
            log_operation(operation_id, "❌ ERROR: No write permission to destination folder!")
            log_operation(operation_id, f"❌ Cannot write to: {dest_folder}")
            log_operation(operation_id, "")
            log_operation(operation_id, "💡 Try these solutions:")
            log_operation(operation_id, "1. Choose a different destination folder (like Desktop or Documents)")
            log_operation(operation_id, "2. Create a new folder in your home directory")
            log_operation(operation_id, "3. Check folder permissions in Finder (Get Info)")
        raise PermissionError(f"No write permission to destination: {dest_folder}")
    except Exception as e:
        if operation_id:
            log_operation(operation_id, f"❌ ERROR: Cannot create destination folder: {e}")
        raise
    
    # First pass: collect all files to move
    if operation_id:
        log_operation(operation_id, "Scanning source folder recursively...")
        update_operation_status(operation_id, 'processing', 5, 'Scanning files...')
    
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
            
            # Skip if file doesn't exist
            if not os.path.exists(src_path):
                continue
            
            files_to_move.append((src_path, filename))
    
    total_files = len(files_to_move)
    if operation_id:
        log_operation(operation_id, f"📊 Found {total_files} files to move.")
        log_operation(operation_id, "")
        log_operation(operation_id, "Starting file transfer...")
        log_operation(operation_id, "")
    
    if total_files == 0:
        if operation_id:
            log_operation(operation_id, "No files found to move.")
        return 0
    
    # Second pass: move all collected files with detailed logging
    moved_count = 0
    skipped_count = 0
    error_count = 0
    last_progress_shown = 0
    
    for index, (src_path, filename) in enumerate(files_to_move, 1):
        # Check again if file still exists
        if not os.path.exists(src_path):
            if operation_id:
                log_operation(operation_id, f"⚠️ Skipped (already moved): {filename}")
            skipped_count += 1
            continue
        
        base, ext = os.path.splitext(filename)
        dest_path = os.path.join(dest_folder, filename)
        count = 1
        original_filename = filename
        while os.path.exists(dest_path):
            filename = f"{base}_{count}{ext}"
            dest_path = os.path.join(dest_folder, filename)
            count += 1
        
        try:
            shutil.move(src_path, dest_path)
            moved_count += 1
            
            # Log each file transfer with details
            if operation_id:
                # Show renamed files differently
                if filename != original_filename:
                    log_operation(operation_id, f"✓ [{moved_count}/{total_files}] {original_filename} → {filename}")
                else:
                    log_operation(operation_id, f"✓ [{moved_count}/{total_files}] {filename}")
                
        except PermissionError as e:
            if operation_id:
                log_operation(operation_id, f"❌ [{index}/{total_files}] Permission denied: {filename}")
                log_operation(operation_id, f"   ↳ File location: {os.path.dirname(src_path)}")
            error_count += 1
        except FileNotFoundError as e:
            if operation_id:
                log_operation(operation_id, f"⚠️ [{index}/{total_files}] File not found: {filename}")
            skipped_count += 1
        except OSError as e:
            if operation_id:
                if "Operation not permitted" in str(e):
                    log_operation(operation_id, f"❌ [{index}/{total_files}] Protected file: {filename}")
                    log_operation(operation_id, f"   ↳ System or locked file - cannot move")
                else:
                    log_operation(operation_id, f"❌ [{index}/{total_files}] OS Error: {filename} - {e}")
            error_count += 1
        except Exception as e:
            if operation_id:
                log_operation(operation_id, f"❌ [{index}/{total_files}] Failed: {filename} - {e}")
            error_count += 1
        
        # Update progress and show progress bar every 10%
        if operation_id:
            progress = int(((index / total_files) * 90) + 10)  # 10-100%
            update_operation_status(operation_id, 'processing', progress, f"Moving: {index}/{total_files}")
            
            # Show visual progress bar every 10% or at milestones
            progress_percent = int((index / total_files) * 100)
            if progress_percent >= last_progress_shown + 10 or index == total_files:
                # Create visual progress bar
                bar_length = 20
                filled = int((progress_percent / 100) * bar_length)
                bar = '█' * filled + '░' * (bar_length - filled)
                log_operation(operation_id, f"")
                log_operation(operation_id, f"[{bar}] {progress_percent}% - {index}/{total_files} files")
                log_operation(operation_id, f"")
                last_progress_shown = progress_percent
    
    # Final summary
    if operation_id:
        log_operation(operation_id, "")
        log_operation(operation_id, "=" * 50)
        log_operation(operation_id, "✅ TRANSFER COMPLETE")
        log_operation(operation_id, "=" * 50)
        log_operation(operation_id, f"📁 Total files processed: {total_files}")
        log_operation(operation_id, f"✓ Successfully moved: {moved_count}")
        if skipped_count > 0:
            log_operation(operation_id, f"⚠️ Skipped: {skipped_count}")
        if error_count > 0:
            log_operation(operation_id, f"❌ Errors: {error_count}")
            log_operation(operation_id, "")
            log_operation(operation_id, "💡 Common fixes for permission errors:")
            log_operation(operation_id, "• Use folders in your home directory (Desktop, Documents, Downloads)")
            log_operation(operation_id, "• Avoid system folders (/System, /Library, /Applications)")
            log_operation(operation_id, "• Avoid iCloud folders if syncing")
            log_operation(operation_id, "• Check file ownership in Finder (Get Info)")
        log_operation(operation_id, f"")
        log_operation(operation_id, f"📂 Destination: {dest_folder}")
    
    return moved_count

# --- Routes ---
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/organize', methods=['POST'])
def api_organize():
    data = request.json
    folder = data.get('folder')
    
    if not folder or not os.path.exists(folder):
        return jsonify({'error': 'Invalid folder path'}), 400
    
    operation_id = f"organize_{int(time.time())}"
    
    def run_organize():
        try:
            update_operation_status(operation_id, 'processing', 0, 'Starting organization...')
            log_operation(operation_id, 'Starting file organization...')
            counts = organize_folder(folder, operation_id)
            log_operation(operation_id, f"Organization complete: {dict(counts)}")
            update_operation_status(operation_id, 'complete', 100, 'Organization complete!')
        except Exception as e:
            log_operation(operation_id, f"Error: {str(e)}")
            update_operation_status(operation_id, 'error', 0, str(e))
    
    thread = threading.Thread(target=run_organize, daemon=True)
    thread.start()
    
    return jsonify({'operation_id': operation_id})

@app.route('/api/excel/sort', methods=['POST'])
def api_excel_sort():
    data = request.json
    folder = data.get('folder')
    
    if not folder or not os.path.exists(folder):
        return jsonify({'error': 'Invalid folder path'}), 400
    
    operation_id = f"excel_sort_{int(time.time())}"
    
    def run_sort():
        try:
            update_operation_status(operation_id, 'processing', 0, 'Sorting Excel files...')
            count = sort_excel_files(folder, operation_id)
            update_operation_status(operation_id, 'complete', 100, f'Sorted {count} Excel files')
        except Exception as e:
            log_operation(operation_id, f"Error: {str(e)}")
            update_operation_status(operation_id, 'error', 0, str(e))
    
    thread = threading.Thread(target=run_sort, daemon=True)
    thread.start()
    
    return jsonify({'operation_id': operation_id})

@app.route('/api/excel/scan-duplicates', methods=['POST'])
def api_excel_scan_duplicates():
    data = request.json
    folder = data.get('folder')
    
    if not folder or not os.path.exists(folder):
        return jsonify({'error': 'Invalid folder path'}), 400
    
    operation_id = f"excel_scan_{int(time.time())}"
    
    def run_scan():
        try:
            update_operation_status(operation_id, 'processing', 0, 'Scanning for duplicates...')
            results = scan_excel_duplicates(folder, operation_id)
            num_duplicates = len(results['duplicates'])
            update_operation_status(operation_id, 'complete', 100, 
                                  f'Found {num_duplicates} groups of duplicates')
        except Exception as e:
            log_operation(operation_id, f"Error: {str(e)}")
            update_operation_status(operation_id, 'error', 0, str(e))
    
    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()
    
    return jsonify({'operation_id': operation_id})

@app.route('/api/excel/rename', methods=['POST'])
def api_excel_rename():
    data = request.json
    folder = data.get('folder')
    
    if not folder or not os.path.exists(folder):
        return jsonify({'error': 'Invalid folder path'}), 400
    
    operation_id = f"excel_rename_{int(time.time())}"
    
    def run_rename():
        try:
            update_operation_status(operation_id, 'processing', 0, 'Renaming Excel files...')
            count = clean_excel_names(folder, operation_id)
            update_operation_status(operation_id, 'complete', 100, f'Renamed {count} Excel files')
        except Exception as e:
            log_operation(operation_id, f"Error: {str(e)}")
            update_operation_status(operation_id, 'error', 0, str(e))
    
    thread = threading.Thread(target=run_rename, daemon=True)
    thread.start()
    
    return jsonify({'operation_id': operation_id})

@app.route('/api/movies/rename', methods=['POST'])
def api_movies_rename():
    data = request.json
    folder = data.get('folder')
    
    if not folder or not os.path.exists(folder):
        return jsonify({'error': 'Invalid folder path'}), 400
    
    operation_id = f"movies_rename_{int(time.time())}"
    
    def run_rename():
        try:
            update_operation_status(operation_id, 'processing', 0, 'Renaming movie files...')
            count = rename_movies_in_folder(folder, operation_id)
            update_operation_status(operation_id, 'complete', 100, f'Renamed {count} movie files')
        except Exception as e:
            log_operation(operation_id, f"Error: {str(e)}")
            update_operation_status(operation_id, 'error', 0, str(e))
    
    thread = threading.Thread(target=run_rename, daemon=True)
    thread.start()
    
    return jsonify({'operation_id': operation_id})

@app.route('/api/extract-files', methods=['POST'])
def extract_files():
    try:
        data = request.json
        source_folder = data.get('source_folder')
        dest_folder = data.get('dest_folder')
        
        if not source_folder or not dest_folder:
            return jsonify({'error': 'Both source and destination folders are required'}), 400
        
        if not os.path.exists(source_folder):
            return jsonify({'error': f'Source folder not found: {source_folder}'}), 400
        
        if os.path.abspath(source_folder) == os.path.abspath(dest_folder):
            return jsonify({'error': 'Source and destination folders must be different'}), 400
        
        operation_id = f"extract_{int(time.time() * 1000)}"
        operation_logs[operation_id] = []
        update_operation_status(operation_id, 'processing', 0, 'Starting file extraction...')
        
        def run_extraction():
            try:
                log_operation(operation_id, f"Extracting files from: {source_folder}")
                log_operation(operation_id, f"Destination: {dest_folder}")
                log_operation(operation_id, "")
                
                moved_count = move_all_files_to_folder(source_folder, dest_folder, operation_id)
                
                update_operation_status(operation_id, 'complete', 100, 
                    f'Successfully moved {moved_count} files')
                log_operation(operation_id, "")
                log_operation(operation_id, "File extraction complete!")
            except Exception as e:
                update_operation_status(operation_id, 'error', 0, str(e))
                log_operation(operation_id, f"Error: {e}")
        
        thread = threading.Thread(target=run_extraction)
        thread.daemon = True
        thread.start()
        
        return jsonify({'operation_id': operation_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/status/<operation_id>')
def api_status(operation_id):
    status = operation_status.get(operation_id, {'status': 'not_found'})
    logs = operation_logs.get(operation_id, [])
    return jsonify({'status': status, 'logs': logs})

@app.route('/favicon.ico')
def favicon():
    return '', 204

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AIO File Organizer - Web Edition</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            overflow: hidden;
        }
        
        .header {
            background: #2d3748;
            color: white;
            padding: 40px 30px;
            text-align: center;
            border-bottom: 1px solid #e2e8f0;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 600;
            letter-spacing: -0.5px;
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.85;
            font-weight: 400;
        }
        
        .tabs {
            display: flex;
            background: #ffffff;
            border-bottom: 1px solid #e2e8f0;
            overflow-x: auto;
        }
        
        .tab {
            padding: 18px 28px;
            cursor: pointer;
            background: transparent;
            border: none;
            font-size: 0.95em;
            font-weight: 500;
            color: #64748b;
            transition: all 0.2s;
            white-space: nowrap;
            border-bottom: 2px solid transparent;
        }
        
        .tab:hover {
            background: #f8fafc;
            color: #334155;
        }
        
        .tab.active {
            background: transparent;
            color: #1e293b;
            border-bottom: 2px solid #3b82f6;
        }
        
        .tab-content {
            display: none;
            padding: 30px;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .section {
            background: #f8fafc;
            padding: 28px;
            border-radius: 12px;
            margin-bottom: 20px;
            border: 1px solid #e2e8f0;
        }
        
        .section h3 {
            color: #1e293b;
            margin-bottom: 18px;
            font-size: 1.3em;
            font-weight: 600;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #475569;
            font-size: 0.95em;
        }
        
        .form-group input {
            width: 100%;
            padding: 12px 16px;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            font-size: 0.95em;
            transition: all 0.2s;
            background: white;
        }
        
        .form-group input:focus {
            outline: none;
            border-color: #3b82f6;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
        }
        
        .btn {
            background: #3b82f6;
            color: white;
            border: none;
            padding: 11px 24px;
            border-radius: 8px;
            font-size: 0.95em;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            margin-right: 10px;
            margin-bottom: 10px;
        }
        
        .btn:hover {
            background: #2563eb;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
        }
        
        .btn:active {
            transform: scale(0.98);
        }
        
        .btn-secondary {
            background: #64748b;
        }
        
        .btn-secondary:hover {
            backgrou8px;
            background: #e2e8f0;
            border-radius: 4px;
            overflow: hidden;
            margin: 20px 0;
        }
        
        .progress-fill {
            height: 100%;
            background: #3b82f6;
            width: 0%;
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            color: transparent;
            font-weight: 500;
            font-size: 0.85em;
        }
        
        .log-box {
            background: #1e293b;
            color: #cbd5e1;
            padding: 20px;
            border-radius: 10px;
            font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
            font-size: 0.9em;
            max-height: 400px;
            overflow-y: auto;
            margin-top: 20px;
            border: 1px solid #334155;
        }
        
        .log-entry {
            margin-bottom: 4px;
            line-height: 1.6;
        }
        
        .status-badge {
            display: inline-block;
            padding: 6px 14px;
            border-radius: 6px;
            font-weight: 500;
            margin: 10px 0;
            font-size: 0.9em;
        }
        
        .status-processing {
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fde68a;
        }
        
        .status-complete {
            background: #d1fae5;
            color: #065f46;
            border: 1px solid #a7f3d0;
        }
        
        .status-error {
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fecaca 0;
        }
        
        .status-processing {
            background: #ffc107;
            color: #000;
        }
        
        .status-complete {
            background: #28a745;
            color: white;
        }
        
        .status-error {
            background: #dc3545;
            color: white;
        }
        
        .feature-grid {
            display: grid;
            grid-templ4px;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            transition: all 0.2s;
        }
        
        .feature-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.06);
            border-color: #cbd5e1;
        }
        
        .feature-card h4 {
            color: #1e293b;
            margin-bottom: 10px;
            font-weight: 600;
        }
        
        .feature-card p {
            color: #64748b;
            line-height: 1.6
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .feature-card h4 {
            color: #667eea;
            margin-bottom: 10px;
        }
        
        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8em;
            }
            
            .tab {
                padding: 15px 20px;
                font-size: 0.9em;
            }
            
            .tab-content {
                padding: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🗂️ AIO File Organizer</h1>
            <p>Professional Web-Based File Management System</p>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="switchTab('extractor')">📤 Extract Files</button>
            <button class="tab" onclick="switchTab('organizer')">📁 Organizer</button>
            <button class="tab" onclick="switchTab('excel')">📊 Excel Tools</button>
            <button class="tab" onclick="switchTab('movies')">🎬 Movie Renamer</button>
            <button class="tab" onclick="switchTab('about')">ℹ️ About</button>
        </div>
        
        <!-- Extract Files Tab -->
        <div id="extractor" class="tab-content active">
            <div class="section">
                <h3>📤 File Extractor</h3>
                <p style="margin-bottom: 20px;">Extract all files from a root folder (including subdirectories) and move them to a destination folder for further organization.</p>
                
                <div class="form-group">
                    <label for="extract-source">📂 Source Folder (to extract from):</label>
                    <input type="text" id="extract-source" placeholder="/path/to/source/folder" />
                    <small style="color: #64748b; display: block; margin-top: 5px;">💡 Tip: Drag folder from Finder to Terminal, then copy the path</small>
                </div>
                
                <div class="form-group">
                    <label for="extract-dest">📁 Destination Folder (where files will go):</label>
                    <input type="text" id="extract-dest" placeholder="/path/to/destination/folder" />
                    <small style="color: #64748b; display: block; margin-top: 5px;">💡 Tip: Drag folder from Finder to Terminal, then copy the path</small>
                </div>
                
                <button class="btn" onclick="runExtractor()">🚀 Extract All Files</button>
                
                <div id="extractor-status"></div>
                <div class="progress-bar" style="display: none;" id="extractor-progress-bar">
                    <div class="progress-fill" id="extractor-progress-fill">0%</div>
                </div>
                <div class="log-box" id="extractor-log" style="display: none;"></div>
            </div>
            
            <div class="section" style="margin-top: 20px;">
                <h4>ℹ️ How it works:</h4>
                <ul style="margin-left: 20px; margin-top: 10px; color: #64748b; line-height: 1.8;">
                    <li>Recursively scans the source folder and all subdirectories</li>
                    <li>Moves all files to the destination folder (subdirectories are flattened)</li>
                    <li>Automatically handles duplicate filenames by adding numbers</li>
                    <li>Skips Python files (.py) and hidden files</li>
                    <li>Perfect for consolidating files before organizing them</li>
                </ul>
            </div>
        </div>
        
        <!-- Organizer Tab -->
        <div id="organizer" class="tab-content">
            <div class="section">
                <h3>File Organizer</h3>
                <p style="margin-bottom: 20px;">Automatically organize files into categorized folders based on file type.</p>
                
                <div class="form-group">
                    <label for="organizer-folder">📂 Select Folder to Organize:</label>
                    <input type="text" id="organizer-folder" placeholder="/path/to/folder" />
                    <small style="color: #64748b; display: block; margin-top: 5px;">💡 Tip: Drag folder from Finder to Terminal, then copy the path</small>
                </div>
                
                <button class="btn" onclick="runOrganizer()">🚀 Organize Files</button>
                
                <div id="organizer-status"></div>
                <div class="progress-bar" style="display: none;" id="organizer-progress-bar">
                    <div class="progress-fill" id="organizer-progress-fill">0%</div>
                </div>
                <div class="log-box" id="organizer-log" style="display: none;"></div>
            </div>
        </div>
        
        <!-- Excel Tools Tab -->
        <div id="excel" class="tab-content">
            <div class="section">
                <h3>Excel File Tools</h3>
                <p style="margin-bottom: 20px;">Sort, scan for duplicates, and clean Excel file names.</p>
                
                <div class="form-group">
                    <label for="excel-folder">📂 Select Folder with Excel Files:</label>
                    <input type="text" id="excel-folder" placeholder="/path/to/folder" />
                </div>
                
                <button class="btn" onclick="sortExcel()">📁 Sort Excel Files</button>
                <button class="btn btn-secondary" onclick="scanExcelDuplicates()">🔍 Find Duplicates</button>
                <button class="btn btn-secondary" onclick="renameExcel()">✏️ Rename Files</button>
                
                <div id="excel-status"></div>
                <div class="progress-bar" style="display: none;" id="excel-progress-bar">
                    <div class="progress-fill" id="excel-progress-fill">0%</div>
                </div>
                <div class="log-box" id="excel-log" style="display: none;"></div>
            </div>
        </div>
        
        <!-- Movies Tab -->
        <div id="movies" class="tab-content">
            <div class="section">
                <h3>Movie File Renamer</h3>
                <p style="margin-bottom: 20px;">Clean and standardize movie file names with proper formatting.</p>
                
                <div class="form-group">
                    <label for="movies-folder">📂 Select Folder with Movie Files:</label>
                    <input type="text" id="movies-folder" placeholder="/path/to/folder" />
                </div>
                
                <button class="btn" onclick="renameMovies()">🎬 Rename Movies</button>
                
                <div id="movies-status"></div>
                <div class="progress-bar" style="display: none;" id="movies-progress-bar">
                    <div class="progress-fill" id="movies-progress-fill">0%</div>
                </div>
                <div class="log-box" id="movies-log" style="display: none;"></div>
            </div>
        </div>
        
        <!-- About Tab -->
        <div id="about" class="tab-content">
            <div class="section">
                <h3>About AIO File Organizer</h3>
                <p style="margin-bottom: 20px;">A comprehensive web-based file management solution.</p>
                
                <div class="feature-grid">
                    <div class="feature-card">
                        <h4>📁 Smart Organization</h4>
                        <p>Automatically categorize files by type into organized folders.</p>
                    </div>
                    <div class="feature-card">
                        <h4>📊 Excel Management</h4>
                        <p>Sort, scan for duplicates, and clean Excel file names.</p>
                    </div>
                    <div class="feature-card">
                        <h4>🎬 Movie Renaming</h4>
                        <p>Standardize movie file names with year and quality tags.</p>
                    </div>
                    <div class="feature-card">
                        <h4>⚡ Real-time Progress</h4>
                        <p>Watch operations in real-time with live progress updates.</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        function switchTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            
            // Show selected tab
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
        }
        
        function pollStatus(operationId, statusElement, progressBar, progressFill, logBox) {
            const interval = setInterval(async () => {
                try {
                    const response = await fetch('/api/status/' + operationId);
                    const data = await response.json();
                    
                    const status = data.status;
                    const logs = data.logs;
                    
                    // Update status badge
                    let statusClass = 'status-processing';
                    if (status.status === 'complete') statusClass = 'status-complete';
                    if (status.status === 'error') statusClass = 'status-error';
                    
                    statusElement.innerHTML = '<div class="status-badge ' + statusClass + '">' + 
                        (status.message || status.status) + '</div>';
                    
                    // Update progress bar
                    if (status.progress !== null && status.progress !== undefined) {
                        progressBar.style.display = 'block';
                        progressFill.style.width = status.progress + '%';
                        progressFill.textContent = status.progress + '%';
                    }
                    
                    // Update logs
                    if (logs.length > 0) {
                        logBox.style.display = 'block';
                        logBox.innerHTML = logs.map(log => 
                            '<div class="log-entry">' + log.message + '</div>'
                        ).join('');
                        logBox.scrollTop = logBox.scrollHeight;
                    }
                    
                    // Stop polling if complete or error
                    if (status.status === 'complete' || status.status === 'error') {
                        clearInterval(interval);
                    }
                } catch (error) {
                    console.error('Error polling status:', error);
                }
            }, 500);
        }
        
        async function runExtractor() {
            const sourceFolder = document.getElementById('extract-source').value;
            const destFolder = document.getElementById('extract-dest').value;
            
            if (!sourceFolder || !destFolder) {
                alert('Please enter both source and destination folder paths');
                return;
            }
            
            if (sourceFolder === destFolder) {
                alert('Source and destination folders must be different');
                return;
            }
            
            const statusEl = document.getElementById('extractor-status');
            const progressBar = document.getElementById('extractor-progress-bar');
            const progressFill = document.getElementById('extractor-progress-fill');
            const logBox = document.getElementById('extractor-log');
            
            statusEl.innerHTML = '<div class="status-badge status-processing">Starting...</div>';
            progressBar.style.display = 'none';
            logBox.innerHTML = '';
            
            try {
                const response = await fetch('/api/extract-files', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        source_folder: sourceFolder,
                        dest_folder: destFolder
                    })
                });
                
                const data = await response.json();
                
                if (data.error) {
                    statusEl.innerHTML = `<div class="status-badge status-error">Error: ${data.error}</div>`;
                    return;
                }
                
                if (data.operation_id) {
                    pollStatus(data.operation_id, statusEl, progressBar, progressFill, logBox);
                }
            } catch (error) {
                statusEl.innerHTML = `<div class="status-badge status-error">Error: ${error.message}</div>`;
            }
        }
        
        async function runOrganizer() {
            const folder = document.getElementById('organizer-folder').value;
            if (!folder) {
                alert('Please enter a folder path');
                return;
            }
            
            const statusEl = document.getElementById('organizer-status');
            const progressBar = document.getElementById('organizer-progress-bar');
            const progressFill = document.getElementById('organizer-progress-fill');
            const logBox = document.getElementById('organizer-log');
            
            statusEl.innerHTML = '<div class="status-badge status-processing">Starting...</div>';
            progressBar.style.display = 'none';
            logBox.innerHTML = '';
            
            try {
                const response = await fetch('/api/organize', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({folder: folder})
                });
                
                const data = await response.json();
                if (data.operation_id) {
                    pollStatus(data.operation_id, statusEl, progressBar, progressFill, logBox);
                }
            } catch (error) {
                statusEl.innerHTML = '<div class="status-badge status-error">Error: ' + error.message + '</div>';
            }
        }
        
        async function sortExcel() {
            const folder = document.getElementById('excel-folder').value;
            if (!folder) {
                alert('Please enter a folder path');
                return;
            }
            
            const statusEl = document.getElementById('excel-status');
            const progressBar = document.getElementById('excel-progress-bar');
            const progressFill = document.getElementById('excel-progress-fill');
            const logBox = document.getElementById('excel-log');
            
            statusEl.innerHTML = '<div class="status-badge status-processing">Starting...</div>';
            
            try {
                const response = await fetch('/api/excel/sort', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({folder: folder})
                });
                
                const data = await response.json();
                if (data.operation_id) {
                    pollStatus(data.operation_id, statusEl, progressBar, progressFill, logBox);
                }
            } catch (error) {
                statusEl.innerHTML = '<div class="status-badge status-error">Error: ' + error.message + '</div>';
            }
        }
        
        async function scanExcelDuplicates() {
            const folder = document.getElementById('excel-folder').value;
            if (!folder) {
                alert('Please enter a folder path');
                return;
            }
            
            const statusEl = document.getElementById('excel-status');
            const progressBar = document.getElementById('excel-progress-bar');
            const progressFill = document.getElementById('excel-progress-fill');
            const logBox = document.getElementById('excel-log');
            
            statusEl.innerHTML = '<div class="status-badge status-processing">Scanning...</div>';
            
            try {
                const response = await fetch('/api/excel/scan-duplicates', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({folder: folder})
                });
                
                const data = await response.json();
                if (data.operation_id) {
                    pollStatus(data.operation_id, statusEl, progressBar, progressFill, logBox);
                }
            } catch (error) {
                statusEl.innerHTML = '<div class="status-badge status-error">Error: ' + error.message + '</div>';
            }
        }
        
        async function renameExcel() {
            const folder = document.getElementById('excel-folder').value;
            if (!folder) {
                alert('Please enter a folder path');
                return;
            }
            
            const statusEl = document.getElementById('excel-status');
            const progressBar = document.getElementById('excel-progress-bar');
            const progressFill = document.getElementById('excel-progress-fill');
            const logBox = document.getElementById('excel-log');
            
            statusEl.innerHTML = '<div class="status-badge status-processing">Renaming...</div>';
            
            try {
                const response = await fetch('/api/excel/rename', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({folder: folder})
                });
                
                const data = await response.json();
                if (data.operation_id) {
                    pollStatus(data.operation_id, statusEl, progressBar, progressFill, logBox);
                }
            } catch (error) {
                statusEl.innerHTML = '<div class="status-badge status-error">Error: ' + error.message + '</div>';
            }
        }
        
        async function renameMovies() {
            const folder = document.getElementById('movies-folder').value;
            if (!folder) {
                alert('Please enter a folder path');
                return;
            }
            
            const statusEl = document.getElementById('movies-status');
            const progressBar = document.getElementById('movies-progress-bar');
            const progressFill = document.getElementById('movies-progress-fill');
            const logBox = document.getElementById('movies-log');
            
            statusEl.innerHTML = '<div class="status-badge status-processing">Renaming...</div>';
            
            try {
                const response = await fetch('/api/movies/rename', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({folder: folder})
                });
                
                const data = await response.json();
                if (data.operation_id) {
                    pollStatus(data.operation_id, statusEl, progressBar, progressFill, logBox);
                }
            } catch (error) {
                statusEl.innerHTML = '<div class="status-badge status-error">Error: ' + error.message + '</div>';
            }
        }
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    print("🚀 Starting AIO File Organizer Web Server...")
    print("📂 Access at: http://localhost:5003")
    print("🌐 For mobile access, use ngrok: ngrok http 5003")
    app.run(debug=True, host='0.0.0.0', port=5003)
