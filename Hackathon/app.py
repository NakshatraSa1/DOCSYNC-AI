"""
Csync AI Main CLI & Web Application.

Local-first AI Pull Request Reviewer powered by Gemma 4 E4B, Ollama,
and the Google Antigravity SDK.
Tagline: Smarter Code Reviews. Stronger Code.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure UTF-8 output on Windows terminals to prevent UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import git_handler
import report
import reviewer
import scanner
from history_manager import history_manager


def load_rules(rules_path: str = ".csync.md") -> str:
    """Load team rules from a markdown file if present."""
    for p in [Path(rules_path), Path(".csync.md"), Path(".privpr.md")]:
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                print(f"[Warning] Could not load rules from {p}: {exc}")
    return ""


def deduplicate_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove exact duplicate findings based on filename, line, and title."""
    seen = set()
    deduped = []
    for item in findings:
        key = (
            item.get("filename"),
            item.get("line"),
            item.get("category"),
            item.get("title"),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


async def run_review(
    repo_path: str = ".",
    base_branch: Optional[str] = None,
    single_file: Optional[str] = None,
    rules_file: str = ".privpr.md",
    output_report: Optional[str] = "report.md",
    static_only: bool = False,
    ai_only: bool = False,
) -> int:
    """
    Execute full review pipeline:
    1. Read git changes or single file.
    2. Run static scanner.
    3. Run local Gemma 4 E4B AI reviewer.
    4. Aggregate and deduplicate findings.
    5. Output Markdown report.
    """
    print("=" * 65)
    print(" Csync AI — Smarter Code Reviews. Stronger Code.")
    print(" Model: Gemma 4 E4B (gemma4:e4b) | Endpoint: http://localhost:11434/v1")
    print(" SDK: Google Antigravity SDK | 100% Local & Private")
    print("=" * 65)

    team_rules = load_rules(rules_file)
    if team_rules:
        print(f"[Csync AI] Loaded team rules from '{rules_file}'.")

    files_to_review: List[Dict[str, Any]] = []

    if single_file:
        file_path = Path(single_file)
        if not file_path.is_file():
            print(f"[Error] Specified file does not exist: {single_file}")
            return 1
        print(f"[PrivPR] Reviewing single file: {single_file}")
        content = file_path.read_text(encoding="utf-8", errors="replace")
        files_to_review.append(
            {
                "filename": single_file,
                "status": "modified",
                "diff": "",
                "content": content,
            }
        )
        repo_name = file_path.parent.name or "local"
        current_branch = None
    else:
        try:
            handler = git_handler.GitHandler(repo_path)
            repo_name = handler.repo_path.name
            current_branch = handler.current_branch

            if base_branch:
                print(f"[PrivPR] Comparing current branch '{current_branch}' against base '{base_branch}'...")
                files_to_review = handler.get_branch_diff(base_branch)
            else:
                print(f"[PrivPR] Inspecting uncommitted changes in '{repo_name}'...")
                files_to_review = handler.get_uncommitted_changes()

        except Exception as exc:
            print(f"[Git Error] {exc}")
            print("[PrivPR] Falling back to scanning files in current directory...")
            # Fallback: scan existing python files in directory
            for root, _, files in os.walk(repo_path):
                if any(ignored in root for ignored in [".git", ".venv", "__pycache__", "build", "dist"]):
                    continue
                for f in files:
                    if f.endswith((".py", ".js", ".ts")):
                        fp = Path(root) / f
                        try:
                            rel = fp.relative_to(repo_path).as_posix()
                            files_to_review.append(
                                {
                                    "filename": rel,
                                    "status": "untracked",
                                    "diff": "",
                                    "content": fp.read_text(encoding="utf-8", errors="replace"),
                                }
                            )
                        except Exception:
                            pass
            repo_name = Path(repo_path).resolve().name
            current_branch = "local"

    if not files_to_review:
        print("[PrivPR] No modified or uncommitted files detected.")
        empty_report = report.generate_report(
            findings=[],
            title="PrivPR Pull Request Review",
            repo_name=repo_name,
            base_branch=base_branch,
            target_branch=current_branch,
        )
        if output_report:
            saved_path = report.save_report(empty_report, output_report)
            print(f"[PrivPR] Clean report written to {saved_path}")
        return 0

    print(f"[PrivPR] Found {len(files_to_review)} file(s) to inspect:")
    for f in files_to_review:
        print(f"  * {f['filename']} ({f['status']})")

    all_findings: List[Dict[str, Any]] = []

    # Step 1: Run Static Security & Code Quality Scanner
    if not ai_only:
        print("\n[Scanner] Running static security & quality checks...")
        for item in files_to_review:
            fn = item["filename"]
            diff = item.get("diff", "")
            content = item.get("content", "")

            # If diff is available, scan the diff to flag added lines
            if diff:
                scan_results = scanner.scan_diff(diff, filename=fn)
            else:
                scan_results = scanner.scan_content(content, filename=fn)

            all_findings.extend(scan_results)

        print(f"[Scanner] Found {len(all_findings)} static finding(s).")

    # Step 2: Run Gemma 4 E4B AI Reviewer
    if not static_only:
        print("\n[AI Reviewer] Connecting to Gemma 4 E4B via Ollama...")
        ai_reviewer = reviewer.CodeReviewer()
        for item in files_to_review:
            fn = item["filename"]
            content = item.get("content", "")
            diff = item.get("diff", "")

            if not content and not diff:
                continue

            print(f"[AI Reviewer] Analyzing {fn}...")
            ai_findings = await ai_reviewer.review_code(
                code=content,
                filename=fn,
                team_rules=team_rules,
                diff=diff,
            )
            print(f"  -> {len(ai_findings)} finding(s) reported by Gemma 4 E4B.")
            all_findings.extend(ai_findings)

    # Step 3: Deduplicate findings
    deduped = deduplicate_findings(all_findings)

    # Step 4: Generate Markdown Report
    print(f"\n[PrivPR] Total unique findings across all checks: {len(deduped)}")
    md_report = report.generate_report(
        findings=deduped,
        title="PrivPR Pull Request Review Report",
        repo_name=repo_name,
        base_branch=base_branch,
        target_branch=current_branch,
    )

    # Save to review history
    engine_label = "Gemma 4 E4B + Scanner"
    if static_only:
        engine_label = "Static Scanner Only"
    elif ai_only:
        engine_label = "Gemma 4 E4B Only"

    history_manager.add_entry(
        target_name=repo_name,
        review_type=f"CLI ({'branch ' + base_branch if base_branch else 'working tree'})",
        findings=deduped,
        markdown_report=md_report,
        files_count=len(files_to_review),
        engine=engine_label,
    )

    if output_report:
        saved_path = report.save_report(md_report, output_report)
        print(f"[Csync AI] Report successfully saved to: {saved_path}")

    # Summary in terminal
    counts = {
        "CRITICAL": sum(1 for f in deduped if f.get("severity") == "CRITICAL"),
        "HIGH": sum(1 for f in deduped if f.get("severity") == "HIGH"),
        "MEDIUM": sum(1 for f in deduped if f.get("severity") == "MEDIUM"),
        "LOW": sum(1 for f in deduped if f.get("severity") == "LOW"),
        "INFO": sum(1 for f in deduped if f.get("severity") == "INFO"),
    }
    print("-" * 45)
    print(" Review Summary:")
    print(f"  [CRITICAL] : {counts['CRITICAL']}")
    print(f"  [HIGH]     : {counts['HIGH']}")
    print(f"  [MEDIUM]   : {counts['MEDIUM']}")
    print(f"  [LOW]      : {counts['LOW']}")
    print(f"  [INFO]     : {counts['INFO']}")
    print("-" * 45)

    if counts["CRITICAL"] > 0 or counts["HIGH"] > 0:
        print("[PrivPR Verdict] FAILED: Fix critical/high security and logic issues before merging.")
        return 1
    elif counts["MEDIUM"] > 0:
        print("[PrivPR Verdict] WARNINGS: Review suggestions before merging.")
        return 0
    else:
        print("[PrivPR Verdict] PASSED: Pull request looks great!")
        return 0


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Csync AI: Local-First AI Pull Request Reviewer using Gemma 4 E4B"
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the Csync AI web dashboard interface",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host for web server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for web server (default: 8000)",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to git repository (default: current directory)",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="Base branch to compare against (e.g., 'main')",
    )
    parser.add_argument(
        "--file",
        default=None,
        help="Review a specific file instead of git repository diff",
    )
    parser.add_argument(
        "--rules",
        default=".csync.md",
        help="Path to team rules markdown file (default: .csync.md)",
    )
    parser.add_argument(
        "--output",
        default="report.md",
        help="Path to output markdown report file (default: report.md)",
    )
    parser.add_argument(
        "--static-only",
        action="store_true",
        help="Run only the static scanner (skips AI model)",
    )
    parser.add_argument(
        "--ai-only",
        action="store_true",
        help="Run only the Gemma 4 E4B AI reviewer (skips static scanner)",
    )

    args = parser.parse_args()

    # Launch web UI if requested
    if args.web:
        import web_app
        web_app.run_server(host=args.host, port=args.port)
        return

    exit_code = asyncio.run(
        run_review(
            repo_path=args.repo,
            base_branch=args.base,
            single_file=args.file,
            rules_file=args.rules,
            output_report=args.output,
            static_only=args.static_only,
            ai_only=args.ai_only,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
