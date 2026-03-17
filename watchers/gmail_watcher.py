"""
gmail_watcher.py — Bronze Tier optional Gmail Watcher.

Monitors Gmail for important unread emails and creates Needs_Action files.

Setup:
    1. Enable Gmail API in Google Cloud Console
    2. Download credentials.json to this folder
    3. Run once to authorize: python gmail_watcher.py --vault /path/to/vault --credentials credentials.json

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    print("ERROR: Google API packages not installed.")
    print("Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
TOKEN_FILE = Path(__file__).parent / "gmail_token.json"


def get_gmail_service(credentials_path: str):
    """Authenticate and return Gmail API service."""
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


class GmailWatcher(BaseWatcher):
    """
    Polls Gmail for unread important emails every 2 minutes.
    Creates a Needs_Action .md file for each new email.
    """

    def __init__(self, vault_path: str, credentials_path: str):
        super().__init__(vault_path, check_interval=120)
        self.service = get_gmail_service(credentials_path)
        self.processed_ids: set[str] = set()

    def check_for_updates(self) -> list:
        results = self.service.users().messages().list(
            userId="me", q="is:unread is:important"
        ).execute()
        messages = results.get("messages", [])
        return [m for m in messages if m["id"] not in self.processed_ids]

    def create_action_file(self, message: dict) -> Path:
        msg = self.service.users().messages().get(
            userId="me", id=message["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        snippet = msg.get("snippet", "")
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        md_path = self.needs_action / f"EMAIL_{message['id']}_{timestamp}.md"
        md_content = f"""---
type: email
source: gmail
message_id: {message['id']}
from: {headers.get('From', 'Unknown')}
subject: {headers.get('Subject', 'No Subject')}
date: {headers.get('Date', 'Unknown')}
received: {datetime.now().isoformat()}
priority: high
status: pending
---

## Email Content (Preview)

{snippet}

## Suggested Actions

- [ ] Read full email in Gmail
- [ ] Draft a reply
- [ ] Forward if needed
- [ ] Move to /Done when handled

---
*Created automatically by GmailWatcher*
"""
        md_path.write_text(md_content, encoding="utf-8")
        self.processed_ids.add(message["id"])
        return md_path


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — Gmail Watcher (Bronze Tier)"
    )
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument(
        "--credentials",
        default="credentials.json",
        help="Path to Gmail API credentials.json",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    watcher = GmailWatcher(str(vault_path), args.credentials)
    watcher.run()


if __name__ == "__main__":
    main()
