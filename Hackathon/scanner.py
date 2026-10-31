"""
Csync AI Static Security & Code Quality Scanner.

Detects hardcoded secrets, passwords, API keys, dangerous eval/exec calls,
and debug print statements in source code and git diffs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class Finding:
    """Represents a single static analysis finding."""

    def __init__(
        self,
        filename: str,
        line: int,
        category: str,
        severity: str,
        title: str,
        explanation: str,
        suggestion: str,
        snippet: str = "",
    ):
        self.filename = filename
        self.line = line
        self.category = category
        self.severity = severity.upper()
        self.title = title
        self.explanation = explanation
        self.suggestion = suggestion
        self.snippet = snippet

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to standard dictionary representation."""
        return {
            "filename": self.filename,
            "line": self.line,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "explanation": self.explanation,
            "suggestion": self.suggestion,
            "snippet": self.snippet,
        }


# Placeholders to ignore to reduce false positives
PLACEHOLDERS = {
    "your_api_key",
    "your_key_here",
    "your_secret_key",
    "your_password",
    "change_me",
    "placeholder",
    "dummy_value",
    "sample_token",
    "replace_me",
    "xxx",
    "todo",
}


class StaticScanner:
    """Deterministic static code and secret scanner."""

    # Pre-compiled regex patterns for performance and reliability
    PATTERNS: List[Dict[str, Any]] = [
        # 1. AWS Access Key
        {
            "id": "SEC-AWS-KEY",
            "regex": re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
            "category": "Security",
            "severity": "CRITICAL",
            "title": "Hardcoded AWS Access Key ID Detected",
            "explanation": "An AWS Access Key ID was detected in plaintext. Exposed cloud credentials can allow unauthorized access to infrastructure.",
            "suggestion": "Remove key immediately, rotate it in AWS IAM, and load credentials from environment variables or AWS Secrets Manager.",
        },
        # 2. GitHub Token
        {
            "id": "SEC-GH-TOKEN",
            "regex": re.compile(r"\b(gh[pousr]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{22,})\b"),
            "category": "Security",
            "severity": "CRITICAL",
            "title": "Hardcoded GitHub Personal Access Token Detected",
            "explanation": "A GitHub token was found hardcoded in source code. This token grants API access to repositories and organizations.",
            "suggestion": "Revoke the token on GitHub immediately and use GitHub Actions secrets or environment variables.",
        },
        # 3. Slack Token
        {
            "id": "SEC-SLACK-TOKEN",
            "regex": re.compile(r"\b(xox[baprs]-[0-9a-zA-Z]{10,48})\b"),
            "category": "Security",
            "severity": "CRITICAL",
            "title": "Hardcoded Slack Token Detected",
            "explanation": "A Slack API bot or user token was identified. Anyone with this token can inspect workspace messages or perform bot actions.",
            "suggestion": "Revoke and regenerate the token in Slack App Settings, storing it in a secret manager.",
        },
        # 4. Private Key Block
        {
            "id": "SEC-PRIV-KEY",
            "regex": re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP)?\s*PRIVATE KEY-----"),
            "category": "Security",
            "severity": "CRITICAL",
            "title": "Unencrypted Private Key Detected",
            "explanation": "A cryptographic private key block was found embedded in source code.",
            "suggestion": "Remove private keys from source code. Store keys in secure key management vaults (e.g. HashiCorp Vault, AWS KMS) or mounted secret files.",
        },
        # 5. Generic API Key / Secret assignments
        {
            "id": "SEC-GEN-KEY",
            "regex": re.compile(
                r"""(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key|client[_-]?secret)\s*[:=]\s*["']([A-Za-z0-9_\-\.\/+=]{12,})["']"""
            ),
            "category": "Security",
            "severity": "CRITICAL",
            "title": "Hardcoded API Key / Secret Detected",
            "explanation": "An API key or secret token appears to be hardcoded in a variable assignment.",
            "suggestion": "Store secrets in environment variables (e.g., `os.environ.get('API_KEY')`) and load them using a `.env` file that is ignored by git.",
        },
        # 6. Hardcoded Password
        {
            "id": "SEC-PASSWORD",
            "regex": re.compile(
                r"""(?i)(?:password|passwd|pwd|db_pass)\s*[:=]\s*["']([^"'\s]{5,})["']"""
            ),
            "category": "Security",
            "severity": "HIGH",
            "title": "Hardcoded Password Detected",
            "explanation": "A password string is hardcoded in source code.",
            "suggestion": "Retrieve passwords at runtime from secure environment variables or a configuration vault.",
        },
        # 7. JWT Token
        {
            "id": "SEC-JWT",
            "regex": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+\b"),
            "category": "Security",
            "severity": "HIGH",
            "title": "Hardcoded JSON Web Token (JWT) Detected",
            "explanation": "A static JWT token was detected in code. Hardcoded session/auth tokens expire or can be used for unauthorized access.",
            "suggestion": "Authenticate dynamically via an identity provider or use configuration secrets.",
        },
        # 8. Dangerous eval() call
        {
            "id": "SEC-EVAL",
            "regex": re.compile(r"(?<![a-zA-Z0-9_])eval\s*\("),
            "category": "Security",
            "severity": "CRITICAL",
            "title": "Dangerous eval() Call Detected",
            "explanation": "The `eval()` function dynamically evaluates arbitrary strings as Python code, creating severe Arbitrary Code Execution vulnerabilities.",
            "suggestion": "Avoid `eval()`. Use `ast.literal_eval()` for parsing safe Python literals, or use `json.loads()` for structured data.",
        },
        # 9. Dangerous exec() call
        {
            "id": "SEC-EXEC",
            "regex": re.compile(r"(?<![a-zA-Z0-9_])exec\s*\("),
            "category": "Security",
            "severity": "CRITICAL",
            "title": "Dangerous exec() Call Detected",
            "explanation": "The `exec()` function executes arbitrary code blocks in the current execution context, exposing the system to Remote Code Execution.",
            "suggestion": "Refactor logic to use functions, classes, or a safe dispatch table instead of dynamic execution.",
        },
        # 10. Dangerous shell=True execution
        {
            "id": "SEC-SUBPROCESS-SHELL",
            "regex": re.compile(
                r"subprocess\.(?:call|Popen|run|check_call|check_output)\s*\([^)]*shell\s*=\s*True"
            ),
            "category": "Security",
            "severity": "HIGH",
            "title": "Dangerous subprocess with shell=True",
            "explanation": "Executing subprocess commands through a system shell (`shell=True`) opens the application to Command Injection attacks.",
            "suggestion": "Pass arguments as a list with `shell=False` (e.g. `subprocess.run(['command', 'arg1'], shell=False)`).",
        },
        # 11. os.system()
        {
            "id": "SEC-OS-SYSTEM",
            "regex": re.compile(r"\bos\.system\s*\("),
            "category": "Security",
            "severity": "HIGH",
            "title": "Unsafe os.system() Call",
            "explanation": "`os.system()` passes strings directly to the shell and does not safely escape arguments.",
            "suggestion": "Use `subprocess.run()` with argument lists and `shell=False`.",
        },
        # 12. Unsafe YAML load
        {
            "id": "SEC-YAML-LOAD",
            "regex": re.compile(r"yaml\.load\s*\([^,\)]*(?:,\s*Loader\s*=\s*(?:yaml\.)?(?:UnsafeLoader|Loader))?\)"),
            "category": "Security",
            "severity": "HIGH",
            "title": "Unsafe yaml.load() Call",
            "explanation": "Calling `yaml.load()` without `SafeLoader` can instantiate arbitrary Python objects and execute harmful code.",
            "suggestion": "Use `yaml.safe_load()` instead.",
        },
        # 13. Unsafe pickle load
        {
            "id": "SEC-PICKLE-LOAD",
            "regex": re.compile(r"pickle\.loads?\s*\("),
            "category": "Security",
            "severity": "HIGH",
            "title": "Unsafe Pickle Deserialization",
            "explanation": "The `pickle` module is not secure against erroneous or maliciously constructed data.",
            "suggestion": "Use safe serialization formats such as JSON (`json.loads`) or Protocol Buffers.",
        },
        # 14. Debug print statements (Python)
        {
            "id": "QLT-PRINT",
            "regex": re.compile(r"(?<![a-zA-Z0-9_])print\s*\("),
            "category": "Code Quality",
            "severity": "LOW",
            "title": "Debug print() Statement Found",
            "explanation": "Direct `print()` calls pollute production stdout, do not support log levels, and can leak runtime data.",
            "suggestion": "Replace `print()` with configured logging (e.g., `logger.debug()` or `logger.info()`), or remove prior to merging.",
        },
        # 15. Debugger breakpoints
        {
            "id": "QLT-BREAKPOINT",
            "regex": re.compile(r"\b(?:breakpoint\s*\(|pdb\.set_trace\s*\(|import\s+pdb|import\s+ipdb)\b"),
            "category": "Code Quality",
            "severity": "HIGH",
            "title": "Leftover Debugger Breakpoint",
            "explanation": "Active debugger breakpoints (`breakpoint()`, `pdb`) will freeze program execution if reached in production.",
            "suggestion": "Remove all debugger breakpoints and debug imports before committing.",
        },
        # 16. Console log (JS/TS)
        {
            "id": "QLT-CONSOLE-LOG",
            "regex": re.compile(r"\bconsole\.(?:log|debug|info|warn|error)\s*\("),
            "category": "Code Quality",
            "severity": "LOW",
            "title": "Debug console.log Statement Found",
            "explanation": "Leftover `console.log` statements clutter browser/node output and may leak sensitive user objects.",
            "suggestion": "Remove `console.log` or use a dedicated logging framework.",
        },
    ]

    @classmethod
    def scan_content(cls, content: str, filename: str = "unknown") -> List[Dict[str, Any]]:
        """
        Scan raw file content line by line for secrets, dangerous calls, and debug prints.

        Args:
            content: Source code text.
            filename: Path or name of the file being scanned.

        Returns:
            List of finding dictionaries.
        """
        findings: List[Dict[str, Any]] = []
        if not content:
            return findings

        lines = content.splitlines()
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                continue

            for rule in cls.PATTERNS:
                match = rule["regex"].search(line)
                if not match:
                    continue

                # Check if secret value is an obvious placeholder
                if match.groups():
                    matched_val = match.group(1).lower()
                    if matched_val in PLACEHOLDERS or any(p in matched_val for p in ["example", "placeholder"]):
                        continue

                # Ignore pure comment lines for print statements
                if rule["category"] == "Code Quality" and (stripped.startswith("#") or stripped.startswith("//")):
                    continue

                finding = Finding(
                    filename=filename,
                    line=idx,
                    category=rule["category"],
                    severity=rule["severity"],
                    title=rule["title"],
                    explanation=rule["explanation"],
                    suggestion=rule["suggestion"],
                    snippet=stripped,
                )
                findings.append(finding.to_dict())

        return findings

    @classmethod
    def scan_file(cls, file_path: str | Path) -> List[Dict[str, Any]]:
        """
        Scan a local file on disk.

        Args:
            file_path: Absolute or relative path to the file.

        Returns:
            List of finding dictionaries.
        """
        path = Path(file_path)
        if not path.is_file():
            return []

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            return cls.scan_content(content, filename=str(path.as_posix()))
        except Exception as exc:
            return [
                Finding(
                    filename=str(path.as_posix()),
                    line=1,
                    category="System",
                    severity="LOW",
                    title="Failed to Read File",
                    explanation=f"Could not read file for static scan: {exc}",
                    suggestion="Ensure file permissions allow reading.",
                ).to_dict()
            ]

    @classmethod
    def scan_diff(cls, diff_content: str, filename: str = "unknown") -> List[Dict[str, Any]]:
        """
        Scan a unified git diff, only evaluating newly added lines (`+`).
        Accurately calculates new file line numbers from git hunk headers.

        Args:
            diff_content: Git unified diff text.
            filename: Filename being inspected.

        Returns:
            List of finding dictionaries tied to added lines.
        """
        findings: List[Dict[str, Any]] = []
        if not diff_content:
            return findings

        current_new_line = 0
        hunk_header_regex = re.compile(r"^@@\s+-\d+(?:,\d+)?\s+\+(\d+)(?:,(\d+))?\s+@@")

        for line in diff_content.splitlines():
            # Check for hunk header @@ -a,b +c,d @@
            hunk_match = hunk_header_regex.match(line)
            if hunk_match:
                current_new_line = int(hunk_match.group(1))
                continue

            # Header lines in diff (--- a/... or +++ b/...)
            if line.startswith("---") or line.startswith("+++"):
                continue

            # Added line
            if line.startswith("+"):
                actual_line = line[1:]  # remove leading '+'
                stripped = actual_line.strip()

                if stripped:
                    for rule in cls.PATTERNS:
                        match = rule["regex"].search(actual_line)
                        if not match:
                            continue

                        # Check for placeholder exclusions
                        if match.groups():
                            matched_val = match.group(1).lower()
                            if matched_val in PLACEHOLDERS or any(p in matched_val for p in ["example", "placeholder"]):
                                continue

                        if rule["category"] == "Code Quality" and (stripped.startswith("#") or stripped.startswith("//")):
                            continue

                        finding = Finding(
                            filename=filename,
                            line=current_new_line,
                            category=rule["category"],
                            severity=rule["severity"],
                            title=rule["title"],
                            explanation=rule["explanation"],
                            suggestion=rule["suggestion"],
                            snippet=stripped,
                        )
                        findings.append(finding.to_dict())

                current_new_line += 1
            elif line.startswith("-"):
                # Deleted line does not increment new file line counter
                continue
            else:
                # Context line (unchanged)
                current_new_line += 1

        return findings


# Direct module helper functions
def scan_content(content: str, filename: str = "unknown") -> List[Dict[str, Any]]:
    """Scan string content for security risks and code quality smells."""
    return StaticScanner.scan_content(content, filename)


def scan_file(file_path: str | Path) -> List[Dict[str, Any]]:
    """Scan a single file on disk."""
    return StaticScanner.scan_file(file_path)


def scan_diff(diff_content: str, filename: str = "unknown") -> List[Dict[str, Any]]:
    """Scan a unified git diff for newly introduced issues."""
    return StaticScanner.scan_diff(diff_content, filename)
