"""
PrivPR Comprehensive Test Suite.

Verifies:
1. scanner.py - secret detection, dangerous calls, debug prints, diff parsing.
2. git_handler.py - git repository inspection, branch diffing, uncommitted changes.
3. report.py - markdown generation, severity metrics, detailed findings.
4. reviewer.py - Gemma 4 E4B config, prompt generation, error handling, live Ollama review.
5. End-to-end module integration.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import git

import git_handler
import report
import reviewer
import scanner


def test_scanner():
    """Verify scanner detects secrets, eval/exec, and debug prints."""
    print("\n--- Running Test: Scanner ---")
    vulnerable_code = """
import os
import subprocess

# Secrets
AWS_KEY = "AKIA1234567890ABCDEF"
GITHUB_PAT = "ghp_123456789012345678901234567890123456"
DB_PASS = "SuperSecretPassword123!"

# Dangerous execution
eval("1 + 1")
exec("x = 10")
os.system("ls -la")
subprocess.run("rm -rf /", shell=True)

# Debug prints
print("Debugging user auth token:", DB_PASS)
breakpoint()
"""
    findings = scanner.scan_content(vulnerable_code, filename="vuln.py")
    categories = {f["category"] for f in findings}
    severities = {f["severity"] for f in findings}
    rules_triggered = {f["title"] for f in findings}

    print(f"Total findings detected: {len(findings)}")
    for f in findings:
        print(f"  [{f['severity']}] {f['category']} - {f['title']} (line {f['line']})")

    assert len(findings) >= 8, f"Expected at least 8 findings, got {len(findings)}"
    assert "Security" in categories
    assert "Code Quality" in categories
    assert "CRITICAL" in severities
    assert "HIGH" in severities
    assert "LOW" in severities

    # Verify diff scanning
    diff_text = """
--- a/app.py
+++ b/app.py
@@ -10,3 +10,4 @@ def test():
     x = 1
+    print("testing diff")
+    eval("bad_call()")
"""
    diff_findings = scanner.scan_diff(diff_text, filename="app.py")
    assert len(diff_findings) == 2, f"Expected 2 diff findings, got {len(diff_findings)}"
    assert diff_findings[0]["line"] == 11
    assert diff_findings[1]["line"] == 12
    print("Scanner tests PASSED.")


def test_git_handler():
    """Verify GitHandler reads uncommitted changes and branch diffs safely."""
    print("\n--- Running Test: GitHandler ---")
    temp_dir = tempfile.mkdtemp(prefix="privpr_git_test_")
    try:
        repo = git.Repo.init(temp_dir)
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()

        # Initial commit on default branch (e.g. main/master)
        initial_branch = repo.active_branch.name
        readme = Path(temp_dir) / "README.md"
        readme.write_text("# Test Repo\nInitial content.", encoding="utf-8")
        repo.index.add(["README.md"])
        initial_commit = repo.index.commit("Initial commit")

        # Create branch 'feature'
        feature_branch = repo.create_head("feature")
        feature_branch.checkout()

        # Modify README and add new file in feature branch
        code_file = Path(temp_dir) / "feature.py"
        code_file.write_text("print('feature code')", encoding="utf-8")
        readme.write_text("# Test Repo\nUpdated on feature branch.", encoding="utf-8")
        repo.index.add(["README.md", "feature.py"])
        repo.index.commit("Feature commit")

        # Test branch diff against the initial branch
        handler = git_handler.GitHandler(temp_dir)
        branch_diffs = handler.get_branch_diff(base_branch=initial_branch)
        assert len(branch_diffs) == 2, f"Expected 2 changed files, got {len(branch_diffs)}"
        filenames = {d["filename"] for d in branch_diffs}
        assert "README.md" in filenames
        assert "feature.py" in filenames
        print(f"Branch diff detected files: {filenames}")

        # Add uncommitted file
        uncommitted_file = Path(temp_dir) / "uncommitted.py"
        uncommitted_file.write_text("eval('uncommitted')", encoding="utf-8")
        uncommitted = handler.get_uncommitted_changes()
        uncommitted_names = {u["filename"] for u in uncommitted}
        assert "uncommitted.py" in uncommitted_names
        print(f"Uncommitted changes detected files: {uncommitted_names}")

        print("GitHandler tests PASSED.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_report_generator():
    """Verify ReportGenerator generates well-formed Markdown."""
    print("\n--- Running Test: ReportGenerator ---")
    mock_findings = [
        {
            "filename": "auth.py",
            "line": 42,
            "category": "Security",
            "severity": "CRITICAL",
            "title": "Hardcoded Secret Key",
            "explanation": "A cryptographic key is hardcoded.",
            "suggestion": "Use os.environ.get('SECRET_KEY').",
            "snippet": "SECRET_KEY = 'super_secret'",
        },
        {
            "filename": "utils.py",
            "line": 15,
            "category": "Code Quality",
            "severity": "LOW",
            "title": "Debug print Statement",
            "explanation": "print() left in code.",
            "suggestion": "Remove or replace with logging.",
            "snippet": "print(user)",
        },
    ]

    md = report.generate_report(
        findings=mock_findings,
        title="PrivPR Test Report",
        repo_name="demo-repo",
        base_branch="main",
        target_branch="feature",
    )

    assert "# PrivPR Test Report" in md
    assert "CRITICAL" in md
    assert "Hardcoded Secret Key" in md
    assert "Debug print Statement" in md
    assert "Gemma 4 E4B" in md
    assert "auth.py:42" in md

    # Test saving report
    tmp_report = Path(tempfile.gettempdir()) / "test_privpr_report.md"
    saved = report.save_report(md, tmp_report)
    assert saved.is_file()
    assert saved.read_text(encoding="utf-8") == md
    saved.unlink(missing_ok=True)

    print("ReportGenerator tests PASSED.")


def test_reviewer_parsing_and_config():
    """Verify reviewer configuration and JSON parsing resilience."""
    print("\n--- Running Test: Reviewer Config & Parsing ---")
    rev = reviewer.CodeReviewer(
        model="gemma4:e4b",
        base_url="http://localhost:11434/v1",
    )

    # 1. Invalid model rejection
    try:
        reviewer.CodeReviewer(model="gpt-4")
        assert False, "Should reject non-gemma4:e4b model"
    except ValueError as exc:
        assert "Invalid model" in str(exc)

    # 2. Markdown fence JSON parsing
    raw_response = """
