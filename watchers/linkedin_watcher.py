"""
linkedin_watcher.py — Silver Tier LinkedIn Watcher & Auto-Poster.

Two jobs in one script:
  1. MONITOR: Poll LinkedIn notifications every 5 minutes for business
     opportunities (connection requests, messages, mentions) and create
     Needs_Action vault files.
  2. POST: Watch /Approved/LINKEDIN_POST_*.md files and auto-publish them
     to LinkedIn via Playwright browser automation.

Setup:
    1. Install playwright: pip install playwright && playwright install chromium
    2. First-time login (opens visible browser):
          python watchers/linkedin_watcher.py --vault ./vault --setup
       → Log in to LinkedIn in the browser, wait 5 seconds, then close it.
       → Session is saved to watchers/linkedin_session/
    3. Normal headless run:
          python watchers/linkedin_watcher.py --vault ./vault

LinkedIn Post Workflow:
    1. Claude drafts a post → saves to vault/Pending_Approval/LINKEDIN_POST_<topic>_<date>.md
    2. Human reviews and moves file to vault/Approved/
    3. This watcher detects the file and publishes it to LinkedIn
    4. Moves file to vault/Done/ and logs the action

Requirements:
    pip install playwright
    playwright install chromium
"""

import argparse
import sys
import json
import re
from pathlib import Path
from datetime import datetime
import logging

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LinkedInWatcher] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("linkedin_watcher")

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("ERROR: Playwright not installed.")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)

DEFAULT_SESSION_DIR = Path(__file__).parent / "linkedin_session"
LINKEDIN_HOME = "https://www.linkedin.com/feed/"
LINKEDIN_NOTIFS = "https://www.linkedin.com/notifications/"

# Notification keywords worth acting on
OPPORTUNITY_KEYWORDS = [
    "viewed your profile",
    "sent you a message",
    "connection request",
    "mentioned you",
    "wants to connect",
    "responded to your",
    "liked your",
    "commented on",
    "job opportunity",
    "collaboration",
    "proposal",
    "speaking",
    "partnership",
]


# ──────────────────────────────────────────────
# LinkedIn Post Publisher
# ──────────────────────────────────────────────

def parse_post_file(filepath: Path) -> str:
    """Extract the post body from a LINKEDIN_POST_*.md approval file."""
    content = filepath.read_text(encoding="utf-8")
    # Find ## Post Content section
    for header in ["## Post Content", "## LinkedIn Post", "## Content"]:
        if header in content:
            after = content.split(header, 1)[1]
            # Stop at next ##
            next_h = after.find("\n## ")
            if next_h > 0:
                after = after[:next_h]
            return after.strip()
    # Fallback: return everything after frontmatter
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return parts[2].strip()
    return content.strip()


