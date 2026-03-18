"""
whatsapp_watcher.py — Silver Tier WhatsApp Watcher.

Monitors WhatsApp Web for unread messages containing business keywords
and creates Needs_Action files for the AI Employee to process.

NOTE: Uses WhatsApp Web automation via Playwright. WhatsApp requires a
persistent browser session (QR scan once, then headless). Be aware of
WhatsApp's Terms of Service regarding automation.

Setup:
    1. Install playwright: pip install playwright && playwright install chromium
    2. First run (headful to scan QR): python whatsapp_watcher.py --vault /path/to/vault --setup
    3. Normal run (headless):          python whatsapp_watcher.py --vault /path/to/vault

Requirements:
    pip install playwright watchdog
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
except ImportError:
    print("ERROR: Playwright not installed.")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# Persistent session stored next to this file
DEFAULT_SESSION_DIR = Path(__file__).parent / "whatsapp_session"

# Keywords that trigger a Needs_Action file
TRIGGER_KEYWORDS = [
    "urgent", "asap", "invoice", "payment", "help",
    "price", "pricing", "proposal", "contract", "deadline",
    "emergency", "important", "call me", "meeting",
]


class WhatsAppWatcher(BaseWatcher):
    """
    Polls WhatsApp Web every 30 seconds for unread messages containing
    business-relevant keywords. Creates a Needs_Action .md file for each.
    """

    def __init__(self, vault_path: str, session_dir: str = None, headless: bool = True):
        super().__init__(vault_path, check_interval=30)
        self.session_dir = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.processed_ids: set[str] = set()

    def _get_unread_messages(self, page) -> list[dict]:
        """Navigate to WhatsApp Web and extract unread keyword messages."""
        messages = []
        try:
            page.goto("https://web.whatsapp.com", wait_until="domcontentloaded")
            page.wait_for_selector('[data-testid="chat-list"]', timeout=30000)

            # Find all unread chat elements
            unread_chats = page.query_selector_all('[aria-label*="unread"]')
            if not unread_chats:
                # Fallback: look for unread badges
                unread_chats = page.query_selector_all('[data-testid="icon-unread-count"]')

            for chat_el in unread_chats:
                try:
                    # Try to get chat container text
                    parent = chat_el.evaluate_handle(
                        "el => el.closest('[role=\"listitem\"]') || el.parentElement"
                    )
                    text = parent.as_element().inner_text().lower() if parent.as_element() else ""
                    sender = ""
                    try:
                        sender_el = parent.as_element().query_selector('[data-testid="cell-frame-title"]')
                        sender = sender_el.inner_text() if sender_el else "Unknown"
                    except Exception:
                        sender = "Unknown"

                    # Only trigger on keyword matches
                    matched_kw = [kw for kw in TRIGGER_KEYWORDS if kw in text]
                    if not matched_kw:
                        continue

                    # Build unique ID to avoid duplicates
                    msg_id = f"{sender}_{datetime.now().strftime('%Y%m%d_%H%M')}"
                    if msg_id in self.processed_ids:
                        continue

                    messages.append({
                        "id": msg_id,
                        "sender": sender,
                        "preview": text[:300],
                        "keywords": matched_kw,
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception as e:
                    self.logger.warning(f"Could not parse chat element: {e}")

        except PWTimeoutError:
            self.logger.warning("WhatsApp Web timed out waiting for chat list. Is the session active?")
        except Exception as e:
            self.logger.error(f"Error reading WhatsApp Web: {e}", exc_info=True)

        return messages

    def check_for_updates(self) -> list:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                str(self.session_dir),
                headless=self.headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            messages = self._get_unread_messages(page)
            browser.close()
        return messages

    def create_action_file(self, message: dict) -> Path:
        safe_sender = "".join(c if c.isalnum() or c in "-_" else "_" for c in message["sender"])
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        md_path = self.needs_action / f"WHATSAPP_{safe_sender}_{timestamp}.md"

        md_content = f"""---
type: whatsapp_message
source: whatsapp_web
message_id: {message['id']}
from: {message['sender']}
received: {message['timestamp']}
keywords_matched: {', '.join(message['keywords'])}
priority: high
status: pending
---

## WhatsApp Message Preview

{message['preview']}

## Suggested Actions

- [ ] Read full message in WhatsApp
- [ ] Draft a reply
- [ ] If invoice/payment requested: create approval file in /Pending_Approval/
- [ ] Move to /Done when handled

---
*Created automatically by WhatsAppWatcher — Silver Tier*
"""
        md_path.write_text(md_content, encoding="utf-8")
        self.processed_ids.add(message["id"])
        return md_path


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — WhatsApp Watcher (Silver Tier)"
    )
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument(
        "--session-dir",
        default=str(DEFAULT_SESSION_DIR),
        help="Path to Playwright persistent session directory (stores WhatsApp login)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run headful (visible browser) for initial QR code scan",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    headless = not args.setup
    if args.setup:
        print("SETUP MODE: A browser window will open. Scan the QR code in WhatsApp.")
        print("After scanning, keep the browser open for 10 seconds, then close it.")
        print("Your session will be saved. Re-run without --setup for headless mode.")

    watcher = WhatsAppWatcher(str(vault_path), args.session_dir, headless=headless)
    watcher.run()


if __name__ == "__main__":
    main()
