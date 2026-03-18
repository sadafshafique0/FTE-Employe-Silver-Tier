---
name: scheduler
description: >
  Silver Tier scheduling skill. Use this skill to set up automated recurring
  tasks using Windows Task Scheduler or cron (Mac/Linux). Schedules daily
  briefings, weekly audits, watcher restarts, and other time-based operations.
  Triggers on: "schedule task", "run daily", "every morning", "cron job",
  "automate schedule", "Task Scheduler", "recurring task", "weekly briefing",
  "daily summary", "schedule watcher".
---

# Scheduler Skill

Set up automated recurring tasks for the AI Employee using Windows Task Scheduler or cron.

## Scheduled Operations (Silver Tier)

| Schedule | Task | Trigger |
|----------|------|---------|
| Daily 8:00 AM | Morning briefing — summarize Needs_Action | Task Scheduler / cron |
| Every 2 min | Gmail watcher check interval | Built into script |
| Every 30 sec | WhatsApp watcher check interval | Built into script |
| Every 5 min | LinkedIn watcher check interval | Built into script |
| Sunday 9:00 PM | Weekly business audit | Task Scheduler / cron |
| On startup | Start all watchers | Startup script |

---

## Windows Task Scheduler Setup

### Create a scheduled task (PowerShell — run as Admin)

```powershell
# Daily Morning Briefing at 8:00 AM
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument '/c "cd /d C:\path\to\FTE-Employe-Silver-Tier && claude --print \"Process all items in Needs_Action and generate a morning briefing\" >> vault\Logs\morning-briefing.log 2>&1"'

$trigger = New-ScheduledTaskTrigger -Daily -At "08:00AM"

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName "AIEmployee-MorningBriefing" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest
```

### Weekly Audit (Sunday 9:00 PM)

```powershell
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument '/c "cd /d C:\path\to\FTE-Employe-Silver-Tier && claude --print \"Run weekly business audit and generate CEO briefing\" >> vault\Logs\weekly-audit.log 2>&1"'

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "09:00PM"

Register-ScheduledTask `
    -TaskName "AIEmployee-WeeklyAudit" `
    -Action $action `
    -Trigger $trigger `
    -RunLevel Highest
```

### Start Watchers on System Startup

```powershell
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument '/c "cd /d C:\path\to\FTE-Employe-Silver-Tier && python watchers\gmail_watcher.py --vault vault --credentials watchers\credentials.json"'

$trigger = New-ScheduledTaskTrigger -AtStartup

Register-ScheduledTask `
    -TaskName "AIEmployee-GmailWatcher" `
    -Action $action `
    -Trigger $trigger `
    -RunLevel Highest
```

### View and Manage Tasks

```powershell
# List all AI Employee tasks
Get-ScheduledTask | Where-Object {$_.TaskName -like "AIEmployee-*"}

# Run a task immediately
Start-ScheduledTask -TaskName "AIEmployee-MorningBriefing"

# Disable a task
Disable-ScheduledTask -TaskName "AIEmployee-WeeklyAudit"

# Delete a task
Unregister-ScheduledTask -TaskName "AIEmployee-MorningBriefing" -Confirm:$false
```

---

## Linux/Mac Cron Setup

### Edit crontab
```bash
crontab -e
```

### Add these entries
```cron
# Daily morning briefing at 8:00 AM
0 8 * * * cd /path/to/FTE-Employe-Silver-Tier && claude --print "Process all items in Needs_Action and generate a morning briefing" >> vault/Logs/morning-briefing.log 2>&1

# Weekly business audit — Sunday 9:00 PM
0 21 * * 0 cd /path/to/FTE-Employe-Silver-Tier && claude --print "Run weekly business audit and generate CEO briefing" >> vault/Logs/weekly-audit.log 2>&1

# Start Gmail watcher at boot (add to rc.local or systemd service)
@reboot cd /path/to/FTE-Employe-Silver-Tier && python watchers/gmail_watcher.py --vault ./vault --credentials watchers/credentials.json &

# Start WhatsApp watcher at boot
@reboot cd /path/to/FTE-Employe-Silver-Tier && python watchers/whatsapp_watcher.py --vault ./vault &

# Start LinkedIn watcher at boot
@reboot cd /path/to/FTE-Employe-Silver-Tier && python watchers/linkedin_watcher.py --vault ./vault &
```

---

## Startup Script

Create `start_watchers.bat` (Windows) or `start_watchers.sh` (Mac/Linux):

### Windows (`start_watchers.bat`)
```bat
@echo off
cd /d C:\path\to\FTE-Employe-Silver-Tier
echo Starting AI Employee Watchers...

start "Gmail Watcher" python watchers\gmail_watcher.py --vault vault --credentials watchers\credentials.json
start "WhatsApp Watcher" python watchers\whatsapp_watcher.py --vault vault
start "LinkedIn Watcher" python watchers\linkedin_watcher.py --vault vault

echo All watchers started.
```

### Mac/Linux (`start_watchers.sh`)
```bash
#!/bin/bash
cd /path/to/FTE-Employe-Silver-Tier

python watchers/gmail_watcher.py --vault ./vault --credentials watchers/credentials.json &
echo "Gmail Watcher started (PID: $!)"

python watchers/whatsapp_watcher.py --vault ./vault &
echo "WhatsApp Watcher started (PID: $!)"

python watchers/linkedin_watcher.py --vault ./vault &
echo "LinkedIn Watcher started (PID: $!)"

echo "All watchers running. Use 'pkill -f watcher' to stop all."
```

---

## Morning Briefing Prompt

When the scheduler triggers the morning briefing, Claude should:

1. Read `vault/Dashboard.md` for current state
2. List all files in `vault/Needs_Action/`
3. Summarize pending items by priority
4. Check `vault/Business_Goals.md` for goal progress
5. Generate a briefing and save to `vault/Plans/BRIEFING_<date>.md`
6. Update Dashboard.md with briefing summary

**Briefing Template:**
```markdown
# Morning Briefing — 2026-03-18

## Status
- Needs Action: X items
- Pending Approval: X items
- Completed Today: X items

## Priority Queue
1. [URGENT] Item description
2. [HIGH] Item description
3. [NORMAL] Item description

## Business Goals Progress
- Revenue MTD: $X / $10,000 target
- Active Projects: X

## Recommended Actions
1. ...
2. ...
```

---

## Scheduled Task Vault Integration

For task scheduling via vault, create a file in `/Needs_Action/`:

```markdown
---
type: scheduled_task
schedule: "2026-03-20 09:00"
recurrence: weekly
action: linkedin_post
topic: Q1 results
priority: normal
---

Create and post a LinkedIn update about Q1 business results.
```

The scheduler skill processes these when they appear in Needs_Action.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Task not running | Check Task Scheduler → History tab for errors |
| Claude not found | Add `claude` to system PATH |
| Watcher already running | Check Task Manager / `pgrep -f watcher` |
| Log file not created | Ensure Logs/ directory exists in vault |