def publish_linkedin_post(page, post_body: str, dry_run: bool = False) -> bool:
    """
    Publish a post to LinkedIn via Playwright.
    Returns True on success.
    """
    if dry_run:
        logger.info(f"[DRY RUN] Would post to LinkedIn:\n{post_body[:200]}...")
        return True

    try:
        logger.info("Navigating to LinkedIn feed...")
        page.goto(LINKEDIN_HOME, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Click "Start a post" button — try multiple selectors
        clicked = False
        for selector in [
            'button[aria-label="Start a post"]',
            'button:has-text("Start a post")',
            '[data-control-name="share.sharebox_feed_create_article"]',
            '.share-box-feed-entry__trigger',
        ]:
            try:
                page.click(selector, timeout=5000)
                clicked = True
                logger.info(f"Clicked post button via: {selector}")
                break
            except Exception:
                continue

        if not clicked:
            logger.error("Could not find 'Start a post' button. LinkedIn UI may have changed.")
            return False

        page.wait_for_timeout(2000)

        # Find the post editor and type content
        editor = None
        for selector in [
            '.ql-editor[contenteditable="true"]',
            '[role="textbox"]',
            'div[contenteditable="true"]',
        ]:
            try:
                editor = page.wait_for_selector(selector, timeout=5000)
                if editor:
                    logger.info(f"Found editor via: {selector}")
                    break
            except Exception:
                continue

        if not editor:
            logger.error("Could not find post editor.")
            return False

        # Type post content
        editor.click()
        page.keyboard.type(post_body, delay=10)
        page.wait_for_timeout(1000)

        # Verify content was entered
        typed_content = editor.inner_text()
        if not typed_content.strip():
            logger.warning("Editor appears empty after typing. Retrying with fill...")
            editor.fill(post_body)
            page.wait_for_timeout(1000)

        logger.info("Post content entered. Looking for Post button...")

        # Click the Post/Submit button
        posted = False
        for selector in [
            'button.share-actions__primary-action',
            'button[aria-label="Post"]',
            'button:has-text("Post")',
        ]:
            try:
                btn = page.wait_for_selector(selector, timeout=5000)
                if btn and btn.is_enabled():
                    btn.click()
                    posted = True
                    logger.info(f"Clicked post submit via: {selector}")
                    break
            except Exception:
                continue

        if not posted:
            logger.error("Could not find Post submit button.")
            return False

        # Wait for confirmation
        page.wait_for_timeout(3000)
        logger.info("LinkedIn post submitted successfully.")
        return True

    except PWTimeout as e:
        logger.error(f"Playwright timeout during post: {e}")
        return False
    except Exception as e:
        logger.error(f"Error publishing LinkedIn post: {e}", exc_info=True)
        return False


# ──────────────────────────────────────────────
# LinkedIn Notification Monitor
# ──────────────────────────────────────────────

def get_notifications(page) -> list[dict]:
    """Scrape LinkedIn notifications page for business-relevant items."""
    notifications = []
    try:
        logger.info("Checking LinkedIn notifications...")
        page.goto(LINKEDIN_NOTIFS, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Try multiple selectors for notification items
        items = []
        for selector in [
            '.notification-item',
            '.artdeco-list__item',
            '[data-urn*="notification"]',
        ]:
            items = page.query_selector_all(selector)
            if items:
                logger.info(f"Found {len(items)} notifications via: {selector}")
                break

        for item in items[:15]:  # Process up to 15 recent notifications
            try:
                text = item.inner_text().strip()
                text_lower = text.lower()
                matched = [kw for kw in OPPORTUNITY_KEYWORDS if kw in text_lower]
                if matched:
                    notifications.append({
                        "text": text[:500],
                        "keywords": matched,
                        "timestamp": datetime.now().isoformat(),
                    })
            except Exception:
                continue

        logger.info(f"Found {len(notifications)} relevant notifications")

    except PWTimeout:
        logger.warning("Notification page timed out. Session may have expired.")
    except Exception as e:
        logger.error(f"Error reading notifications: {e}", exc_info=True)

    return notifications


def is_logged_in(page) -> bool:
    """Check if the LinkedIn session is still active."""
    try:
        page.goto("https://www.linkedin.com/", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(1500)
        # If redirected to login page, session expired
        return "login" not in page.url and "authwall" not in page.url
    except Exception:
        return False


# ──────────────────────────────────────────────
# Main Watcher Class
# ──────────────────────────────────────────────

class LinkedInWatcher(BaseWatcher):
    """
    Silver Tier LinkedIn Watcher.
    - Polls LinkedIn notifications every 5 minutes.
    - Auto-publishes approved posts from /Approved/LINKEDIN_POST_*.md.
    - Creates Needs_Action files for business-relevant notifications.
    """

    def __init__(self, vault_path: str, session_dir: str = None, headless: bool = True, dry_run: bool = False):
        super().__init__(vault_path, check_interval=300)  # 5 minutes
        self.session_dir = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.dry_run = dry_run
        self.approved_dir = self.vault_path / "Approved"
        self.processed_notif_ids: set[str] = set()
        self._items_buffer: list[dict] = []

    def _get_approved_posts(self) -> list[Path]:
        """Return list of approved LinkedIn post files."""
        if not self.approved_dir.exists():
            return []
        return list(self.approved_dir.glob("LINKEDIN_POST_*.md"))

    def check_for_updates(self) -> list:
        """Run a browser session: check notifications + publish approved posts."""
        self._items_buffer = []

        approved_posts = self._get_approved_posts()

        # Only launch browser if there's something to do
        if not approved_posts:
            # Still check notifications on schedule
            pass

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    str(self.session_dir),
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                    viewport={"width": 1280, "height": 800},
                )
                page = browser.pages[0] if browser.pages else browser.new_page()

                # Check if still logged in
                if not is_logged_in(page):
                    self.logger.warning(
                        "LinkedIn session expired. Run --setup to re-login: "
                        "python watchers/linkedin_watcher.py --vault ./vault --setup"
                    )
                    browser.close()
                    return []

                # 1. Publish any approved posts
                for post_file in approved_posts:
                    self._publish_approved_post(page, post_file)

                # 2. Check notifications
                notifications = get_notifications(page)
                for notif in notifications:
                    notif_id = f"li_{hash(notif['text'][:80])}_{datetime.now().strftime('%Y%m%d')}"
                    if notif_id not in self.processed_notif_ids:
                        notif["id"] = notif_id
                        self._items_buffer.append(notif)
                        self.processed_notif_ids.add(notif_id)

                browser.close()

        except Exception as e:
            self.logger.error(f"Browser session error: {e}", exc_info=True)

        return self._items_buffer

    def _publish_approved_post(self, page, post_file: Path):
        """Publish one approved post and move it to Done."""
        self.logger.info(f"Publishing approved post: {post_file.name}")
        try:
            post_body = parse_post_file(post_file)
            if not post_body:
                self.logger.error(f"No post content found in {post_file.name}")
                return

            success = publish_linkedin_post(page, post_body, dry_run=self.dry_run)
            if success:
                done_path = self.done / post_file.name
                post_file.rename(done_path)
                self.logger.info(f"Post published & moved to Done: {post_file.name}")
                self.log_activity(f"LinkedIn post published: {post_file.name}")
                self._log_action(post_file.name, "linkedin_post_published", "success")
            else:
                self.logger.error(f"Failed to publish {post_file.name} — leaving in /Approved/")
                self._log_action(post_file.name, "linkedin_post_published", "failed")
        except Exception as e:
            self.logger.error(f"Error publishing {post_file.name}: {e}", exc_info=True)

    def _log_action(self, filename: str, action_type: str, result: str):
        """Write to daily JSON log."""
        logs_dir = self.vault_path / "Logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_file = logs_dir / f"{datetime.now().strftime('%Y-%m-%d')}.json"
        existing = []
        if log_file.exists():
            try:
                existing = json.loads(log_file.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.append({
            "timestamp": datetime.now().isoformat(),
            "action_type": action_type,
            "file": filename,
            "result": result,
            "dry_run": self.dry_run,
        })
        log_file.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    def create_action_file(self, item: dict) -> Path:
        """Create a Needs_Action file for a LinkedIn notification."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        md_path = self.needs_action / f"LINKEDIN_{timestamp}.md"

        md_content = f"""---
type: linkedin_notification
source: linkedin
notification_id: {item.get('id', 'unknown')}
received: {item['timestamp']}
keywords_matched: {', '.join(item['keywords'])}
priority: normal
status: pending
---

## LinkedIn Notification

{item['text']}

## Suggested Actions

- [ ] Review on LinkedIn
- [ ] Reply to message or connection request
- [ ] If collaboration opportunity: create Plan in /Plans/
- [ ] Move to /Done when handled

---
*Created automatically by LinkedInWatcher — Silver Tier*
"""
        md_path.write_text(md_content, encoding="utf-8")
        return md_path


# ──────────────────────────────────────────────
# Setup Mode
# ──────────────────────────────────────────────

def setup_linkedin_session(session_dir: Path):
    """Open a visible browser for the user to log in to LinkedIn."""
    print("\n" + "="*60)
    print("LinkedIn Session Setup")
    print("="*60)
    print("1. A browser window will open.")
    print("2. Log in to LinkedIn with your credentials.")
    print("3. Once logged in and on the LinkedIn feed, wait 5 seconds.")
    print("4. Close the browser — your session will be saved.")
    print("="*60 + "\n")

    session_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            str(session_dir),
            headless=False,
            args=["--no-sandbox"],
            viewport={"width": 1280, "height": 800},
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://www.linkedin.com/login")
        print("Browser opened. Please log in to LinkedIn...")
        print("Close the browser window when done.")
        try:
            # Wait until user closes the browser
            browser.wait_for_event("close", timeout=120000)
        except Exception:
            pass
        finally:
            try:
                browser.close()
            except Exception:
                pass

    print(f"\nSession saved to: {session_dir}")
    print("Run without --setup to start in headless mode.")


# ──────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — LinkedIn Watcher & Auto-Poster (Silver Tier)"
    )
    parser.add_argument("--vault", required=True, help="Path to Obsidian vault")
    parser.add_argument(
        "--session-dir",
        default=str(DEFAULT_SESSION_DIR),
        help="Playwright persistent session directory (stores LinkedIn login)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Open visible browser for initial LinkedIn login",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be posted without actually posting",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Poll interval in seconds (default: 300 = 5 min)",
    )
    parser.add_argument(
        "--post-only",
        action="store_true",
        help="Only process approved posts (skip notification monitoring)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    session_dir = Path(args.session_dir)

    if not vault_path.exists():
        print(f"ERROR: Vault path does not exist: {vault_path}")
        sys.exit(1)

    if args.setup:
        setup_linkedin_session(session_dir)
        return

    if not session_dir.exists():
        print(f"ERROR: LinkedIn session not found at: {session_dir}")
        print("Run setup first: python watchers/linkedin_watcher.py --vault ./vault --setup")
        sys.exit(1)

    print(f"Vault:      {vault_path}")
    print(f"Session:    {session_dir}")
    print(f"Headless:   True")
    print(f"Dry run:    {args.dry_run}")
    print(f"Interval:   {args.interval}s")
    print()

    watcher = LinkedInWatcher(
        str(vault_path),
        session_dir=str(session_dir),
        headless=True,
        dry_run=args.dry_run,
    )
    watcher.check_interval = args.interval
    watcher.run()


if __name__ == "__main__":
    main()
