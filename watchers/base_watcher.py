"""
base_watcher.py — Abstract base class for all AI Employee Watchers.
All watchers follow the same pattern: check for updates → create action files.
"""

import time
import logging
from pathlib import Path
from abc import ABC, abstractmethod
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class BaseWatcher(ABC):
    def __init__(self, vault_path: str, check_interval: int = 60):
        self.vault_path = Path(vault_path)
        self.needs_action = self.vault_path / "Needs_Action"
        self.inbox = self.vault_path / "Inbox"
        self.done = self.vault_path / "Done"
        self.check_interval = check_interval
        self.logger = logging.getLogger(self.__class__.__name__)
        self._ensure_folders()

    def _ensure_folders(self):
        """Create required vault folders if they don't exist."""
        for folder in [self.needs_action, self.inbox, self.done,
                       self.vault_path / "Plans", self.vault_path / "Logs",
                       self.vault_path / "Pending_Approval",
                       self.vault_path / "Approved", self.vault_path / "Rejected"]:
            folder.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def check_for_updates(self) -> list:
        """Return list of new items to process."""
        pass

    @abstractmethod
    def create_action_file(self, item) -> Path:
        """Create a .md file in Needs_Action folder for each item."""
        pass

    def log_activity(self, description: str):
        """Append an activity entry to Dashboard.md."""
        dashboard = self.vault_path / "Dashboard.md"
        if not dashboard.exists():
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n- [{timestamp}] {description}"
        content = dashboard.read_text(encoding="utf-8")
        marker = "## Recent Activity"
        if marker in content:
            content = content.replace(marker, marker + entry, 1)
            dashboard.write_text(content, encoding="utf-8")

    def run(self):
        self.logger.info(f"Starting {self.__class__.__name__} (interval: {self.check_interval}s)")
        while True:
            try:
                items = self.check_for_updates()
                for item in items:
                    path = self.create_action_file(item)
                    self.logger.info(f"Created action file: {path.name}")
                    self.log_activity(f"New item queued by {self.__class__.__name__}: {path.name}")
            except KeyboardInterrupt:
                self.logger.info("Watcher stopped by user.")
                break
            except Exception as e:
                self.logger.error(f"Error during check: {e}", exc_info=True)
            time.sleep(self.check_interval)
