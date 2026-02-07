"""
Auto-save and backup management for Manager App
Prevents data loss and maintains version history
"""

import os
import time
import threading
from datetime import datetime
from utils import ensure_directory, create_backup, cleanup_old_backups


class AutoSaveManager:
    """Manages auto-save functionality for applications"""
    
    def __init__(self, app, save_callback, interval_seconds=300):
        """
        Initialize auto-save manager
        
        Args:
            app: The tkinter application instance
            save_callback: Function to call for saving
            interval_seconds: Time between auto-saves (default 5 minutes)
        """
        self.app = app
        self.save_callback = save_callback
        self.interval_seconds = interval_seconds
        self.is_running = False
        self.has_unsaved_changes = False
        self.last_save_time = time.time()
        self._timer = None
    
    def mark_dirty(self):
        """Mark that there are unsaved changes"""
        self.has_unsaved_changes = True
    
    def mark_clean(self):
        """Mark that all changes are saved"""
        self.has_unsaved_changes = False
        self.last_save_time = time.time()
    
    def start(self):
        """Start auto-save timer"""
        if not self.is_running:
            self.is_running = True
            self._schedule_next_save()
    
    def stop(self):
        """Stop auto-save timer"""
        self.is_running = False
        if self._timer:
            self.app.after_cancel(self._timer)
            self._timer = None
    
    def _schedule_next_save(self):
        """Schedule the next auto-save"""
        if self.is_running:
            self._timer = self.app.after(
                self.interval_seconds * 1000,
                self._auto_save
            )
    
    def _auto_save(self):
        """Perform auto-save if there are unsaved changes"""
        if self.has_unsaved_changes:
            try:
                self.save_callback()
                self.mark_clean()
                print(f"[AutoSave] Saved at {datetime.now().strftime('%H:%M:%S')}")
            except Exception as e:
                print(f"[AutoSave] Failed: {e}")
        
        # Schedule next save
        self._schedule_next_save()
    
    def get_time_since_last_save(self):
        """Get seconds since last save"""
        return time.time() - self.last_save_time


class BackupManager:
    """Manages backup creation and rotation"""
    
    def __init__(self, data_dir, backup_dir=None, max_backups=10):
        """
        Initialize backup manager
        
        Args:
            data_dir: Directory containing data files
            backup_dir: Directory for backups (default: data_dir/backups)
            max_backups: Maximum number of backups to keep per file
        """
        self.data_dir = data_dir
        self.backup_dir = backup_dir or os.path.join(data_dir, "backups")
        self.max_backups = max_backups
        
        ensure_directory(self.backup_dir)
    
    def create_backup(self, filename):
        """
        Create backup of specific file
        
        Returns:
            str: Path to backup file or None
        """
        source_path = os.path.join(self.data_dir, filename)
        if not os.path.exists(source_path):
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{filename}.{timestamp}.backup"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        try:
            import shutil
            shutil.copy2(source_path, backup_path)
            
            # Cleanup old backups
            self._cleanup_old_backups(filename)
            
            return backup_path
        except Exception as e:
            print(f"Backup failed for {filename}: {e}")
            return None
    
    def _cleanup_old_backups(self, filename):
        """Remove old backups beyond max_backups limit"""
        try:
            # Find all backups for this file
            backups = []
            for backup_file in os.listdir(self.backup_dir):
                if backup_file.startswith(filename):
                    backup_path = os.path.join(self.backup_dir, backup_file)
                    backups.append((
                        backup_path,
                        os.path.getmtime(backup_path)
                    ))
            
            # Sort by modification time (newest first)
            backups.sort(key=lambda x: x[1], reverse=True)
            
            # Remove old backups
            for backup_path, _ in backups[self.max_backups:]:
                try:
                    os.remove(backup_path)
                    print(f"Removed old backup: {os.path.basename(backup_path)}")
                except:
                    pass
        except Exception as e:
            print(f"Cleanup failed: {e}")
    
    def list_backups(self, filename):
        """
        List all backups for a file
        
        Returns:
            list: List of (backup_path, timestamp) tuples
        """
        backups = []
        try:
            for backup_file in os.listdir(self.backup_dir):
                if backup_file.startswith(filename):
                    backup_path = os.path.join(self.backup_dir, backup_file)
                    mtime = os.path.getmtime(backup_path)
                    backups.append((backup_path, datetime.fromtimestamp(mtime)))
            
            backups.sort(key=lambda x: x[1], reverse=True)
        except Exception as e:
            print(f"List backups failed: {e}")
        
        return backups
    
    def restore_backup(self, backup_path, target_filename=None):
        """
        Restore a backup file
        
        Args:
            backup_path: Path to backup file
            target_filename: Target filename (if None, derived from backup)
            
        Returns:
            bool: Success status
        """
        try:
            import shutil
            
            if target_filename is None:
                # Extract original filename from backup name
                backup_name = os.path.basename(backup_path)
                target_filename = backup_name.split('.')[0]
            
            target_path = os.path.join(self.data_dir, target_filename)
            
            # Create backup of current file before restoring
            if os.path.exists(target_path):
                self.create_backup(target_filename)
            
            # Restore
            shutil.copy2(backup_path, target_path)
            return True
        except Exception as e:
            print(f"Restore failed: {e}")
            return False
    
    def cleanup_all_old_backups(self, days_to_keep=30):
        """Remove all backups older than specified days"""
        cleanup_old_backups(self.backup_dir, days_to_keep)


class DataValidator:
    """Validates data before saving to prevent corruption"""
    
    @staticmethod
    def validate_daily_log(data):
        """
        Validate daily log data structure
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if not isinstance(data, dict):
            return False, "Data must be a dictionary"
        
        # Check for required sections
        if 'employees' not in data:
            return False, "Missing employees section"
        
        if not isinstance(data['employees'], list):
            return False, "Employees must be a list"
        
        # Validate each employee entry
        for i, emp in enumerate(data['employees']):
            if not isinstance(emp, dict):
                return False, f"Employee {i} must be a dictionary"
            
            if 'name' not in emp or not emp['name']:
                return False, f"Employee {i} missing name"
        
        return True, ""
    
    @staticmethod
    def validate_employee_list(employees):
        """
        Validate employee list
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if not isinstance(employees, list):
            return False, "Employees must be a list"
        
        seen_names = set()
        for i, emp in enumerate(employees):
            if 'name' not in emp:
                return False, f"Employee {i} missing name"
            
            name = emp['name'].strip().lower()
            if name in seen_names:
                return False, f"Duplicate employee name: {emp['name']}"
            seen_names.add(name)
        
        return True, ""


# Singleton instance for app-wide use
_backup_manager = None

def get_backup_manager(data_dir=None):
    """Get or create global backup manager instance"""
    global _backup_manager
    
    if _backup_manager is None and data_dir:
        _backup_manager = BackupManager(data_dir)
    
    return _backup_manager
