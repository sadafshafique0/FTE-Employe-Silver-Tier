"""
gmail_watcher.py — Silver Tier Gmail Watcher.

Monitors Gmail inbox for unread emails and creates Needs_Action vault files.
Supports full email body extraction, priority classification, and thread context.

Setup:
    1. Enable Gmail API in Google Cloud Console
       → APIs & Services → Enable APIs → Search "Gmail API" → Enable
    2. Create OAuth 2.0 credentials (Desktop App type)
       → Credentials → Create Credentials → OAuth client ID → Desktop app
    3. Download credentials JSON → save as Credentials.json in project root
    4. First run (opens browser for OAuth):
          python watchers/gmail_watcher.py --vault ./vault --credentials Credentials.json
    5. Subsequent runs reuse the saved token (no browser needed).

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import argparse
import base64
import json
import re
import sys
from email import message_from_bytes
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("ERROR: Google API packages not installed.")
    print("Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

# Read-only scope for the watcher (sending is handled by gmail_sender.py)
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_FILE = Path(__file__).parent / "gmail_token.json"

# Keywords used for priority classification
URGENT_KEYWORDS = [
    "urgent", "asap", "emergency", "critical", "immediately",
    "deadline", "overdue", "action required", "time sensitive",
]
HIGH_KEYWORDS = [
    "invoice", "payment", "proposal", "contract", "meeting",
    "interview", "offer", "follow up", "follow-up", "important",
    "project", "client", "deliverable",
]
NEWSLETTER_KEYWORDS = [
    "unsubscribe", "newsletter", "digest", "weekly update", "monthly update",
    "no-reply", "noreply", "donotreply", "do-not-reply", "marketing",
    "promotion", "promotional", "opt out", "opt-out", "mailing list",
    "you're receiving this", "you are receiving this", "manage preferences",
    "email preferences", "update your preferences",
]


def get_gmail_service(credentials_path: str):
    """Authenticate with Gmail API. Opens browser on first run."""
    creds = None
    creds_path = Path(credentials_path)

    if not creds_path.exists():
        print(f"ERROR: Credentials file not found: {creds_path}")
        print("Download it from Google Cloud Console → APIs & Services → Credentials")
        sys.exit(1)

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
        print(f"Token saved to: {TOKEN_FILE}")

    return build("gmail", "v1", credentials=creds)


def classify_priority(subject: str, body: str, sender: str) -> str:
    """Classify email priority based on content."""
    text = f"{subject} {body} {sender}".lower()
    if any(kw in text for kw in URGENT_KEYWORDS):
        return "urgent"
    if any(kw in text for kw in HIGH_KEYWORDS):
        return "high"
    return "normal"


def is_newsletter(subject: str, body: str, sender: str, headers: dict) -> bool:
    """Detect if the email is a newsletter or promotional mail."""
    text = f"{subject} {body} {sender}".lower()
    if any(kw in text for kw in NEWSLETTER_KEYWORDS):
        return True
    # Check List-Unsubscribe header — standard newsletter header
    if headers.get("List-Unsubscribe") or headers.get("List-ID"):
        return True
    return False


def extract_unsubscribe_link(body: str, headers: dict) -> str:
    """Extract unsubscribe URL from email body or List-Unsubscribe header."""
    # Check List-Unsubscribe header first (most reliable)
    list_unsub = headers.get("List-Unsubscribe", "")
    if list_unsub:
        # Header format: <https://...>, <mailto:...>
        urls = re.findall(r'<(https?://[^>]+)>', list_unsub)
        if urls:
            return urls[0]

    # Fallback: scan body for unsubscribe links
    unsub_pattern = re.compile(
        r'(https?://[^\s<>"\']+(?:unsubscribe|optout|opt-out|remove)[^\s<>"\']*)',
        re.IGNORECASE
    )
    matches = unsub_pattern.findall(body)
    if matches:
        return matches[0]

    return ""


def extract_email_body(payload: dict) -> str:
    """Recursively extract plain text body from Gmail message payload."""
    body_text = ""

    def _extract(part):
        nonlocal body_text
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")

        if mime_type == "text/plain" and data:
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            body_text += decoded
        elif mime_type in ("multipart/alternative", "multipart/mixed", "multipart/related"):
            for subpart in part.get("parts", []):
                _extract(subpart)
        elif not body_text and mime_type == "text/html" and data:
            # Fallback: strip HTML tags
            decoded = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            body_text += re.sub(r"<[^>]+>", "", decoded)

    _extract(payload)
    return body_text.strip()[:2000]  # Cap at 2000 chars for vault files


class GmailWatcher(BaseWatcher):
    """
    Silver Tier Gmail Watcher.
    Polls Gmail every 2 minutes for ALL unread emails.
    Creates rich Needs_Action .md files with full body content and priority.
    """

    def __init__(self, vault_path: str, credentials_path: str, query: str = "is:unread"):
        super().__init__(vault_path, check_interval=120)
        self.service = get_gmail_service(credentials_path)
        self.query = query
        self.processed_ids: set[str] = set()
        self._load_processed_ids()
        self.logger.info(f"Gmail Watcher ready. Query: '{self.query}'")

    def _processed_ids_file(self) -> Path:
        return self.vault_path / "Logs" / "gmail_processed_ids.json"

    def _load_processed_ids(self):
        """Load previously processed IDs so we don't re-process after restart."""
        f = self._processed_ids_file()
        if f.exists():
            try:
                self.processed_ids = set(json.loads(f.read_text(encoding="utf-8")))
                self.logger.info(f"Loaded {len(self.processed_ids)} previously processed email IDs")
            except Exception:
                self.processed_ids = set()

    def _save_processed_ids(self):
        """Persist processed IDs to disk."""
        f = self._processed_ids_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        # Keep only last 1000 IDs to prevent file bloat
        ids_list = list(self.processed_ids)[-1000:]
        f.write_text(json.dumps(ids_list), encoding="utf-8")

    def check_for_updates(self) -> list:
        """Fetch unread emails from Gmail matching the query."""
        try:
            results = self.service.users().messages().list(
                userId="me",
                q=self.query,
                maxResults=20,
            ).execute()
        except HttpError as e:
            self.logger.error(f"Gmail API error: {e}")
            return []

        messages = results.get("messages", [])
        new_messages = [m for m in messages if m["id"] not in self.processed_ids]
        self.logger.info(f"Found {len(messages)} matching emails, {len(new_messages)} new")
        return new_messages

    def create_action_file(self, message: dict) -> Path:
        """Fetch full email and create a rich Needs_Action .md file."""
        try:
            msg = self.service.users().messages().get(
                userId="me",
                id=message["id"],
                format="full",
            ).execute()
        except HttpError as e:
            self.logger.error(f"Could not fetch message {message['id']}: {e}")
            self.processed_ids.add(message["id"])
            return None

        # Extract headers
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        sender = headers.get("From", "Unknown")
        subject = headers.get("Subject", "(No Subject)")
        date = headers.get("Date", "Unknown")
        snippet = msg.get("snippet", "")
        thread_id = msg.get("threadId", "")
        label_ids = msg.get("labelIds", [])

        # Extract full body
        body = extract_email_body(msg["payload"])
        if not body:
            body = snippet  # Fallback to snippet if body extraction fails

        # Classify priority and type
        priority = classify_priority(subject, body, sender)
        newsletter = is_newsletter(subject, body, sender, headers)
        unsub_link = extract_unsubscribe_link(body, headers) if newsletter else ""

        # Clean sender name for filename
        sender_name = re.sub(r"[^\w\s-]", "", sender.split("<")[0].strip())[:30]
        safe_sender = re.sub(r"\s+", "_", sender_name) or "Unknown"
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        md_path = self.needs_action / f"EMAIL_{safe_sender}_{timestamp}.md"

        # Build suggested actions based on email type
        suggested_actions = []
        if newsletter:
            suggested_actions.append("- [ ] **NEWSLETTER DETECTED**")
            if unsub_link:
                suggested_actions.append(f"- [ ] Unsubscribe: {unsub_link}")
            else:
                suggested_actions.append("- [ ] Unsubscribe (find link in email body)")
            suggested_actions.append("- [ ] Delete this email")
        else:
            suggested_actions.append("- [ ] Reply to sender")
            suggested_actions.append("- [ ] Forward to relevant party")
            suggested_actions.append("- [ ] If reply needed: create approval file in /Pending_Approval/")
            suggested_actions.append("- [ ] Delete this email")
            suggested_actions.append("- [ ] Archive after processing")

        actions_block = "\n".join(suggested_actions)

        md_content = f"""---
type: email
source: gmail
message_id: {message['id']}
thread_id: {thread_id}
from: "{sender}"
subject: "{subject}"
date: {date}
received: {datetime.now().isoformat()}
priority: {priority}
is_newsletter: {str(newsletter).lower()}
labels: {', '.join(label_ids)}
status: pending
---

## Email: {subject}

**From:** {sender}
**Date:** {date}
**Priority:** {priority.upper()}{"  |  📧 NEWSLETTER" if newsletter else ""}

### Body

{body}

### Suggested Actions

{actions_block}

---
*Created automatically by GmailWatcher — Silver Tier*
"""
        md_path.write_text(md_content, encoding="utf-8")
        self.processed_ids.add(message["id"])
        self._save_processed_ids()

        # Mark as read in Gmail (optional — comment out if you want to keep unread)
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message["id"],
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
        except HttpError:
            pass  # Non-critical — don't fail if we can't mark as read

        return md_path


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — Gmail Watcher (Silver Tier)"
    )
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument(
        "--credentials",
        default="Credentials.json",
        help="Path to Gmail OAuth credentials JSON (default: Credentials.json in current dir)",
    )
    parser.add_argument(
        "--query",
        default="is:unread",
        help="Gmail search query (default: 'is:unread'). Examples: 'is:unread is:important', 'is:unread from:client@example.com'",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=120,
        help="Poll interval in seconds (default: 120)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    # Resolve credentials path relative to CWD if not absolute
    creds_path = Path(args.credentials)
    if not creds_path.is_absolute():
        creds_path = Path.cwd() / creds_path

    print(f"Vault:       {vault_path}")
    print(f"Credentials: {creds_path}")
    print(f"Query:       {args.query}")
    print(f"Interval:    {args.interval}s")
    print()

    watcher = GmailWatcher(str(vault_path), str(creds_path), query=args.query)
    watcher.check_interval = args.interval
    watcher.run()


if __name__ == "__main__":
    main()