Here are the findings from review:
```json
[
  {
    "filename": "api.py",
    "line": 10,
    "category": "Security",
    "severity": "HIGH",
    "title": "SQL Injection Risk",
    "explanation": "Unsanitized user input formatted into query.",
    "suggestion": "Use parameterized query."
  }
]
```
Please let me know if you need more details.
"""
    parsed = rev._parse_and_validate_response(raw_response, filename="api.py")
    assert len(parsed) == 1
    assert parsed[0]["title"] == "SQL Injection Risk"
    assert parsed[0]["severity"] == "HIGH"
    assert parsed[0]["category"] == "Security"
    assert parsed[0]["line"] == 10

    # 3. Malformed / plain text response resilience
    plain_text = "The code looks mostly okay, but line 5 might have a null pointer risk."
    parsed_fallback = rev._parse_and_validate_response(plain_text, filename="api.py")
    assert len(parsed_fallback) == 1
    assert parsed_fallback[0]["severity"] == "INFO"

    # 4. Clean "no issues" response
    clean_resp = "[]"
    assert rev._parse_and_validate_response(clean_resp, filename="api.py") == []

    print("Reviewer Config & Parsing tests PASSED.")


async def test_live_gemma_reviewer():
    """Test live integration with Gemma 4 E4B via Ollama and Google Antigravity SDK."""
    print("\n--- Running Test: Live Gemma 4 E4B Reviewer via Ollama ---")
    rev = reviewer.CodeReviewer()
    snippet = """
def fetch_user(user_id):
    # Potential SQL injection risk
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)
"""
    rules = "Never allow dynamic string formatting in SQL queries."
    findings = await rev.review_code(
        code=snippet,
        filename="db_ops.py",
        team_rules=rules,
    )

    print(f"Gemma 4 E4B returned {len(findings)} finding(s):")
    for f in findings:
        print(f"  [{f['severity']}] {f['category']} - {f['title']}")
        print(f"    Explanation: {f['explanation']}")
        print(f"    Suggestion:  {f['suggestion']}")

    assert isinstance(findings, list)
    print("Live Gemma 4 E4B Reviewer test PASSED.")


async def main_async():
    test_scanner()
    test_git_handler()
    test_report_generator()
    test_reviewer_parsing_and_config()
    await test_live_gemma_reviewer()
    print("\n" + "=" * 50)
    print(" ALL PRIVPR TESTS PASSED SUCCESSFULLY! ")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    asyncio.run(main_async())
