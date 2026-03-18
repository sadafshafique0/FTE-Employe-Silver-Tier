---
name: linkedin-poster
description: >
  Silver Tier LinkedIn automation skill. Draft and post LinkedIn content to
  generate business leads and sales. Full human-in-the-loop: Claude drafts →
  human approves → linkedin_watcher.py auto-publishes via Playwright.
  Triggers on: "post on LinkedIn", "LinkedIn post", "create LinkedIn content",
  "generate LinkedIn post", "post about my business", "LinkedIn marketing",
  "promote on LinkedIn", "social media post".
---

# LinkedIn Poster Skill

Draft, approve, and auto-publish LinkedIn posts for lead generation.

## Full Workflow

```
1. User asks → Claude drafts post
2. Claude saves to vault/Pending_Approval/LINKEDIN_POST_<topic>_<date>.md
3. Human reviews in Obsidian → moves to vault/Approved/
4. linkedin_watcher.py detects → publishes via Playwright → moves to Done/
```

---

## LinkedIn Watcher Setup (Required — One Time)

```bash
# Step 1: Install Playwright
pip install playwright
playwright install chromium

# Step 2: Login to LinkedIn (opens visible browser)
python watchers/linkedin_watcher.py --vault ./vault --setup
```
In the browser: log in to LinkedIn → wait on the feed for 5 seconds → close browser.
Session saved to `watchers/linkedin_session/`.

```bash
# Step 3: Start watcher (headless — monitors + auto-posts)
python watchers/linkedin_watcher.py --vault ./vault
```

---

## Step 1 — Drafting a LinkedIn Post (Claude's Job)

When asked to post on LinkedIn, first read `vault/Business_Goals.md` for context,
then save this approval file:

**Save to:** `vault/Pending_Approval/LINKEDIN_POST_<topic>_<YYYY-MM-DD>.md`

```markdown
---
type: approval_request
action: linkedin_post
created: 2026-03-18T09:00:00
expires: 2026-03-19T09:00:00
status: pending
topic: Q1 results announcement
---

## What I want to post

Announce Q1 2026 results and attract new clients.

## Post Content

🚀 Q1 2026 Results — We hit 145% of our revenue target!

Here's what worked for our clients this quarter:

→ Automated their email follow-ups → 3x response rate
→ Streamlined invoicing → 40% faster payments
→ Set up AI-assisted scheduling → 5 hours saved per week

The common thread? Systems that work while you sleep.

If you're a [target audience] looking to scale without burning out, let's talk.

DM me "SYSTEMS" and I'll share our exact framework.

#AI #Automation #BusinessGrowth #Productivity #Entrepreneurship

## Why

Q1 results are strong — good time to attract new clients and build credibility.

## To Approve
Move this file to /Approved/

## To Reject
Move this file to /Rejected/
```

**Critical:** The `## Post Content` section is what gets published word-for-word.

---

## Step 2 — Human Approves

In Obsidian, move the file:
- To `vault/Approved/` → post will be published automatically
- To `vault/Rejected/` → no action, file logged

---

## Step 3 — Auto-Publish

`linkedin_watcher.py` runs every 5 minutes, scans `/Approved/` for `LINKEDIN_POST_*.md` files, and publishes them via Playwright. On success, file moves to `/Done/`.

---

## LinkedIn Post Templates

### Lead Generation (Problem → Solution → CTA)
```
🎯 [Bold hook: problem your audience has]

Most [target audience] struggle with [specific pain point].

Here's what we've found works:

→ [Tip 1]
→ [Tip 2]
→ [Tip 3]

The result? [Outcome/transformation]

If you're ready to [desired result], DM me "[keyword]" — I'll share our framework.

#[Niche] #[Industry] #[Topic]
```

### Social Proof (Client Win)
```
📊 Client win worth sharing:

[Client type] came to us with: [Before state / problem]

After [X weeks/months]:
✅ [Result 1]
✅ [Result 2]
✅ [Result 3]

How? [Brief 1-sentence explanation of your method]

Want similar results? Drop a comment or DM me.

#[Industry] #[Results] #[Service]
```

### Value Post (Insight / Teaching)
```
[Counter-intuitive statement about your industry]

Here's what actually works:

1. [Point 1]
2. [Point 2]
3. [Point 3]

The bottom line: [Key takeaway]

Save this if it was useful. Follow me for more [topic] insights.

#[Hashtags]
```

### Announcement Post
```
[News/milestone] 🎉

[What happened + context]

Key numbers:
- [Metric 1]
- [Metric 2]

What this means for [audience]: [Relevance]

[CTA — connect, comment, or DM]

#[Tags]
```

---

## Content Rules (LinkedIn Algorithm)

1. **First line = hook** — must make people stop scrolling
2. **Short paragraphs** — 1-2 lines max (LinkedIn formatting)
3. **Use whitespace** — blank lines between points
4. **One clear CTA** — DM, comment, or follow (not all three)
5. **3-5 hashtags** — mix broad (#AI) and niche (#FreelanceAutomation)
6. **No external links in post** — hurts reach; put in comments instead
7. **Emojis sparingly** — 1-3 max, relevant only
8. **Post 3-5x/week** — consistency beats perfection

---

## Business Goals Alignment

Before drafting, read `vault/Business_Goals.md` to align posts with:
- Current revenue targets
- Active offers / services
- Target audience profile
- Pain points to address this month

---

## Monitoring LinkedIn Engagement

The `linkedin_watcher.py` also creates `Needs_Action` files for:
- Connection requests → review + accept
- Messages from leads → draft reply
- Profile views from target companies → reach out
- Comments on posts → engage back

These appear as `LINKEDIN_<timestamp>.md` in `vault/Needs_Action/`.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Post not publishing | Ensure `linkedin_watcher.py` is running |
| "Start a post" button not found | LinkedIn UI changed — update selector in `linkedin_watcher.py` |
| Session expired | Re-run: `python watchers/linkedin_watcher.py --vault ./vault --setup` |
| Post editor empty | Try `--dry-run` first to test; check Playwright logs |
| Rate limited by LinkedIn | Space posts 2+ hours apart; don't post too frequently |
