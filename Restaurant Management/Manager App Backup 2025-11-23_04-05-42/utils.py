"""
Shared utility functions for Manager App
Reduces code duplication and centralizes common operations
"""

import os
import json
import csv
from datetime import datetime
from tkinter import messagebox
import shutil


# ============================================================================
# NUMBER VALIDATION & PARSING
# ============================================================================

def safe_float(value, default=0.0):
    """
    Safely convert value to float with fallback
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        float: Converted value or default
    """
    try:
        if value in (None, '', '--', 'None', 'nan'):
            return default
        return float(str(value).replace('$', '').replace(',', '').strip())
    except (ValueError, TypeError, AttributeError):
        return default


def safe_int(value, default=0):
    """Safely convert value to integer with fallback"""
    try:
        if value in (None, '', '--', 'None'):
            return default
        return int(float(str(value).strip()))
    except (ValueError, TypeError, AttributeError):
        return default


def validate_number(value, min_val=None, max_val=None):
    """
    Validate that value is a number within optional range
    
    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        num = float(value)
        if min_val is not None and num < min_val:
            return False, f"Value must be at least {min_val}"
        if max_val is not None and num > max_val:
            return False, f"Value must not exceed {max_val}"
        return True, ""
    except (ValueError, TypeError):
        return False, "Invalid number format"


def format_currency(value):
    """Format number as currency string"""
    try:
        return f"${float(value):,.2f}"
    except:
        return "$0.00"


# ============================================================================
# DATE UTILITIES
# ============================================================================

def parse_date(date_str, formats=None):
    """
    Parse date string with multiple format attempts
    
    Args:
        date_str: String to parse
        formats: List of format strings to try
        
    Returns:
        datetime or None
    """
    if formats is None:
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%m-%d-%Y",
            "%m-%d-%y"
        ]
    
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str), fmt)
        except (ValueError, TypeError):
            continue
    return None


def format_date(date_obj, format_str="%Y-%m-%d"):
    """Format datetime object to string"""
    try:
        if isinstance(date_obj, str):
            date_obj = parse_date(date_obj)
        return date_obj.strftime(format_str) if date_obj else ""
    except:
        return ""


def get_date_range(start_date, end_date):
    """Generate list of dates between start and end (inclusive)"""
    from datetime import timedelta
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


# ============================================================================
# FILE OPERATIONS
# ============================================================================

def ensure_directory(path):
    """Create directory if it doesn't exist"""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        print(f"Error creating directory {path}: {e}")
        return False


def safe_file_write(filepath, content, backup=True):
    """
    Safely write to file with optional backup
    
    Args:
        filepath: Path to file
        content: Content to write
        backup: Whether to backup existing file
        
    Returns:
        bool: Success status
    """
    try:
        # Create backup if requested and file exists
        if backup and os.path.exists(filepath):
            backup_path = f"{filepath}.backup"
            shutil.copy2(filepath, backup_path)
        
        # Write content
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to write file:\n{str(e)}")
        return False


def safe_json_load(filepath, default=None):
    """Safely load JSON file with fallback"""
    if default is None:
        default = {}
    
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading JSON from {filepath}: {e}")
    
    return default


def safe_json_save(filepath, data, backup=True):
    """Safely save data to JSON file"""
    try:
        if backup and os.path.exists(filepath):
            shutil.copy2(filepath, f"{filepath}.backup")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save JSON:\n{str(e)}")
        return False


# ============================================================================
# CSV OPERATIONS
# ============================================================================

def read_csv_safe(filepath, encoding='utf-8'):
    """
    Safely read CSV file
    
    Returns:
        list: List of rows (each row is a list)
    """
    try:
        with open(filepath, 'r', encoding=encoding, newline='') as f:
            reader = csv.reader(f)
            return list(reader)
    except Exception as e:
        print(f"Error reading CSV {filepath}: {e}")
        return []


