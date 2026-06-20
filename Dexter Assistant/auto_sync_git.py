"""
Auto-sync Git module for Dexter Assistant
Automatically commits and pushes database changes to GitHub
"""

import os
import subprocess
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import tuple

logger = logging.getLogger(__name__)


class GitAutoSync:
    """Handles automatic git commits and pushes for database changes"""
    
    def __init__(self, repo_root: Path, git_user_name: str = "Dexter Auto-Sync", git_user_email: str = "autosync@dexter.local"):
        """
        Initialize GitAutoSync
        
        Args:
            repo_root: Root directory of the git repository
            git_user_name: Name to use for git commits
            git_user_email: Email to use for git commits
        """
        self.repo_root = Path(repo_root)
        self.git_user_name = git_user_name
        self.git_user_email = git_user_email
        self.branch = os.environ.get("GIT_BRANCH", "checkpoint/dexter-assist-20260601-173327")
        
        # Ensure repo_root is a valid git repo
        if not (self.repo_root / ".git").exists():
            raise ValueError(f"{repo_root} is not a git repository")
        
        self._configure_git()
    
    def _configure_git(self):
        """Configure git user for commits"""
        try:
            subprocess.run(
                ["git", "config", "user.name", self.git_user_name],
                cwd=self.repo_root,
                capture_output=True,
                check=True,
                timeout=10
            )
            subprocess.run(
                ["git", "config", "user.email", self.git_user_email],
                cwd=self.repo_root,
                capture_output=True,
                check=True,
                timeout=10
            )
            logger.info(f"Git configured for auto-sync: {self.git_user_name} <{self.git_user_email}>")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to configure git: {e}")
            raise
    
    def has_changes(self) -> bool:
        """
        Check if there are any uncommitted changes in tracked files
        
        Returns:
            True if there are changes, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            return bool(result.stdout.strip())
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to check git status: {e}")
            return False
    
    def get_changed_files(self) -> list[str]:
        """
        Get list of changed files
        
        Returns:
            List of changed file paths
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            files = [line[3:].strip() for line in result.stdout.strip().split('\n') if line.strip()]
            return files
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get changed files: {e}")
            return []
    
    def commit_and_push(self, commit_message: str = None, paths: list[str] = None) -> tuple[bool, str]:
        """
        Commit and push changes to remote
        
        Args:
            commit_message: Custom commit message (auto-generated if None)
            paths: Specific paths to commit (all if None)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Check for changes first
            if not self.has_changes():
                logger.info("No changes to commit")
                return True, "No changes detected"
            
            changed_files = self.get_changed_files()
            if not changed_files:
                logger.info("No tracked files changed")
                return True, "No tracked files changed"
            
            # Add files to staging
            if paths:
                for path in paths:
                    subprocess.run(
                        ["git", "add", path],
                        cwd=self.repo_root,
                        capture_output=True,
                        check=True,
                        timeout=10
                    )
            else:
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=self.repo_root,
                    capture_output=True,
                    check=True,
                    timeout=10
                )
            
            # Generate commit message if not provided
            if not commit_message:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                file_summary = ", ".join(changed_files[:3])
                if len(changed_files) > 3:
                    file_summary += f", +{len(changed_files) - 3} more"
                commit_message = f"Auto-sync: Update database files [{timestamp}]\n\nChanged: {file_summary}"
            
            # Commit changes
            result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            
            logger.info(f"Committed changes: {commit_message[:50]}...")
            
            # Push to remote
            push_result = subprocess.run(
                ["git", "push", "origin", self.branch],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if push_result.returncode == 0:
                logger.info(f"Successfully pushed to {self.branch}")
                return True, f"Committed and pushed {len(changed_files)} file(s)"
            else:
                error_msg = push_result.stderr or "Unknown error"
                logger.error(f"Push failed: {error_msg}")
                return False, f"Push failed: {error_msg}"
        
        except subprocess.TimeoutExpired as e:
            logger.error(f"Git operation timed out: {e}")
            return False, "Operation timed out"
        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Unexpected error during commit/push: {e}")
            return False, str(e)
    
    def sync_database_files(self) -> dict:
        """
        Sync common database files that change during operations
        ProductMixRestaurantDB, daily_logs, inventory_data
        
        Returns:
            Dict with sync status
        """
        status = {
            "synced_at": datetime.now().isoformat(),
            "success": False,
            "message": "",
            "files_changed": []
        }
        
        try:
            changed = self.get_changed_files()
            db_files = [
                "ProductMixRestaurantDB/product_mix.db",
                "ProductMixRestaurantDB/production_items.db",
                "daily_logs/",
                "inventory_data/"
            ]
            
            relevant_changes = [f for f in changed if any(f.startswith(db) for db in db_files)]
            
            if relevant_changes:
                success, msg = self.commit_and_push()
                status["success"] = success
                status["message"] = msg
                status["files_changed"] = relevant_changes
                logger.info(f"Database sync complete: {msg}")
            else:
                status["success"] = True
                status["message"] = "No database changes to sync"
            
            return status
        
        except Exception as e:
            status["success"] = False
            status["message"] = f"Sync failed: {str(e)}"
            logger.error(f"Database sync error: {e}")
            return status


def create_auto_sync_scheduler(app, repo_root: Path, interval_minutes: int = 30):
    """
    Create a background scheduler to auto-sync git changes
    
    Args:
        app: Flask app instance
        repo_root: Root directory of the git repository
        interval_minutes: Interval between syncs (default 30 minutes)
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        
        scheduler = BackgroundScheduler()
        
        def sync_job():
            """Background job for git sync"""
            try:
                logger.info("Starting auto-sync job...")
                syncer = GitAutoSync(repo_root)
                result = syncer.sync_database_files()
                logger.info(f"Auto-sync result: {json.dumps(result, default=str)}")
            except Exception as e:
                logger.error(f"Auto-sync job failed: {e}")
        
        scheduler.add_job(
            sync_job,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id="git_autosync",
            name="Git Auto-Sync Job",
            replace_existing=True,
            coalesce=True,
            max_instances=1
        )
        
        if not scheduler.running:
            scheduler.start()
            logger.info(f"Auto-sync scheduler started (interval: {interval_minutes} minutes)")
        
        return scheduler
    
    except ImportError:
        logger.warning("APScheduler not installed. Auto-sync scheduler not available.")
        return None


if __name__ == "__main__":
    # Test script
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    repo_root = Path(__file__).parent.parent
    
    try:
        syncer = GitAutoSync(repo_root)
        logger.info(f"Repository: {repo_root}")
        logger.info(f"Branch: {syncer.branch}")
        
        # Check for changes
        if syncer.has_changes():
            changed = syncer.get_changed_files()
            logger.info(f"Found {len(changed)} changed file(s)")
            for f in changed[:10]:
                logger.info(f"  - {f}")
            
            # Sync database files
            result = syncer.sync_database_files()
            logger.info(f"Sync result: {json.dumps(result, default=str)}")
        else:
            logger.info("No changes to sync")
    
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
