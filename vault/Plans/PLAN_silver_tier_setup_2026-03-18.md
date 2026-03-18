---
created: 2026-03-18T16:00:00
status: completed
related_file: Dashboard.md
priority: high
---

## Objective

Set up all Silver Tier AI Employee capabilities: Gmail watcher, LinkedIn watcher,
orchestrator, email MCP server, approval workflow, and scheduling. Validate each
component end-to-end.

## Reasoning

This is a multi-component deployment requiring sequential setup because:
1. Gmail auth must come before watcher can run
2. LinkedIn session must be saved before watcher can post
3. Orchestrator depends on both Gmail token and vault structure
4. MCP server requires credentials already authorized

Estimated complexity: HIGH — 8 interdependent components across 3 external services.

## Steps

- [x] Step 1: Read hackathon requirements and scope all Silver Tier deliverables
- [x] Step 2: Create Agent Skills (.claude/skills/) for all AI capabilities
- [x] Step 3: Build gmail_watcher.py — polls inbox, creates Needs_Action files
- [x] Step 4: Authorize Gmail (OAuth2, gmail.modify + gmail.send scopes)
- [x] Step 5: Build gmail_sender.py — sends approved emails via Gmail API
- [x] Step 6: Build linkedin_watcher.py — monitors notifications + publishes posts
- [x] Step 7: Authenticate LinkedIn session via Playwright (--setup mode)
- [x] Step 8: Build orchestrator.py — polls /Approved/, routes actions
- [x] Step 9: Build whatsapp_watcher.py — monitors WhatsApp Web for keywords
- [x] Step 10: Test LinkedIn post end-to-end (draft → approve → publish)
- [x] Step 11: Test email delete/spam via checkbox-driven automation
- [x] Step 12: Build email_mcp_server.py — MCP protocol server for Gmail tools
- [x] Step 13: Register MCP server in .claude/settings.json
- [x] Step 14: Create start_watchers.bat and .sh for one-click startup
- [x] Step 15: Push all code to github.com/sadafshafique0/FTE-Employe-Silver-Tier

## Notes

- LinkedIn session expires periodically — re-run `--setup` to refresh
- Gmail tokens persist in watchers/gmail_token.json and gmail_send_token.json
- Orchestrator polls every 10s — no manual restart needed after checkbox actions
- MCP server runs over stdio — Claude Code connects automatically via settings.json
- Rate limit: 10 emails/hour enforced in gmail_sender.py
