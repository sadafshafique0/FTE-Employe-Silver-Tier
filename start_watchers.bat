@echo off
REM AI Employee Silver Tier — Start All Watchers
REM Run this from the project root directory (where Credentials.json lives)

cd /d "%~dp0"
echo.
echo ========================================
echo  AI Employee Silver Tier — Starting...
echo ========================================
echo.

REM Check vault exists
if not exist "vault" (
    echo ERROR: vault\ not found. Run from project root.
    pause & exit /b 1
)

REM ── 1. File System Watcher ──────────────────────────────────────────
echo [1/5] Starting File System Watcher...
start "FS-Watcher" /MIN python watchers\filesystem_watcher.py --vault vault
timeout /t 2 /nobreak >nul

REM ── 2. Gmail Watcher ────────────────────────────────────────────────
if exist "Credentials.json" (
    echo [2/5] Starting Gmail Watcher...
    start "Gmail-Watcher" /MIN python watchers\gmail_watcher.py --vault vault --credentials Credentials.json
) else (
    echo [2/5] SKIPPED Gmail Watcher ^(Credentials.json not found in project root^)
)
timeout /t 2 /nobreak >nul

REM ── 3. WhatsApp Watcher ─────────────────────────────────────────────
if exist "watchers\whatsapp_session" (
    echo [3/5] Starting WhatsApp Watcher...
    start "WhatsApp-Watcher" /MIN python watchers\whatsapp_watcher.py --vault vault
) else (
    echo [3/5] SKIPPED WhatsApp Watcher
    echo        First run: python watchers\whatsapp_watcher.py --vault vault --setup
)
timeout /t 2 /nobreak >nul

REM ── 4. LinkedIn Watcher ─────────────────────────────────────────────
if exist "watchers\linkedin_session" (
    echo [4/5] Starting LinkedIn Watcher...
    start "LinkedIn-Watcher" /MIN python watchers\linkedin_watcher.py --vault vault
) else (
    echo [4/5] SKIPPED LinkedIn Watcher
    echo        First run: python watchers\linkedin_watcher.py --vault vault --setup
)
timeout /t 2 /nobreak >nul

REM ── 5. Orchestrator ─────────────────────────────────────────────────
if exist "Credentials.json" (
    echo [5/5] Starting Orchestrator ^(will send approved emails^)...
    start "Orchestrator" /MIN python watchers\orchestrator.py --vault vault --credentials Credentials.json
) else (
    echo [5/5] Starting Orchestrator ^(dry-run — no Credentials.json^)...
    start "Orchestrator" /MIN python watchers\orchestrator.py --vault vault --dry-run
)

echo.
echo ========================================
echo  All watchers started!
echo.
echo  Gmail:    reads inbox → vault/Needs_Action/
echo  LinkedIn: monitors notifications + publishes approved posts
echo  WhatsApp: monitors messages → vault/Needs_Action/
echo  FS:       monitors vault/Inbox/ drops
echo  Orch:     sends approved emails from vault/Approved/
echo.
echo  Check Task Manager for running python processes.
echo  To stop all: close the minimized windows.
echo ========================================
echo.
pause
