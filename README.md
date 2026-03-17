# Personal AI Employee — Bronze Tier

> *Your life and business on autopilot. Local-first, agent-driven, human-in-the-loop.*

A Bronze Tier implementation of the Personal AI Employee from the [Panaversity Hackathon](https://github.com/panaversity). Built with Claude Code + Obsidian vault architecture.

---

## What's Included (Bronze Tier)

| Deliverable | Status |
|---|---|
| Obsidian vault with `Dashboard.md` | ✅ |
| `Company_Handbook.md` (rules of engagement) | ✅ |
| Folder structure: Inbox / Needs_Action / Done | ✅ |
| File System Watcher script | ✅ |
| Gmail Watcher script (optional) | ✅ |
| Agent Skill: `vault-manager` | ✅ |
| `CLAUDE.md` (AI Employee configuration) | ✅ |

---

## Quick Start

### 1. Install dependencies

```bash
# Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# Install required packages
pip install watchdog
```

### 2. Open vault in Obsidian

1. Open Obsidian → "Open folder as vault"
2. Select the `vault/` folder in this repo
3. You'll see `Dashboard.md` as your home screen

### 3. Start Claude Code as your AI Employee

```bash
# Run from this directory — Claude reads CLAUDE.md automatically
claude
```

Claude will:
- Read `Company_Handbook.md` rules
- Check `Dashboard.md` status
- List items in `Needs_Action/`
- Announce it's ready

### 4. Start the File System Watcher

In a separate terminal:

```bash
python watchers/filesystem_watcher.py --vault ./vault
```

Now **drop any file into `vault/Inbox/`** — the watcher will automatically create a `Needs_Action` entry and Claude can process it.

---

## How It Works

```
[You drop a file in /Inbox/]
        ↓
[FileSystemWatcher detects it]
        ↓
[Creates FILE_*.md in /Needs_Action/]
        ↓
[Claude reads it, creates a Plan in /Plans/]
        ↓
[For sensitive actions → creates /Pending_Approval/ file]
        ↓
[You move approval file to /Approved/]
        ↓
[Claude executes + logs + moves to /Done/]
        ↓
[Dashboard.md updated]
```

---

## Vault Folder Reference

| Folder | Purpose |
|---|---|
| `Inbox/` | Drop zone — put any file here for the AI to pick up |
| `Needs_Action/` | Items waiting to be processed by Claude |
| `Plans/` | Multi-step plans Claude creates |
| `Done/` | Completed items (never deleted) |
| `Pending_Approval/` | Actions waiting for your approval |
| `Approved/` | Move files here to approve an action |
| `Rejected/` | Move files here to reject an action |
| `Logs/` | Daily audit logs in JSON format |

---

## Customizing Your AI Employee

Edit `vault/Company_Handbook.md` to:
- Change communication tone and rules
- Adjust approval thresholds
- Add your business context (name, clients, rate card)
- Set priority keywords

Edit `vault/Business_Goals.md` to:
- Set revenue targets
- List active projects
- Define KPI alert thresholds

---

## Optional: Gmail Watcher

Requires Google API setup:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Enable the Gmail API
3. Download `credentials.json` to the `watchers/` folder
4. Run:

```bash
pip install google-auth google-auth-oauthlib google-api-python-client
python watchers/gmail_watcher.py --vault ./vault --credentials watchers/credentials.json
```

> ⚠️ Never commit `credentials.json` or `gmail_token.json` to git. They're in `.gitignore`.

---

## Security Notes

- Credentials must NEVER be committed to git
- All sensitive actions require human approval via file move
- `.env` files are gitignored by default
- Audit logs stored in `vault/Logs/` — retain 90 days minimum

---

## Architecture

```
EXTERNAL SOURCES          PERCEPTION           VAULT (Obsidian)
Gmail / File drops  →  Watcher Scripts  →  Needs_Action/
                                              ↓
                                         REASONING (Claude Code)
                                         Reads Company_Handbook.md
                                         Creates Plans/
                                              ↓
                         HUMAN-IN-LOOP ← Pending_Approval/
                                              ↓ (approved)
                                         ACTION (MCP - Silver+)
                                              ↓
                                         Done/ + Logs/ + Dashboard.md
```

---

## Tier Roadmap

| Tier | Features |
|------|----------|
| **Bronze ← You are here** | Vault + File Watcher + Claude reads/writes |
| Silver | Gmail + WhatsApp + LinkedIn + Email MCP + Cron |
| Gold | Full cross-domain + Odoo + Ralph Wiggum loop |
| Platinum | Cloud 24/7 + Always-on + Local/Cloud split |

---

## Submission

- **Tier:** Bronze
- **Primary Tool:** Claude Code
- **All AI functionality:** Implemented as Agent Skills (see `.claude/skills/`)
- **Demo:** Drop a file in `vault/Inbox/`, run Claude, show Dashboard update
