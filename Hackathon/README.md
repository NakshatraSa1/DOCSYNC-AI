# Csync AI — Smarter Code Reviews. Stronger Code.

Csync AI is a premium, local-first developer product for automated Pull Request and code reviews. Powered exclusively by **Gemma 4 E4B** (`gemma4:e4b`) via **Ollama** and the **Google Antigravity SDK**, coupled with a deterministic static security scanner.

---

## 🔒 Privacy & Architecture Guarantees
- **100% On-Device AI**: All code analysis executes locally via Ollama (`http://localhost:11434/v1`).
- **Zero Cloud Leakage**: No source code, diffs, tokens, or review findings leave your machine.
- **Code Preservation**: Csync AI strictly inspects code and offers recommendations; it never alters source code automatically.
- **Read-Only Git Inspector**: Repository inspection is non-destructive and never executes repository code or hooks.

---

## 🖥️ Web Dashboard & User Experience

Csync AI features a dark interface built with deep ink-black and graphite surfaces, soft silver typography, and a cold cyan accent.

### Guided Review Workflow:
1. **Scope Selection**: Select between **Uncommitted Git Changes**, **Branch Comparison** (e.g. against `main`), or **Direct Paste / File Upload**.
2. **Team Rules & Standards**: Optionally view and edit team standards (stored in `.csync.md` / `.privpr.md`).
3. **Engine Choice**: Run full **Hybrid Intelligence** (Scanner + Gemma 4 E4B) or instant **Static Security Scan**.
4. **Live Telemetry & Analysis**: Track real-time progress across AST parsing, pattern scanning, and local Gemma 4 E4B inference.
5. **Interactive Findings Explorer**: Scan security vulnerabilities with severity badges (Critical, High, Medium, Low, Info), category filters, flagged code blocks, technical explanations, and remediation advice.
6. **Export Report**: Export full Markdown reports (`csync_ai_report.md`).

### Review History Pop-Up Panel:
- **Clean Dashboard**: The Recent Review Activity section is removed from the permanent home screen for an uncluttered experience.
- **Optional Pop-Up Panel**: A dedicated **Review History** option in the sidebar and top navigation opens a pop-up modal panel on demand.
- **Smooth Navigation**: Includes a close (`×`) button and closes when clicking outside the modal backdrop or pressing `Esc`.
- **Real History**: Displays actual past reviews with timestamps, target files, and severity breakdowns. When no reviews exist, displays: *"No reviews yet. Your completed reviews will appear here."*

---

## 🚀 Quick Start

### 1. Prerequisites
Ensure Ollama is running locally with Gemma 4 E4B:
```bash
ollama serve
ollama run gemma4:e4b
```

### 2. Launch Web Interface
Start the Csync AI web dashboard:
```bash
python web_app.py
# or
python app.py --web
```
Open **http://127.0.0.1:8000** in your browser.

### 3. Command Line Usage
Run code reviews directly in terminal or CI/CD pipelines:
```bash
# Review uncommitted changes
python app.py

# Compare current branch against base branch
python app.py --base main

# Review a specific file
python app.py --file path/to/code.py

# Run static scanner only
python app.py --static-only
```

---

## 📁 Project Structure

- **`web_app.py`**: Starlette/Uvicorn server hosting the Csync AI web application and REST API.
- **`templates/index.html`**: Premium dark interface with Review History modal, Gemma status pill, and findings explorer.
- **`history_manager.py`**: Persistent review history storage (`.csync_history.json`).
- **`reviewer.py`**: Local Gemma 4 E4B asynchronous code reviewer using Google Antigravity SDK.
- **`scanner.py`**: Deterministic static security and code quality scanner.
- **`git_handler.py`**: Non-executing, read-only Git repository inspector.
- **`report.py`**: Markdown report generator with executive summary and severity metrics.
- **`.csync.md` / `.privpr.md`**: Team coding standards and review rules.
- **`app.py`**: CLI & web launcher.
- **`test_privpr.py`**: Comprehensive backend test suite.
