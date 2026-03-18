---
name: gmail-sender
description: >
  Silver Tier email drafting and sending skill via Gmail API. Use this skill to
  draft, review, and send emails through Gmail. ALWAYS creates a human-approval
  file before sending — the orchestrator executes the send. Triggers on:
  "send email", "reply to email", "draft email", "write email", "compose email",
  "email reply", "send via Gmail", "email the client".
---

# Gmail Sender Skill

Draft emails with human approval, then auto-send via Gmail API (orchestrator).

## Architecture

```
Claude drafts → /Pending_Approval/EMAIL_SEND_*.md → Human approves (moves to /Approved/)
→ orchestrator.py detects → calls gmail_sender.py → email sent → /Done/
```

---

## Credentials Setup (One-Time)

`Credentials.json` is already in the project root. To authorize Gmail:

```bash
# Authorize Gmail (opens browser once — then token is saved)
python watchers/gmail_sender.py --credentials Credentials.json --authorize

# This saves watchers/gmail_send_token.json
# Future sends are automatic (no browser needed)
```

### Gmail API Scopes Used
- `gmail.send` — send emails
- `gmail.modify` — mark emails as read (watcher)

---

## Step 1 — Draft an Email (Claude's Job)

When the user asks to send/reply to an email, create this approval file:

**Save to:** `vault/Pending_Approval/EMAIL_SEND_<recipient-name>_<YYYY-MM-DD>.md`

```markdown
---
type: approval_request
action: email_send
created: 2026-03-18T10:00:00
expires: 2026-03-19T10:00:00
status: pending
to: recipient@example.com
cc:
subject: Re: Project Update
thread_id:
---

## What I want to do

Reply to John's email about the project update with revised timeline.

## Email Body

Hi John,

Thank you for your message. Here is the updated project timeline:

- Phase 1 (Design): March 25, 2026
- Phase 2 (Development): April 10, 2026
- Final Delivery: April 30, 2026

Please let me know if you have any questions.

Best regards,
[Your Name]

## Why

Client requested updated project status.

## To Approve
Move this file to /Approved/

## To Reject
Move this file to /Rejected/
```

**Important rules for the approval file:**
- `to:` must be a valid email address
- `action:` must be exactly `email_send`
- The `## Email Body` section must exist with the actual email text
- For replies, include `thread_id:` from the original email's Needs_Action file

---

## Step 2 — Human Reviews

In Obsidian, the human:
- **Approves**: Moves file to `vault/Approved/` → orchestrator sends it
- **Rejects**: Moves file to `vault/Rejected/` → no action taken

---

## Step 3 — Orchestrator Sends

The orchestrator runs continuously, watching `/Approved/`:

```bash
# Start orchestrator (it handles both Gmail sends and LinkedIn posts)
python watchers/orchestrator.py --vault ./vault --credentials Credentials.json
```

When it finds `EMAIL_SEND_*.md` in `/Approved/`, it calls:
```bash
python watchers/gmail_sender.py --approval-file vault/Approved/EMAIL_SEND_*.md \
    --credentials Credentials.json --vault ./vault
```

---

## Direct Send (CLI, for testing)

```bash
# Send directly (requires prior --authorize)
python watchers/gmail_sender.py \
    --credentials Credentials.json \
    --to "client@example.com" \
    --subject "Invoice #123" \
    --body "Please find the invoice attached." \
    --vault ./vault

# Dry run (won't actually send — safe for testing)
python watchers/gmail_sender.py --dry-run \
    --credentials Credentials.json \
    --to "test@example.com" \
    --subject "Test" \
    --body "Test body"
```

---

## Email Reply Templates

### Standard Reply
```
Hi [Name],

Thank you for your message.

[Specific response]

[Next steps or action item]

Best regards,
[Your Name]
```

### Invoice Delivery
```
Hi [Name],

Please find Invoice #[number] for [service/product] below.

Amount: $[amount]
Due Date: [date]
Payment: [bank transfer / PayPal / etc.]

Thank you for your business!

Best regards,
[Your Name]
```

### Meeting Request Response
```
Hi [Name],

Thank you for reaching out. I'm available on:

- [Day, Date] at [Time]
- [Day, Date] at [Time]

Please let me know which works best for you, or suggest an alternative time.

Looking forward to our conversation!

Best regards,
[Your Name]
```

---

## Rate Limits & Safety

| Limit | Value |
|-------|-------|
| Max emails/hour | 10 (enforced in code) |
| Gmail free daily limit | 500 emails/day |
| Gmail Workspace daily limit | 2,000 emails/day |

**Safety rules enforced:**
- NEVER sends without a file in `/Approved/`
- Rate limit resets every hour
- All sends logged to `vault/Logs/YYYY-MM-DD.json`
- Dry-run mode available for testing

---

## Audit Log Format

Every sent email is logged:

```json
{
  "timestamp": "2026-03-18T10:05:00",
  "action_type": "email_send",
  "file": "EMAIL_SEND_John_2026-03-18.md",
  "to": "john@example.com",
  "subject": "Re: Project Update",
  "status": "sent",
  "message_id": "18e1a2b3c4d5",
  "dry_run": false,
  "actor": "gmail_sender"
}
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `Credentials.json not found` | Ensure file is in project root directory |
| `Token expired` | Delete `watchers/gmail_send_token.json` and re-run `--authorize` |
| `403 Forbidden` | Gmail API not enabled or OAuth consent needs verification |
| Email not sending | Check `/Approved/` folder — file must be there and named `EMAIL_SEND_*.md` |
| Rate limit hit | Max 10/hour — wait until next hour |
| `## Email Body section missing` | Add `## Email Body` section to the approval file |