def write_csv_safe(filepath, rows, backup=True):
    """
    Safely write CSV file
    
    Args:
        filepath: Path to CSV file
        rows: List of rows to write
        backup: Whether to backup existing file
        
    Returns:
        bool: Success status
    """
    try:
        if backup and os.path.exists(filepath):
            shutil.copy2(filepath, f"{filepath}.backup")
        
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Failed to write CSV:\n{str(e)}")
        return False


def csv_to_dict(filepath, key_column=0):
    """
    Load CSV into dictionary keyed by specified column
    
    Returns:
        dict: {key: row_dict}
    """
    result = {}
    try:
        with open(filepath, 'r', encoding='utf-8', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = list(row.values())[key_column]
                result[key] = row
    except Exception as e:
        print(f"Error loading CSV as dict: {e}")
    
    return result


# ============================================================================
# DATA VALIDATION
# ============================================================================

def validate_employee_data(data):
    """
    Validate employee data dictionary
    
    Returns:
        tuple: (is_valid, error_message)
    """
    required_fields = ['name', 'area']
    
    for field in required_fields:
        if field not in data or not data[field]:
            return False, f"Missing required field: {field}"
    
    # Validate numeric fields
    numeric_fields = ['cash', 'cc_tips', 'visa', 'mastercard', 'amex', 
                     'discover', 'beer', 'liquor', 'wine', 'food']
    
    for field in numeric_fields:
        if field in data:
            is_valid, msg = validate_number(data[field], min_val=0)
            if not is_valid:
                return False, f"Invalid {field}: {msg}"
    
    return True, ""


def validate_date_range(start_date, end_date):
    """Validate that date range is valid"""
    try:
        if start_date > end_date:
            return False, "Start date must be before end date"
        
        # Check if range is too large (optional)
        delta = (end_date - start_date).days
        if delta > 365:
            return False, "Date range cannot exceed 1 year"
        
        return True, ""
    except:
        return False, "Invalid date range"


# ============================================================================
# STRING UTILITIES
# ============================================================================

def clean_string(value):
    """Clean and normalize string"""
    if value is None:
        return ""
    return str(value).strip()


def truncate_string(text, max_length=50, suffix="..."):
    """Truncate string to max length"""
    text = str(text)
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def normalize_name(name):
    """Normalize employee/user name"""
    return " ".join(clean_string(name).title().split())


# ============================================================================
# BACKUP UTILITIES
# ============================================================================

def create_backup(source_path, backup_dir=None):
    """
    Create timestamped backup of file or directory
    
    Returns:
        str: Path to backup or None if failed
    """
    try:
        if backup_dir is None:
            backup_dir = os.path.join(os.path.dirname(source_path), "backups")
        
        ensure_directory(backup_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        basename = os.path.basename(source_path)
        backup_path = os.path.join(backup_dir, f"{basename}.{timestamp}")
        
        if os.path.isfile(source_path):
            shutil.copy2(source_path, backup_path)
        elif os.path.isdir(source_path):
            shutil.copytree(source_path, backup_path)
        else:
            return None
        
        return backup_path
    except Exception as e:
        print(f"Backup failed: {e}")
        return None


def cleanup_old_backups(backup_dir, days_to_keep=30):
    """Remove backups older than specified days"""
    try:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days_to_keep)
        
        for filename in os.listdir(backup_dir):
            filepath = os.path.join(backup_dir, filename)
            if os.path.isfile(filepath):
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if file_time < cutoff:
                    os.remove(filepath)
                    print(f"Removed old backup: {filename}")
    except Exception as e:
        print(f"Cleanup failed: {e}")


# ============================================================================
# UI UTILITIES
# ============================================================================

def confirm_action(title, message):
    """Show confirmation dialog"""
    return messagebox.askyesno(title, message)


def show_error(message, title="Error"):
    """Show error message"""
    messagebox.showerror(title, message)


def show_success(message, title="Success"):
    """Show success message"""
    messagebox.showinfo(title, message)


def show_warning(message, title="Warning"):
    """Show warning message"""
    messagebox.showwarning(title, message)
