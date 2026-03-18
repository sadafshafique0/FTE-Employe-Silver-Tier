---
name: whatsapp-watcher
description: >
  Silver Tier WhatsApp monitoring skill. Use this skill to start, stop, or
  manage the WhatsApp Web watcher that monitors incoming messages for business
  keywords and creates Needs_Action files. Triggers on: "start WhatsApp watcher",
  "monitor WhatsApp", "check WhatsApp messages", "WhatsApp setup", "scan QR code".
---

# WhatsApp Watcher Skill

Monitors WhatsApp Web for business-critical messages and queues them in the vault.

## How It Works

The `whatsapp_watcher.py` script uses Playwright to automate WhatsApp Web in a
persistent browser session. It polls every 30 seconds for unread messages
containing business keywords like `urgent`, `invoice`, `payment`, `proposal`.

When triggered, it creates a `WHATSAPP_<sender>_<timestamp>.md` file in `/Needs_Action/`.

---

## Setup (First Time)

### Step 1 — Install dependencies
```bash
pip install playwright
playwright install chromium
```

### Step 2 — Scan QR code (headful mode)
```bash
python watchers/whatsapp_watcher.py --vault ./vault --setup
```
A browser window opens → scan QR in WhatsApp on your phone → session saved.

### Step 3 — Run headless (normal operation)
```bash
python watchers/whatsapp_watcher.py --vault ./vault
```

---

## Starting the Watcher

```bash
# Background (recommended)
python watchers/whatsapp_watcher.py --vault ./vault &

# With custom session directory
python watchers/whatsapp_watcher.py --vault ./vault --session-dir ./watchers/whatsapp_session
```

## Stopping the Watcher

```bash
# Find the process
pgrep -f "whatsapp_watcher"

# Kill it
pkill -f "whatsapp_watcher"
```

---

## Needs_Action File Created

For each triggered message, a file is created:

```
vault/Needs_Action/WHATSAPP_ClientName_2026-03-18_09-30-00.md
```

```yaml
---
type: whatsapp_message
source: whatsapp_web
from: Client Name
received: 2026-03-18T09:30:00
keywords_matched: invoice, payment
priority: high
status: pending
---

## WhatsApp Message Preview
...
```

---

## Trigger Keywords

| Keyword | Business Context |
|---------|-----------------|
| urgent / asap | Needs immediate attention |
| invoice / payment | Financial action required |
| proposal / contract | Sales opportunity |
| pricing | Lead capture |
| meeting / call me | Calendar action |
| help / emergency | Support needed |

To add keywords, edit `watchers/whatsapp_watcher.py` → `TRIGGER_KEYWORDS` list.

---

## Processing WhatsApp Items

After the watcher creates a Needs_Action file, the vault-manager skill handles it:

1. Reads the message preview
2. Classifies priority
3. If invoice/payment → creates approval request in `/Pending_Approval/`
4. If meeting request → creates plan with calendar action
5. Moves processed file to `/Done/`

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| QR code expired | Re-run with `--setup` to re-scan |
| Session lost after restart | Normal — re-run `--setup` once |
| No messages detected | Check keyword list matches your business |
| Playwright not found | `pip install playwright && playwright install chromium` |
| Browser crashes | Delete `watchers/whatsapp_session/` and re-setup |

---

## Security Notes

- WhatsApp session stored locally in `watchers/whatsapp_session/` — never commit this
- Add to `.gitignore`: `watchers/whatsapp_session/`
- WhatsApp Web automation may violate WhatsApp ToS — use for personal/business accounts only
- Session contains auth tokens — treat like a password
