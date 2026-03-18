#!/usr/bin/env python3
"""
email_mcp_server.py — Gmail MCP Server for AI Employee (Silver Tier)

Implements the Model Context Protocol (MCP) over stdio (JSON-RPC 2.0).
Exposes Gmail as callable tools for Claude:

  Tools:
    send_email    — Compose and send an email via Gmail API
    list_emails   — List recent inbox messages with metadata
    get_email     — Fetch full content of a specific email
    trash_email   — Move an email to Gmail Trash
    mark_spam     — Move an email to Gmail Spam folder

Setup (register in .claude/settings.json):
    {
      "mcpServers": {
        "gmail": {
          "command": "python",
          "args": ["watchers/email_mcp_server.py"],
          "env": {
            "GMAIL_CREDENTIALS": "Credentials.json",
            "GMAIL_TOKEN": "watchers/gmail_token.json"
          }
        }
      }
    }

Usage:
    python watchers/email_mcp_server.py         # stdio mode (default, for MCP)
    python watchers/email_mcp_server.py --test  # smoke-test mode

Requirements:
    pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import base64
import json
import logging
import os
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logging.basicConfig(
    filename=str(Path(__file__).parent / "email_mcp_server.log"),
    level=logging.INFO,
    format="%(asctime)s [EmailMCP] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("email_mcp")

# ── MCP Protocol Constants ──────────────────────────────────────────────────
JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "gmail-mcp"
SERVER_VERSION = "1.0.0"

# ── Gmail Auth ───────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

_gmail_service = None


def get_gmail_service():
    global _gmail_service
    if _gmail_service:
        return _gmail_service

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Google API packages not installed. "
            "Run: pip install google-auth google-auth-oauthlib "
            "google-auth-httplib2 google-api-python-client"
        )

    creds_path = Path(os.environ.get("GMAIL_CREDENTIALS", "Credentials.json"))
    # Prefer the send token (gmail.modify + gmail.send), fall back to watcher token
    token_path = Path(os.environ.get("GMAIL_TOKEN", "watchers/gmail_send_token.json"))

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif creds_path.exists():
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        else:
            raise RuntimeError(f"No credentials found at {creds_path}")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    _gmail_service = build("gmail", "v1", credentials=creds)
    return _gmail_service


# ── Tool Implementations ─────────────────────────────────────────────────────

def tool_send_email(to: str, subject: str, body: str,
                    cc: str = "", thread_id: str = "") -> dict:
    """Send an email via Gmail API."""
    service = get_gmail_service()

    if cc:
        msg = MIMEMultipart("alternative")
        msg["cc"] = cc
    else:
        msg = MIMEText(body, "plain")

    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id

    result = service.users().messages().send(userId="me", body=payload).execute()
    logger.info(f"Email sent to {to} | Gmail ID: {result.get('id')}")
    return {
        "status": "sent",
        "message_id": result.get("id"),
        "to": to,
        "subject": subject,
        "timestamp": datetime.now().isoformat(),
    }


def tool_list_emails(max_results: int = 10, query: str = "in:inbox") -> dict:
    """List recent Gmail inbox messages."""
    service = get_gmail_service()
    response = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = response.get("messages", [])
    results = []
    for msg in messages[:max_results]:
        meta = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in meta.get("payload", {}).get("headers", [])}
        results.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "snippet": meta.get("snippet", "")[:120],
        })

    return {"count": len(results), "messages": results}


def tool_get_email(message_id: str) -> dict:
    """Fetch the full content of a Gmail message."""
    service = get_gmail_service()
    msg = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()

    headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = ""
    payload = msg.get("payload", {})

    def extract_body(part):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        for sub in part.get("parts", []):
            result = extract_body(sub)
            if result:
                return result
        return ""

    body = extract_body(payload)
    return {
        "id": message_id,
        "from": headers.get("From", ""),
        "subject": headers.get("Subject", ""),
        "date": headers.get("Date", ""),
        "body": body[:3000],
        "labels": msg.get("labelIds", []),
    }


def tool_trash_email(message_id: str) -> dict:
    """Move an email to Gmail Trash."""
    service = get_gmail_service()
    service.users().messages().trash(userId="me", id=message_id).execute()
    logger.info(f"Trashed Gmail message: {message_id}")
    return {"status": "trashed", "message_id": message_id}


def tool_mark_spam(message_id: str) -> dict:
    """Move an email to Gmail Spam."""
    service = get_gmail_service()
    service.users().messages().modify(
        userId="me", id=message_id,
        body={"addLabelIds": ["SPAM"], "removeLabelIds": ["INBOX"]}
    ).execute()
    logger.info(f"Marked as spam: {message_id}")
    return {"status": "marked_spam", "message_id": message_id}


# ── Tool Registry ─────────────────────────────────────────────────────────────

TOOLS = {
    "send_email": {
        "fn": tool_send_email,
        "description": "Send an email via Gmail API. Requires human approval first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to":        {"type": "string", "description": "Recipient email address"},
                "subject":   {"type": "string", "description": "Email subject line"},
                "body":      {"type": "string", "description": "Plain text email body"},
                "cc":        {"type": "string", "description": "Optional CC addresses"},
                "thread_id": {"type": "string", "description": "Optional Gmail thread ID for replies"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    "list_emails": {
        "fn": tool_list_emails,
        "description": "List recent Gmail messages with metadata (from, subject, date, snippet).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_results": {"type": "integer", "description": "Max emails to return (default 10)", "default": 10},
                "query":       {"type": "string", "description": "Gmail search query (default: 'in:inbox')", "default": "in:inbox"},
            },
        },
    },
    "get_email": {
        "fn": tool_get_email,
        "description": "Fetch full content of a specific Gmail message by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID"},
            },
            "required": ["message_id"],
        },
    },
    "trash_email": {
        "fn": tool_trash_email,
        "description": "Move an email to Gmail Trash (recoverable for 30 days).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID to trash"},
            },
            "required": ["message_id"],
        },
    },
    "mark_spam": {
        "fn": tool_mark_spam,
        "description": "Mark an email as spam and remove it from inbox.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "Gmail message ID to mark as spam"},
            },
            "required": ["message_id"],
        },
    },
}


# ── MCP Protocol Handlers ─────────────────────────────────────────────────────

def handle_initialize(req_id, params):
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": req_id,
        "result": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
    }


def handle_tools_list(req_id, params):
    tools = []
    for name, spec in TOOLS.items():
        tools.append({
            "name": name,
            "description": spec["description"],
            "inputSchema": spec["inputSchema"],
        })
    return {"jsonrpc": JSONRPC_VERSION, "id": req_id, "result": {"tools": tools}}


def handle_tools_call(req_id, params):
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if tool_name not in TOOLS:
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
        }

    try:
        result = TOOLS[tool_name]["fn"](**arguments)
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False,
            },
        }
    except Exception as e:
        logger.error(f"Tool {tool_name} error: {e}")
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            },
        }


HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "notifications/initialized": None,  # No response needed
}


# ── stdio MCP Loop ─────────────────────────────────────────────────────────────

def run_stdio():
    """Main MCP server loop — reads JSON-RPC requests from stdin, writes responses to stdout."""
    logger.info("Gmail MCP server started (stdio mode)")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            continue

        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        logger.info(f"Request: {method} (id={req_id})")

        handler = HANDLERS.get(method)
        if handler is None:
            if req_id is not None:
                response = {
                    "jsonrpc": JSONRPC_VERSION,
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
                print(json.dumps(response), flush=True)
            continue

        response = handler(req_id, params)
        if response is not None:
            print(json.dumps(response), flush=True)


# ── Smoke Test ────────────────────────────────────────────────────────────────

def run_test():
    """Quick smoke test — connect to Gmail and list 3 emails."""
    print("Gmail MCP Server — Smoke Test")
    print("=" * 40)
    try:
        result = tool_list_emails(max_results=3)
        print(f"Connected to Gmail. Found {result['count']} messages:")
        for msg in result["messages"]:
            print(f"  [{msg['id']}] {msg['from'][:30]:30s} — {msg['subject'][:40]}")
        print("\nTools available:")
        for name, spec in TOOLS.items():
            print(f"  {name:15s} — {spec['description'][:60]}")
        print("\nSmoke test PASSED.")
    except Exception as e:
        print(f"Smoke test FAILED: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    else:
        run_stdio()
