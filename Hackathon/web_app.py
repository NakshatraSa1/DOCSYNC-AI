"""
Csync AI Web Application Server.

Local-first web interface for Csync AI powered by Starlette, Uvicorn,
Gemma 4 E4B via Ollama, and the Google Antigravity SDK.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

import git_handler
import report
import reviewer
import scanner
from history_manager import history_manager

OLLAMA_ENDPOINT = "http://localhost:11434/v1"
MODEL_NAME = "gemma4:e4b"
RULES_FILE = Path(".csync.md")
if not RULES_FILE.is_file():
    RULES_FILE = Path(".privpr.md")


async def get_index(request: Request) -> HTMLResponse:
    """Serve the Csync AI web dashboard interface."""
    template_path = Path("templates") / "index.html"
    if template_path.is_file():
        content = template_path.read_text(encoding="utf-8")
        return HTMLResponse(content)
    return HTMLResponse("<h1>Csync AI Dashboard Template Not Found</h1>", status_code=500)


async def api_status(request: Request) -> JSONResponse:
    """
    Check live connection status to local Ollama and Gemma 4 E4B.
    """
    start_time = time.time()
    ollama_online = False
    model_loaded = False
    details = ""

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_ENDPOINT}/models")
            latency_ms = round((time.time() - start_time) * 1000)
            if resp.status_code == 200:
                ollama_online = True
                data = resp.json()
                models = [m.get("id") or m.get("name") for m in data.get("data", [])]
                # Check for gemma4:e4b
                model_loaded = any("gemma4" in str(m) for m in models)
                details = f"Ollama online ({latency_ms}ms). Models: {', '.join(str(m) for m in models[:3])}"
            else:
                details = f"Ollama returned HTTP {resp.status_code}"
    except Exception as exc:
        details = f"Cannot reach Ollama at {OLLAMA_ENDPOINT}: {exc}"

    return JSONResponse(
        {
            "ollama_online": ollama_online,
            "model_loaded": model_loaded,
            "model_name": MODEL_NAME,
            "endpoint": OLLAMA_ENDPOINT,
            "details": details,
        }
    )


async def api_git_info(request: Request) -> JSONResponse:
    """
    Retrieve git repository status, branch name, uncommitted changes,
    and branch list for the specified repository path (defaults to current dir).
    """
    repo_param = request.query_params.get("repo_path", ".").strip() or "."
    target_path = Path(repo_param).resolve()

    try:
        handler = git_handler.GitHandler(target_path)
        current_branch = handler.current_branch
        branches = [b.name for b in handler.repo.branches]
        uncommitted = handler.get_uncommitted_changes()
        return JSONResponse(
            {
                "is_repo": True,
                "repo_path": str(target_path),
                "repo_name": target_path.name or str(target_path),
                "current_branch": current_branch,
                "branches": branches,
                "uncommitted_files": [
                    {
                        "filename": u["filename"],
                        "status": u["status"],
                        "lines_changed": len(u.get("diff", "").splitlines()),
                    }
                    for u in uncommitted
                ],
                "uncommitted_count": len(uncommitted),
            }
        )
    except Exception as exc:
        return JSONResponse(
            {
                "is_repo": False,
                "repo_path": str(target_path),
                "repo_name": target_path.name or str(target_path),
                "current_branch": "none",
                "branches": [],
                "uncommitted_files": [],
                "uncommitted_count": 0,
                "error": str(exc),
            }
        )


async def api_git_init(request: Request) -> JSONResponse:
    """
    Initialize a new Git repository in the specified directory.
    """
    try:
        import git
        body = await request.json()
        repo_param = body.get("repo_path", ".").strip() or "."
        target_path = Path(repo_param).resolve()
        target_path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(target_path, initial_branch="main")
        return JSONResponse({
            "success": True,
            "repo_path": str(target_path),
            "message": f"Initialized empty Git repository in {target_path}",
        })
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)


async def api_rules_get(request: Request) -> JSONResponse:
    """Read current team rules markdown file."""
    content = ""
    for p in [Path(".csync.md"), Path(".privpr.md")]:
        if p.is_file():
            content = p.read_text(encoding="utf-8", errors="replace")
            break
    return JSONResponse({"rules": content})


async def api_rules_save(request: Request) -> JSONResponse:
    """Update team rules markdown file."""
    try:
        body = await request.json()
        new_rules = body.get("rules", "")
        Path(".csync.md").write_text(new_rules, encoding="utf-8")
        Path(".privpr.md").write_text(new_rules, encoding="utf-8")
        return JSONResponse({"success": True})
    except Exception as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)


async def api_history_list(request: Request) -> JSONResponse:
    """
    Retrieve real completed reviews history.
    Never returns fake data.
    """
    records = history_manager.get_all(limit=50)
    # Return summary list without full heavy markdown report to keep payload light
    summaries = []
    for r in records:
        summaries.append(
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "target_name": r["target_name"],
                "review_type": r["review_type"],
                "files_count": r["files_count"],
                "findings_count": r["findings_count"],
                "counts": r["counts"],
                "status": r["status"],
                "engine": r["engine"],
            }
        )
    return JSONResponse({"history": summaries})


async def api_history_item(request: Request) -> JSONResponse:
    """Retrieve full details of a specific past review session."""
    review_id = request.path_params.get("id", "")
    item = history_manager.get_by_id(review_id)
    if item:
        return JSONResponse(item)
    return JSONResponse({"error": "Review record not found"}, status_code=404)


async def api_history_clear(request: Request) -> JSONResponse:
    """Clear all past review history entries."""
    history_manager.clear()
    return JSONResponse({"success": True})


async def api_review(request: Request) -> JSONResponse:
    """
    Execute genuine code review pipeline:
    - Mode: 'uncommitted' | 'branch' | 'custom'
    - Options: static_only, ai_only
    - Connects to Scanner and local Gemma 4 E4B via Ollama.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    scope = body.get("scope", "uncommitted")  # 'uncommitted' | 'branch' | 'custom'
    repo_param = body.get("repo_path", ".").strip() or "."
    target_repo_path = Path(repo_param).resolve()
    base_branch = body.get("base_branch")
    custom_code = body.get("custom_code", "")
    custom_filename = body.get("custom_filename", "snippet.py")
    static_only = bool(body.get("static_only", False))
    ai_only = bool(body.get("ai_only", False))

    # Read rules
    rules_text = ""
    for p in [Path(".csync.md"), Path(".privpr.md")]:
        if p.is_file():
            rules_text = p.read_text(encoding="utf-8", errors="replace")
            break

    files_to_review: List[Dict[str, Any]] = []
    target_name = target_repo_path.name or "Working Tree"
    review_type = "Uncommitted Changes"

    if scope == "custom":
        if not custom_code.strip():
            return JSONResponse({"error": "Please provide code to review"}, status_code=400)
        target_name = custom_filename
        review_type = "Snippet / File Upload"
        files_to_review.append(
            {
                "filename": custom_filename,
                "status": "modified",
                "diff": "",
                "content": custom_code,
            }
        )
    elif scope == "branch":
        if not base_branch:
            base_branch = "main"
        target_name = f"{target_repo_path.name} (vs {base_branch})"
        review_type = f"Branch ({base_branch})"
        try:
            handler = git_handler.GitHandler(target_repo_path)
            files_to_review = handler.get_branch_diff(base_branch)
        except Exception as exc:
            return JSONResponse(
                {"error": f"Git branch diff failed: {exc}"}, status_code=400
            )
    else:  # 'uncommitted'
        review_type = "Uncommitted Changes"
        try:
            handler = git_handler.GitHandler(target_repo_path)
            target_name = f"{target_repo_path.name} (uncommitted)"
            files_to_review = handler.get_uncommitted_changes()
        except Exception as exc:
            return JSONResponse(
                {
                    "error": (
                        f"Could not read git repository at '{target_repo_path}': {exc}. "
                        "Ensure the path is a valid Git repository, or click 'Initialize Git'."
                    )
                },
                status_code=400,
            )

    if not files_to_review:
        # Generate clean report
        md_empty = report.generate_report(
            findings=[],
            title="Csync AI Pull Request Review Report",
            repo_name=target_name,
            base_branch=base_branch if scope == "branch" else None,
        )
        entry = history_manager.add_entry(
            target_name=target_name,
            review_type=review_type,
            findings=[],
            markdown_report=md_empty,
            files_count=0,
            engine="Gemma 4 E4B + Scanner",
        )
        return JSONResponse(
            {
                "id": entry["id"],
                "target_name": target_name,
                "review_type": review_type,
                "files_count": 0,
                "findings": [],
                "counts": entry["counts"],
                "status": "PASSED",
                "markdown_report": md_empty,
            }
        )

    all_findings: List[Dict[str, Any]] = []

    # 1. Run deterministic static scanner
    if not ai_only:
        for f in files_to_review:
            fn = f["filename"]
            diff = f.get("diff", "")
            content = f.get("content", "")
            if diff:
                scan_res = scanner.scan_diff(diff, filename=fn)
            else:
                scan_res = scanner.scan_content(content, filename=fn)
            all_findings.extend(scan_res)

    # 2. Run Gemma 4 E4B local AI reviewer
    if not static_only:
        try:
            ai_reviewer = reviewer.CodeReviewer()
            for f in files_to_review:
                fn = f["filename"]
                content = f.get("content", "")
                diff = f.get("diff", "")
                if not content and not diff:
                    continue
                ai_res = await ai_reviewer.review_code(
                    code=content,
                    filename=fn,
                    team_rules=rules_text,
                    diff=diff,
                )
                all_findings.extend(ai_res)
        except Exception as exc:
            all_findings.append(
                {
                    "filename": "reviewer.py",
                    "line": 1,
                    "category": "System Error",
                    "severity": "CRITICAL",
                    "title": "Gemma 4 E4B Review Engine Failure",
                    "explanation": f"Failed while processing code with local Gemma 4 E4B: {exc}",
                    "suggestion": "Verify local Ollama service is active at http://localhost:11434/v1.",
                    "snippet": "",
                }
            )

    # Deduplicate findings
    seen = set()
    deduped = []
    for item in all_findings:
        key = (
            item.get("filename"),
            item.get("line"),
            item.get("category"),
            item.get("title"),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    # Generate Markdown Report
    md_report = report.generate_report(
        findings=deduped,
        title="Csync AI Pull Request Review Report",
        repo_name=target_name,
        base_branch=base_branch if scope == "branch" else None,
    )

    # Persist in real history
    engine_label = "Gemma 4 E4B + Scanner"
    if static_only:
        engine_label = "Static Scanner Only"
    elif ai_only:
        engine_label = "Gemma 4 E4B Only"

    entry = history_manager.add_entry(
        target_name=target_name,
        review_type=review_type,
        findings=deduped,
        markdown_report=md_report,
        files_count=len(files_to_review),
        engine=engine_label,
    )

    return JSONResponse(
        {
            "id": entry["id"],
            "target_name": target_name,
            "review_type": review_type,
            "files_count": len(files_to_review),
            "findings": deduped,
            "counts": entry["counts"],
            "status": entry["status"],
            "markdown_report": md_report,
        }
    )


async def api_export_report(request: Request) -> Response:
    """Download the markdown review report."""
    try:
        body = await request.json()
        md_text = body.get("markdown", "")
    except Exception:
        md_text = "# Csync AI Review Report\n\nNo content."

    return PlainTextResponse(
        content=md_text,
        media_type="text/markdown",
        headers={"Content-Disposition": 'attachment; filename="csync_ai_report.md"'},
    )


# Define routes
routes = [
    Route("/", get_index, methods=["GET"]),
    Route("/api/status", api_status, methods=["GET"]),
    Route("/api/git-info", api_git_info, methods=["GET"]),
    Route("/api/git-init", api_git_init, methods=["POST"]),
    Route("/api/rules", api_rules_get, methods=["GET"]),
    Route("/api/rules", api_rules_save, methods=["POST"]),
    Route("/api/history", api_history_list, methods=["GET"]),
    Route("/api/history/{id}", api_history_item, methods=["GET"]),
    Route("/api/history", api_history_clear, methods=["DELETE"]),
    Route("/api/review", api_review, methods=["POST"]),
    Route("/api/export", api_export_report, methods=["POST"]),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(debug=False, routes=routes, middleware=middleware)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the Csync AI web application using Uvicorn."""
    import uvicorn

    print("=" * 65)
    print(" Csync AI — Smarter Code Reviews. Stronger Code.")
    print(" Model: Gemma 4 E4B (gemma4:e4b) | Endpoint: http://localhost:11434/v1")
    print(" 100% Local-First & Private AI Code Reviewer")
    print(f" Web Interface: http://{host}:{port}")
    print("=" * 65)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run_server()
