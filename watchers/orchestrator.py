"""
orchestrator.py — Silver Tier Orchestrator.

Watches vault/Approved/ folder every 10 seconds and triggers the right
MCP action for each approved file type:

  EMAIL_SEND_*.md   → send via gmail_sender.py
  LINKEDIN_POST_*.md → handled by linkedin_watcher.py (skip here)
  Unknown types     → log warning, move to Done

This is the "hands" of the AI Employee — it executes approved actions.

Usage:
    python watchers/orchestrator.py --vault ./vault --credentials Credentials.json

    # Dry-run (won't actually send anything):
    python watchers/orchestrator.py --vault ./vault --credentials Credentials.json --dry-run

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import argparse
import json
import subprocess
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

GMAIL_TOKEN = Path(__file__).parent / "gmail_token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Orchestrator] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("orchestrator")

SCRIPT_DIR = Path(__file__).parent


def parse_frontmatter(filepath: Path) -> dict:
    """Parse YAML frontmatter from a .md file."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")
    fm = {}
    in_fm = False
    fm_count = 0
    for line in lines:
        if line.strip() == "---":
            fm_count += 1
            in_fm = fm_count == 1
            if fm_count == 2:
                break
            continue
        if in_fm and ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"')
    return fm


def log_action(vault_path: Path, entry: dict):
    """Append an entry to today's JSON log."""
    logs_dir = vault_path / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"
    existing = []
    if log_file.exists():
        try:
            existing = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    existing.append(entry)
    log_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def update_dashboard(vault_path: Path, message: str):
    """Append an activity line to Dashboard.md."""
    dashboard = vault_path / "Dashboard.md"
    if not dashboard.exists():
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n- [{timestamp}] {message}"
    content = dashboard.read_text(encoding="utf-8")
    marker = "## Recent Activity"
    if marker in content:
        content = content.replace(marker, marker + entry, 1)
        dashboard.write_text(content, encoding="utf-8")


def get_gmail_service():
    """Get Gmail service using existing watcher token."""
    if not GMAIL_AVAILABLE:
        return None
    if not GMAIL_TOKEN.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN), GMAIL_SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        logger.warning(f"Could not load Gmail service: {e}")
        return None


def scan_needs_action_for_deletions(vault_path: Path, dry_run: bool):
    """
    Scan Needs_Action files for checked '- [x] Delete this email' boxes.
    Trashes the email in Gmail and moves the vault file to Done/.
    """
    needs_action = vault_path / "Needs_Action"
    done_dir = vault_path / "Done"
    if not needs_action.exists():
        return

    gmail = get_gmail_service()
    deleted = 0

    for f in needs_action.glob("EMAIL_*.md"):
        try:
            content = f.read_text(encoding="utf-8")
            # Check if delete action is ticked: - [x] Delete this email
            if "- [x] Delete this email" not in content:
                continue

            # Extract message_id from frontmatter
            message_id = None
            for line in content.split("\n"):
                if line.startswith("message_id:"):
                    message_id = line.split(":", 1)[1].strip()
                    break

            logger.info(f"Delete requested: {f.name} (Gmail ID: {message_id})")

            if not dry_run and gmail and message_id:
                try:
                    gmail.users().messages().trash(userId="me", id=message_id).execute()
                    logger.info(f"Trashed in Gmail: {message_id}")
                except HttpError as e:
                    logger.error(f"Gmail trash failed for {message_id}: {e}")

            # Move vault file to Done
            done_path = done_dir / f.name
            f.rename(done_path)
            logger.info(f"Moved to Done: {f.name}")

            log_action(vault_path, {
                "timestamp": datetime.now().isoformat(),
                "action_type": "email_delete",
                "file": f.name,
                "gmail_id": message_id,
                "result": "dry_run" if dry_run else "trashed",
                "actor": "orchestrator",
            })
            deleted += 1

        except Exception as e:
            logger.error(f"Error processing delete for {f.name}: {e}")

    if deleted:
        logger.info(f"Deleted {deleted} email(s) from Gmail and vault")


