"""
Csync AI Pull Request Markdown Report Generator.

Transforms findings from the Static Scanner and Gemma 4 E4B AI Reviewer
into clear, actionable GitHub-flavored Markdown reports.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

SEVERITY_BADGES = {
    "CRITICAL": "[🔴 CRITICAL]",
    "HIGH": "[🟠 HIGH]",
    "MEDIUM": "[🟡 MEDIUM]",
    "LOW": "[🔵 LOW]",
    "INFO": "[⚪ INFO]",
}


class ReportGenerator:
    """Generates structured Markdown reports from pull request review findings."""

    def __init__(
        self,
        findings: List[Dict[str, Any]],
        title: str = "Csync AI Pull Request Review Report",
        repo_name: str = "",
        base_branch: Optional[str] = None,
        target_branch: Optional[str] = None,
    ):
        self.findings = findings
        self.title = title
        self.repo_name = repo_name
        self.base_branch = base_branch
        self.target_branch = target_branch

    def generate(self) -> str:
        """Construct the full Markdown report."""
        lines: List[str] = []

        # 1. Header
        lines.append(f"# {self.title}\n")
        lines.append(
            "> **Csync AI** — *Smarter Code Reviews. Stronger Code.*\n"
            "> Powered by **Gemma 4 E4B** (`gemma4:e4b`) via Ollama. 100% On-Device & Private.\n"
        )

        # PR Metadata
        metadata_items = [
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        if self.repo_name:
            metadata_items.append(f"**Repository**: `{self.repo_name}`")
        if self.base_branch and self.target_branch:
            metadata_items.append(f"**Comparing**: `{self.target_branch}` -> `{self.base_branch}`")
        elif self.base_branch:
            metadata_items.append(f"**Base Branch**: `{self.base_branch}`")
        else:
            metadata_items.append("**Scope**: Uncommitted changes & working tree")

        lines.append(" | ".join(metadata_items) + "\n")
        lines.append("---\n")

        # 2. Executive Summary
        lines.append(self._render_summary())

        # 3. Quick Reference Table
        if self.findings:
            lines.append(self._render_quick_table())

        # 4. Detailed Findings
        lines.append(self._render_detailed_findings())

        # 5. Policy & Security Assurance Footer
        lines.append(self._render_footer())

        return "\n".join(lines)

    def _render_summary(self) -> str:
        """Render the status badge and findings metric breakdown."""
        counts = Counter(f.get("severity", "INFO").upper() for f in self.findings)
        cat_counts = Counter(f.get("category", "General") for f in self.findings)
        total = len(self.findings)

        # Determine overall verdict
        if counts["CRITICAL"] > 0:
            status = "🔴 **ACTION REQUIRED: CRITICAL ISSUES DETECTED**"
            status_desc = "Severe vulnerabilities or high-risk flaws were identified. Resolve before merging."
        elif counts["HIGH"] > 0:
            status = "🟠 **CHANGES REQUESTED**"
            status_desc = "High-priority issues were detected that require remediation prior to merge."
        elif counts["MEDIUM"] > 0 or counts["LOW"] > 0:
            status = "🟡 **APPROVED WITH SUGGESTIONS**"
            status_desc = "Minor edge cases, code quality smells, or debug statements were noted."
        else:
            status = "🟢 **PASSED: CLEAN PULL REQUEST**"
            status_desc = "No security vulnerabilities, runtime risks, or logic flaws detected."

        md = [
            "## 📊 Executive Summary\n",
            f"**Review Verdict**: {status}  \n",
            f"*{status_desc}*\n",
            "### Findings by Severity",
            "| Severity | Count | Status |",
            "|---|---|---|",
            f"| 🔴 **CRITICAL** | {counts['CRITICAL']} | {'⚠️ Must resolve' if counts['CRITICAL'] else '✅ Clean'} |",
            f"| 🟠 **HIGH** | {counts['HIGH']} | {'⚠️ Action required' if counts['HIGH'] else '✅ Clean'} |",
            f"| 🟡 **MEDIUM** | {counts['MEDIUM']} | {'⚠️ Recommended fix' if counts['MEDIUM'] else '✅ Clean'} |",
            f"| 🔵 **LOW** | {counts['LOW']} | {'ℹ️ Clean up' if counts['LOW'] else '✅ Clean'} |",
            f"| ⚪ **INFO** | {counts['INFO']} | Advisory |",
            f"| **TOTAL** | **{total}** | |",
            "",
        ]

        if cat_counts:
            md.append("### Findings by Category")
            cat_table = ["| Category | Count |", "|---|---|"]
            for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
                cat_table.append(f"| **{cat}** | {cnt} |")
            md.extend(cat_table)
            md.append("")

        return "\n".join(md)

    def _render_quick_table(self) -> str:
        """Render a concise overview table of findings."""
        md = [
            "## 📋 Quick Findings Index\n",
            "| # | Severity | Category | File:Line | Issue Summary |",
            "|---|---|---|---|---|",
        ]

        # Sort findings by severity order
        sorted_findings = sorted(
            self.findings,
            key=lambda x: (
                SEVERITY_ORDER.index(x.get("severity", "INFO").upper())
                if x.get("severity", "INFO").upper() in SEVERITY_ORDER
                else 99
            ),
        )

        for idx, item in enumerate(sorted_findings, start=1):
            sev = item.get("severity", "INFO").upper()
            badge = SEVERITY_BADGES.get(sev, sev)
            cat = item.get("category", "General")
            fn = item.get("filename", "unknown")
            line = item.get("line")
            loc = f"`{fn}:{line}`" if line else f"`{fn}`"
            title = item.get("title", "Issue").replace("|", "\\|")
            md.append(f"| {idx} | {badge} | {cat} | {loc} | {title} |")

        md.append("")
        return "\n".join(md)

    def _render_detailed_findings(self) -> str:
        """Render full details for each finding."""
        if not self.findings:
            return "## 🔍 Detailed Findings\n\n🎉 No issues detected! All checks passed successfully.\n"

        md = ["## 🔍 Detailed Findings\n"]

        # Sort by severity
        sorted_findings = sorted(
            self.findings,
            key=lambda x: (
                SEVERITY_ORDER.index(x.get("severity", "INFO").upper())
                if x.get("severity", "INFO").upper() in SEVERITY_ORDER
                else 99
            ),
        )

        for idx, item in enumerate(sorted_findings, start=1):
            sev = item.get("severity", "INFO").upper()
            badge = SEVERITY_BADGES.get(sev, sev)
            cat = item.get("category", "General")
            fn = item.get("filename", "unknown")
            line = item.get("line")
            title = item.get("title", "Finding")
            explanation = item.get("explanation", "No explanation provided.")
            suggestion = item.get("suggestion", "No suggestion provided.")
            snippet = item.get("snippet", "")

            loc_str = f"`{fn}:{line}`" if line else f"`{fn}`"

            md.append(f"### {idx}. {badge} {title}\n")
            md.append(f"- **Location**: {loc_str}")
            md.append(f"- **Category**: `{cat}`")
            md.append(f"- **Severity**: `{sev}`\n")

            if snippet:
                md.append("**Flagged Code**:")
                md.append("```python")
                md.append(snippet)
                md.append("```\n")

            md.append(f"**Explanation**:\n{explanation}\n")
            md.append(f"**Suggested Remediation**:\n{suggestion}\n")
            md.append("---\n")

        return "\n".join(md)

    def _render_footer(self) -> str:
        """Render footer explaining local execution and safety guarantees."""
        return (
            "## 🛡️ Csync AI Privacy & Security Guarantee\n\n"
            "- **Product**: Csync AI — *Smarter Code Reviews. Stronger Code.*\n"
            "- **Model**: Gemma 4 E4B (`gemma4:e4b`) executed locally on Ollama (`http://localhost:11434/v1`).\n"
            "- **SDK**: Google Antigravity SDK (`LocalOpenAIAgentConfig`).\n"
            "- **Privacy**: Local-first architecture — zero source code, diffs, or prompts were sent to any external cloud API.\n"
            "- **Safety**: Source code was strictly read and analyzed. No files were modified automatically.\n"
        )


def generate_report(
    findings: List[Dict[str, Any]],
    title: str = "Csync AI Pull Request Review Report",
    repo_name: str = "",
    base_branch: Optional[str] = None,
    target_branch: Optional[str] = None,
) -> str:
    """
    Generate a Markdown pull request report from finding dictionaries.

    Args:
        findings: List of finding dictionaries from reviewer and scanner.
        title: Main report heading.
        repo_name: Optional repository name.
        base_branch: Optional base branch being compared against.
        target_branch: Optional current branch.

    Returns:
        Formatted Markdown string.
    """
    generator = ReportGenerator(
        findings=findings,
        title=title,
        repo_name=repo_name,
        base_branch=base_branch,
        target_branch=target_branch,
    )
    return generator.generate()


def save_report(
    markdown_content: str,
    output_path: str | Path = "report.md",
) -> Path:
    """
    Save the generated Markdown report to a file.

    Args:
        markdown_content: Markdown text.
        output_path: Target file path on disk.

    Returns:
        Resolved Path to the saved report file.
    """
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_content, encoding="utf-8")
    return path
