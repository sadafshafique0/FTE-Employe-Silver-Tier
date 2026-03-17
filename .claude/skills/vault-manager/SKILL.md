---
name: vault-manager
description: >
  AI Employee vault operations skill. Use this skill whenever the user asks to process
  the vault, handle Needs_Action items, update Dashboard.md, create plan files, move
  tasks to Done, or perform any read/write operation on the Obsidian vault. Triggers on:
  "check the vault", "process inbox", "what needs action", "update dashboard",
  "process tasks", "check Needs_Action", "create a plan", "mark as done",
  "what's pending", or any request involving vault files or folders.
---

# Vault Manager Skill

Manages the AI Employee's Obsidian vault: reads tasks, creates plans, updates the dashboard, and moves files through the workflow.

## Vault Structure

```
vault/
├── Dashboard.md          ← Real-time summary (update after every action)
├── Company_Handbook.md   ← Rules of engagement (read before acting)
├── Business_Goals.md     ← Business context and targets
├── Inbox/                ← Drop zone for new files (watcher moves to Needs_Action)
├── Needs_Action/         ← Items queued for processing
├── Plans/                ← Plan.md files Claude creates for multi-step tasks
├── Done/                 ← Completed items (never delete, always move here)
├── Pending_Approval/     ← Items awaiting human approval
├── Approved/             ← Human-approved items (trigger the action)
├── Rejected/             ← Human-rejected items (log and stop)
└── Logs/                 ← Audit log files (YYYY-MM-DD.json)
```

## Standard Workflow

### On every session start:
1. Read `Company_Handbook.md` to load rules
2. Read `Dashboard.md` for current state
3. List all files in `/Needs_Action/`
4. Process each item (see Processing Rules below)
5. Update `Dashboard.md` when done

### Processing a Needs_Action item:

```
1. Read the .md file to understand the task
2. Determine priority (urgent / high / normal / low)
3. For simple tasks: do the work, move file to /Done/
4. For multi-step tasks: create a Plan.md in /Plans/
5. For sensitive actions: create an approval file in /Pending_Approval/
6. Update Dashboard.md with activity log entry
```

### Creating a Plan file:

Save to `/Plans/PLAN_description_YYYY-MM-DD.md`:

```markdown
---
created: <ISO timestamp>
status: in_progress
related_file: <Needs_Action filename>
---

## Objective
<what needs to happen>

## Steps
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3 (REQUIRES APPROVAL — creates /Pending_Approval/ file)

## Notes
<any context or decisions made>
```

### Creating an Approval Request:

Save to `/Pending_Approval/ACTION_description_YYYY-MM-DD.md`:

```markdown
---
type: approval_request
action: <email_send | payment | delete | social_post>
created: <ISO timestamp>
expires: <24h later>
status: pending
---

## What I want to do
<clear description of the action>

## Why
<reason>

## To Approve
Move this file to /Approved/

## To Reject
Move this file to /Rejected/
```

### Updating Dashboard.md:

After any action, append to the `## Recent Activity` section:

```
- [YYYY-MM-DD HH:MM] <description of what was done>
```

Also update the **Inbox Summary** counts.

### Logging to /Logs/:

For any completed action, append a JSON entry to `/Logs/YYYY-MM-DD.json`:

```json
{
  "timestamp": "ISO-8601",
  "action_type": "file_processed | plan_created | approval_requested | task_completed",
  "description": "what happened",
  "result": "success | pending_approval | skipped"
}
```

## Rules (from Company_Handbook.md)

- NEVER take irreversible actions without a file in /Approved/
- NEVER delete files — move to /Done/ or /Rejected/
- ALWAYS read Company_Handbook.md before acting on anything sensitive
- ALWAYS update Dashboard.md after processing
- If uncertain about any action → create NEEDS_CLARIFICATION_ file in /Needs_Action/

## Example: Processing a File Drop

**Input:** `Needs_Action/FILE_report-q1_2026-03-14.md`

**Actions:**
1. Read the metadata file
2. Read the actual file it references
3. Summarize the content
4. Create `Plans/PLAN_process-q1-report_2026-03-14.md` with summary + next steps
5. Move the original Needs_Action file to `Done/`
6. Append to Dashboard.md activity log
7. Log to `Logs/2026-03-14.json`