def process_email_send(filepath: Path, vault_path: Path, credentials_path: Path, dry_run: bool) -> bool:
    """Call gmail_sender.py to send the email in this approval file."""
    sender_script = SCRIPT_DIR / "gmail_sender.py"
    if not sender_script.exists():
        logger.error(f"gmail_sender.py not found at {sender_script}")
        return False

    cmd = [
        sys.executable, str(sender_script),
        "--approval-file", str(filepath),
        "--credentials", str(credentials_path),
        "--vault", str(vault_path),
    ]
    if dry_run:
        cmd.append("--dry-run")

    logger.info(f"Sending email via gmail_sender: {filepath.name}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            logger.info(f"Email sent successfully: {filepath.name}")
            logger.info(result.stdout.strip())
            return True
        else:
            logger.error(f"gmail_sender failed (exit {result.returncode}):")
            logger.error(result.stderr.strip())
            return False
    except subprocess.TimeoutExpired:
        logger.error("gmail_sender timed out after 60s")
        return False
    except Exception as e:
        logger.error(f"Error calling gmail_sender: {e}")
        return False


def process_approved_file(
    filepath: Path,
    vault_path: Path,
    credentials_path: Path,
    dry_run: bool,
) -> bool:
    """Route an approved file to the correct action handler."""
    logger.info(f"Processing: {filepath.name}")

    try:
        fm = parse_frontmatter(filepath)
        action = fm.get("action", "").strip().lower()

        success = False
        description = f"Action: {action} | File: {filepath.name}"

        if action in ("email_send", "send_email", "email"):
            success = process_email_send(filepath, vault_path, credentials_path, dry_run)

        elif action == "linkedin_post":
            # LinkedIn posts are handled by linkedin_watcher.py
            # Just rename so linkedin_watcher picks it up correctly
            new_name = filepath.name
            if not filepath.name.startswith("LINKEDIN_POST_"):
                new_name = "LINKEDIN_POST_" + filepath.name
            new_path = filepath.parent / new_name
            if new_path != filepath:
                filepath.rename(new_path)
                logger.info(f"Renamed to {new_name} for linkedin_watcher pickup")
            else:
                logger.info(f"LinkedIn post ready for linkedin_watcher: {filepath.name}")
            return True  # Don't move to Done — linkedin_watcher handles that

        else:
            logger.warning(f"Unknown action '{action}' in {filepath.name} — moving to Done")
            success = True  # Move to Done anyway

        # Move to Done
        done_path = vault_path / "Done" / filepath.name
        filepath.rename(done_path)
        logger.info(f"Moved to Done: {filepath.name}")

        # Log the action
        log_action(vault_path, {
            "timestamp": datetime.now().isoformat(),
            "action_type": action or "unknown",
            "file": filepath.name,
            "result": "success" if success else "failed",
            "dry_run": dry_run,
            "actor": "orchestrator",
        })

        # Update dashboard
        status = "sent" if success else "FAILED"
        update_dashboard(vault_path, f"[Orchestrator] {description} → {status}")

        return success

    except Exception as e:
        logger.error(f"Error processing {filepath.name}: {e}", exc_info=True)
        log_action(vault_path, {
            "timestamp": datetime.now().isoformat(),
            "action_type": "error",
            "file": filepath.name,
            "result": f"error: {e}",
            "dry_run": dry_run,
        })
        return False


def run(vault_path: Path, credentials_path: Path, dry_run: bool, poll_interval: int):
    """Main polling loop."""
    approved_dir = vault_path / "Approved"
    done_dir = vault_path / "Done"
    logs_dir = vault_path / "Logs"

    for d in [approved_dir, done_dir, logs_dir]:
        d.mkdir(parents=True, exist_ok=True)

    logger.info(f"Orchestrator started")
    logger.info(f"Vault:       {vault_path}")
    logger.info(f"Credentials: {credentials_path}")
    logger.info(f"Dry run:     {dry_run}")
    logger.info(f"Poll:        {poll_interval}s")
    logger.info(f"Watching:    {approved_dir}")

    while True:
        try:
            # 1. Process approved actions (/Approved/ folder)
            action_files = [
                f for f in approved_dir.glob("*.md")
                if f.name != ".gitkeep"
                and not f.name.startswith(".")
                and not f.name.startswith("LINKEDIN_POST_")
            ]
            for f in action_files:
                process_approved_file(f, vault_path, credentials_path, dry_run)

            # 2. Scan Needs_Action for checked delete boxes
            scan_needs_action_for_deletions(vault_path, dry_run)

        except KeyboardInterrupt:
            logger.info("Orchestrator stopped.")
            break
        except Exception as e:
            logger.error(f"Orchestrator loop error: {e}", exc_info=True)

        time.sleep(poll_interval)


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — Orchestrator (Silver Tier)"
    )
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument(
        "--credentials",
        default="Credentials.json",
        help="Path to Gmail OAuth credentials JSON (default: Credentials.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log actions without executing them",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Seconds between polling /Approved/ (default: 10)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    # Resolve credentials relative to CWD
    creds_path = Path(args.credentials)
    if not creds_path.is_absolute():
        creds_path = Path.cwd() / creds_path

    if not creds_path.exists():
        logger.warning(f"Credentials not found at {creds_path} — email sending disabled")
        logger.warning("Place your Credentials.json in the project root or use --credentials flag")

    run(vault_path, creds_path, args.dry_run, args.poll_interval)


if __name__ == "__main__":
    main()
