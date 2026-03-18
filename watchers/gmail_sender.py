"""
gmail_sender.py — Silver Tier Gmail Sender (MCP-style action).

Sends emails via Gmail API. Called by the orchestrator when an email approval
file appears in /Approved/. Supports:
  - Plain text and HTML emails
  - Reply threading (via thread_id)
  - Dry-run mode (default: safe)
  - Rate limiting (max 10 emails/hour)
  - Full audit logging

Setup:
    Uses Credentials.json from project root (same file as gmail_watcher.py).
    Requires gmail.send scope — will re-authorize if current token lacks it.

Usage (standalone):
    python watchers/gmail_sender.py --credentials Credentials.json \\
        --to "client@example.com" \\
        --subject "Invoice #123" \\
        --body "Please find attached..."

    # Dry run (safe test — won't actually send):
    python watchers/gmail_sender.py --dry-run --to "test@example.com" ...

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import argparse
import base64
import json
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [GmailSender] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gmail_sender")

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

# Send scope (separate token file from watcher so scopes don't conflict)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]
TOKEN_FILE = Path(__file__).parent / "gmail_send_token.json"

# Rate limiting state (resets each hour)
_send_count = 0
_send_hour = datetime.now().hour
MAX_EMAILS_PER_HOUR = 10


def get_send_service(credentials_path: str):
    """Get Gmail service with send scope."""
    creds = None
    creds_file = Path(credentials_path)

    if not creds_file.exists():
        logger.error(f"Credentials file not found: {creds_file}")
        sys.exit(1)

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
        logger.info(f"Send token saved: {TOKEN_FILE}")

    return build("gmail", "v1", credentials=creds)


def check_rate_limit():
    """Enforce max 10 emails/hour."""
    global _send_count, _send_hour
    current_hour = datetime.now().hour
    if current_hour != _send_hour:
        _send_count = 0
        _send_hour = current_hour
    if _send_count >= MAX_EMAILS_PER_HOUR:
        raise RuntimeError(
            f"Rate limit: {MAX_EMAILS_PER_HOUR} emails/hour. "
            f"Sent {_send_count} this hour. Try again next hour."
        )


def build_message(
    to: str,
    subject: str,
    body: str,
    from_addr: str = "me",
    cc: str = "",
    reply_to_thread_id: str = "",
    html: bool = False,
) -> dict:
    """Build a Gmail API message dict."""
    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "html"))
    else:
        msg = MIMEText(body, "plain")

    msg["to"] = to
    msg["subject"] = subject
    if cc:
        msg["cc"] = cc

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"raw": raw}
    if reply_to_thread_id:
        payload["threadId"] = reply_to_thread_id
    return payload


def send_email(
    service,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    thread_id: str = "",
    dry_run: bool = False,
    html: bool = False,
) -> dict:
    """
    Send an email via Gmail API.
    Returns result dict with message_id, status, timestamp.
    """
    check_rate_limit()

    result = {
        "timestamp": datetime.now().isoformat(),
        "to": to,
        "subject": subject,
        "dry_run": dry_run,
        "status": "pending",
        "message_id": None,
    }

    if dry_run:
        logger.info(f"[DRY RUN] Would send email:")
        logger.info(f"  To:      {to}")
        logger.info(f"  Subject: {subject}")
        logger.info(f"  Body:    {body[:100]}...")
        result["status"] = "dry_run_skipped"
        return result

    try:
        message = build_message(to, subject, body, cc=cc, reply_to_thread_id=thread_id, html=html)
        sent = service.users().messages().send(userId="me", body=message).execute()
        global _send_count
        _send_count += 1

        result["status"] = "sent"
        result["message_id"] = sent.get("id")
        logger.info(f"Email sent to {to} | Gmail ID: {sent.get('id')}")

    except HttpError as e:
        result["status"] = f"error: {e}"
        logger.error(f"Gmail send failed: {e}")
        raise

    return result


def process_approval_file(filepath: Path, service, dry_run: bool = False) -> dict:
    """
    Parse an approval .md file and send the email.
    Expected frontmatter fields: to, subject, body (or ## Email Body section).
    Returns result dict.
    """
    content = filepath.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Parse frontmatter
    fm = {}
    in_fm = False
    fm_count = 0
    body_lines = []

    for line in lines:
        if line.strip() == "---":
            fm_count += 1
            if fm_count == 1:
                in_fm = True
                continue
            elif fm_count == 2:
                in_fm = False
                continue
        if in_fm and ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"')
        elif fm_count >= 2:
            body_lines.append(line)

    body_text = "\n".join(body_lines)

    # Extract email body from "## Email Body" or "## Body" section
    email_body = ""
    for section_header in ["## Email Body", "## Body", "## Email Content"]:
        if section_header in body_text:
            parts = body_text.split(section_header, 1)
            after = parts[1]
            # Stop at next ## section
            next_section = after.find("\n## ")
            if next_section > 0:
                after = after[:next_section]
            # Strip "To:", "Subject:" lines
            filtered = [
                ln for ln in after.split("\n")
                if not ln.startswith("**To:**")
                and not ln.startswith("**Subject:**")
                and not ln.startswith("**CC:**")
            ]
            email_body = "\n".join(filtered).strip()
            break

    to = fm.get("to", "")
    subject = fm.get("subject", "(No Subject)")
    cc = fm.get("cc", "")
    thread_id = fm.get("thread_id", fm.get("reply_to_thread_id", ""))

    if not to:
        raise ValueError(f"No 'to' field found in {filepath.name}")
    if not email_body:
        raise ValueError(f"No email body found in {filepath.name}. Add a '## Email Body' section.")

    return send_email(service, to, subject, email_body, cc=cc, thread_id=thread_id, dry_run=dry_run)


def log_result(vault_path: Path, result: dict, filename: str):
    """Append send result to daily log."""
    logs_dir = vault_path / "Logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"

    existing = []
    if log_file.exists():
        try:
            existing = json.loads(log_file.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    existing.append({
        "action_type": "email_send",
        "file": filename,
        "actor": "gmail_sender",
        **result,
    })
    log_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — Gmail Sender (Silver Tier MCP Action)"
    )
    parser.add_argument(
        "--credentials",
        default="Credentials.json",
        help="Path to Gmail OAuth credentials JSON (default: Credentials.json)",
    )
    parser.add_argument("--to", help="Recipient email address")
    parser.add_argument("--subject", default="Message from AI Employee", help="Email subject")
    parser.add_argument("--body", help="Email body text")
    parser.add_argument("--cc", default="", help="CC recipient(s)")
    parser.add_argument("--thread-id", default="", help="Thread ID for replies")
    parser.add_argument(
        "--approval-file",
        help="Path to an approval .md file to process (instead of --to/--subject/--body)",
    )
    parser.add_argument(
        "--vault",
        default=".",
        help="Path to vault (for logging). Default: current directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be sent without actually sending",
    )
    parser.add_argument(
        "--authorize",
        action="store_true",
        help="Authorize Gmail send scope and exit",
    )
    args = parser.parse_args()

    # Resolve credentials
    creds_path = Path(args.credentials)
    if not creds_path.is_absolute():
        creds_path = Path.cwd() / creds_path

    service = get_send_service(str(creds_path))

    if args.authorize:
        print("Gmail send authorization complete.")
        return

    vault_path = Path(args.vault).resolve()
    result = {}

    if args.approval_file:
        approval_path = Path(args.approval_file)
        if not approval_path.exists():
            print(f"ERROR: Approval file not found: {approval_path}")
            sys.exit(1)
        result = process_approval_file(approval_path, service, dry_run=args.dry_run)
        log_result(vault_path, result, approval_path.name)
    elif args.to and args.body:
        result = send_email(
            service,
            to=args.to,
            subject=args.subject,
            body=args.body,
            cc=args.cc,
            thread_id=args.thread_id,
            dry_run=args.dry_run,
        )
        log_result(vault_path, result, "cli_send")
    else:
        parser.print_help()
        print("\nERROR: Provide either --approval-file or both --to and --body")
        sys.exit(1)

    print(f"Result: {result['status']}")
    if result.get("message_id"):
        print(f"Gmail Message ID: {result['message_id']}")


if __name__ == "__main__":
    main()
