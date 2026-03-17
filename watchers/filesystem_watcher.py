"""
filesystem_watcher.py — Bronze Tier Watcher.

Monitors the vault's /Inbox folder for new files.
When a file is dropped there, it creates a Needs_Action .md file
so Claude Code knows to process it.

Usage:
    python filesystem_watcher.py --vault /path/to/vault

Requirements:
    pip install watchdog
"""

import argparse
import shutil
import sys
from pathlib import Path
from datetime import datetime

# Allow running from any directory
sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("ERROR: 'watchdog' package not installed.")
    print("Run: pip install watchdog")
    sys.exit(1)


class InboxDropHandler(FileSystemEventHandler):
    """Handles new files dropped into /Inbox."""

    def __init__(self, watcher: "FileSystemWatcher"):
        self.watcher = watcher

    def on_created(self, event):
        if event.is_directory:
            return
        source = Path(event.src_path)
        # Skip hidden files and .gitkeep
        if source.name.startswith(".") or source.name == ".gitkeep":
            return
        self.watcher.queue.append(source)

    def on_moved(self, event):
        """Also handle files moved into the Inbox folder."""
        if event.is_directory:
            return
        dest = Path(event.dest_path)
        if dest.parent == self.watcher.inbox:
            if not dest.name.startswith("."):
                self.watcher.queue.append(dest)


class FileSystemWatcher(BaseWatcher):
    """
    Watches the vault's /Inbox folder for new file drops.
    Creates a Needs_Action .md file for each dropped file,
    then moves the original file to /Needs_Action for Claude to process.
    """

    def __init__(self, vault_path: str):
        super().__init__(vault_path, check_interval=5)
        self.queue: list[Path] = []
        self.processed: set[str] = set()

    def check_for_updates(self) -> list:
        """Drain the queue of newly dropped files."""
        items = [p for p in self.queue if p.name not in self.processed]
        self.queue.clear()
        return items

    def create_action_file(self, source: Path) -> Path:
        """
        Move the dropped file to /Needs_Action and create a metadata .md file.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_name = source.stem.replace(" ", "_")

        # Move the actual file into Needs_Action
        dest_file = self.needs_action / f"{source.name}"
        if dest_file.exists():
            dest_file = self.needs_action / f"{safe_name}_{timestamp}{source.suffix}"
        shutil.move(str(source), str(dest_file))

        # Create companion metadata .md file
        md_path = self.needs_action / f"FILE_{safe_name}_{timestamp}.md"
        file_size = dest_file.stat().st_size
        md_content = f"""---
type: file_drop
source: inbox
original_name: {source.name}
moved_to: {dest_file.name}
size_bytes: {file_size}
received: {datetime.now().isoformat()}
priority: normal
status: pending
---

## File Dropped for Processing

A new file has been dropped into the Inbox and is ready for AI processing.

**File:** `{dest_file.name}`
**Size:** {file_size:,} bytes
**Received:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Suggested Actions

- [ ] Read and summarize the file content
- [ ] Classify: invoice / report / contract / other
- [ ] Create a Plan.md if action is required
- [ ] Move this file to /Done when complete

---
*Created automatically by FileSystemWatcher*
"""
        md_path.write_text(md_content, encoding="utf-8")
        self.processed.add(source.name)
        return md_path

    def run(self):
        self.logger.info(f"FileSystemWatcher watching: {self.inbox}")
        self.logger.info("Drop any file into the /Inbox folder to trigger processing.")
        self.logger.info("Press Ctrl+C to stop.")

        handler = InboxDropHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self.inbox), recursive=False)
        observer.start()

        try:
            while True:
                import time
                time.sleep(self.check_interval)
                items = self.check_for_updates()
                for item in items:
                    path = self.create_action_file(item)
                    self.logger.info(f"Action file created: {path.name}")
                    self.log_activity(f"File dropped and queued: {item.name}")
        except KeyboardInterrupt:
            observer.stop()
            self.logger.info("FileSystemWatcher stopped.")
        observer.join()


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — File System Watcher (Bronze Tier)"
    )
    parser.add_argument(
        "--vault",
        required=True,
        help="Absolute path to your Obsidian vault folder",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    watcher = FileSystemWatcher(str(vault_path))
    watcher.run()


if __name__ == "__main__":
    main()
