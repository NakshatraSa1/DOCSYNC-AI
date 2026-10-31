"""
Csync AI Code Reviewer.

Local-first code reviewer powered exclusively by Gemma 4 E4B via Ollama
and the Google Antigravity SDK.
Tagline: Smarter Code Reviews. Stronger Code.

Reviews security, logic errors, edge cases, runtime risks, and code quality.
Produces structured JSON findings while strictly preserving source code integrity.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

try:
    from google.antigravity import Agent, LocalOpenAIAgentConfig, types
except ImportError:  # pragma: no cover
    Agent = None  # type: ignore
    LocalOpenAIAgentConfig = None  # type: ignore
    types = None  # type: ignore

logger = logging.getLogger("csync.reviewer")

# STRICT LOCAL MODEL CONFIGURATION
ALLOWED_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434/v1"

ALLOWED_CATEGORIES = {
    "Security",
    "Logic Errors",
    "Logic Error",
    "Edge Cases",
    "Edge Case",
    "Runtime Risks",
    "Runtime Risk",
    "Code Quality",
}

ALLOWED_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}


class OllamaConnectionError(Exception):
    """Raised when the local Ollama Gemma service is unreachable."""
    pass


class CodeReviewer:
    """
    Local AI Code Reviewer utilizing Gemma 4 E4B.
    """

    def __init__(
        self,
        model: str = ALLOWED_MODEL,
        base_url: str = DEFAULT_OLLAMA_ENDPOINT,
    ):
        """
        Initialize the local Gemma 4 E4B reviewer.

        Args:
            model: Must be 'gemma4:e4b'.
            base_url: Ollama OpenAI-compatible endpoint (http://localhost:11434/v1).
        """
        if model != ALLOWED_MODEL:
            raise ValueError(
                f"Invalid model '{model}'. PrivPR strictly permits only '{ALLOWED_MODEL}'."
            )

        self.model = model
        self.base_url = base_url

    def _get_agent_config(self) -> Any:
        """Create the LocalOpenAIAgentConfig for Gemma 4 E4B."""
        if LocalOpenAIAgentConfig is None:
            raise RuntimeError(
                "google-antigravity SDK is not installed. Please install `google-antigravity`."
            )

        # Explicitly disable tool definitions to prevent tool overhead and token exhaustion
        capabilities = None
        if types is not None:
            capabilities = types.CapabilitiesConfig(
                enabled_tools=[],
                file_reads=False,
                file_writes=False,
                command_execution=False,
                subagents=False,
                mcp=False,
            )

        return LocalOpenAIAgentConfig(
            model=self.model,
            base_url=self.base_url,
            capabilities=capabilities,
        ).lightweight()

    async def review_code(
        self,
        code: str,
        filename: str = "snippet.py",
        team_rules: str = "",
        diff: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Asynchronously review code or diff using Gemma 4 E4B.

        Args:
            code: Source code content of the file.
            filename: Target file path or name.
            team_rules: Custom team rules / coding standards (e.g. from .privpr.md).
            diff: Optional git diff for contextual review.

        Returns:
            List of structured finding dictionaries.
        """
        if not code.strip() and not diff.strip():
            return []

        prompt = self._build_prompt(
            filename=filename,
            code=code,
            diff=diff,
            team_rules=team_rules,
        )

        try:
            config = self._get_agent_config()
            async with Agent(config) as agent:
                response = await agent.chat(prompt)
                raw_text = await response.text()

            return self._parse_and_validate_response(raw_text, filename=filename)

        except (ConnectionError, OSError) as exc:
            logger.error("Connection error reaching local Gemma 4 E4B at %s: %s", self.base_url, exc)
            return [
                {
                    "filename": filename,
                    "line": 1,
                    "category": "Security",
                    "severity": "CRITICAL",
                    "title": "Local Ollama Connection Failed",
                    "explanation": (
                        f"Could not connect to Gemma 4 E4B at {self.base_url}. "
                        "PrivPR requires a running Ollama instance on localhost. "
                        f"Underlying error: {exc}"
                    ),
                    "suggestion": (
                        "Verify Ollama is running (`ollama serve`) and the model is loaded (`ollama run gemma4:e4b`)."
                    ),
                    "snippet": "",
                }
            ]
        except Exception as exc:
            logger.error("Unexpected error during review: %s", exc)
            # Catch any other SDK/HTTP communication failures gracefully
            err_msg = str(exc)
            if "Connect" in err_msg or "11434" in err_msg or "refused" in err_msg.lower():
                return [
                    {
                        "filename": filename,
                        "line": 1,
                        "category": "Security",
                        "severity": "CRITICAL",
                        "title": "Local Ollama Connection Error",
                        "explanation": f"Failed to reach local Ollama endpoint ({self.base_url}): {err_msg}",
                        "suggestion": "Start Ollama with `ollama serve` and ensure port 11434 is accessible.",
                        "snippet": "",
                    }
                ]

            return [
                {
                    "filename": filename,
                    "line": 1,
                    "category": "Review Engine",
                    "severity": "MEDIUM",
                    "title": "Review Engine Error",
                    "explanation": f"An error occurred while analyzing {filename}: {err_msg}",
                    "suggestion": "Check application logs for details.",
                    "snippet": "",
                }
            ]

    async def review_files(
        self,
        files: List[Dict[str, Any]],
        team_rules: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Review multiple changed files sequentially or concurrently.

        Args:
            files: List of dicts with 'filename', 'content', and optional 'diff'.
            team_rules: Custom team rules string.

        Returns:
            Aggregated list of all findings.
        """
        all_findings: List[Dict[str, Any]] = []
        for file_info in files:
            fn = file_info.get("filename", "unknown")
            content = file_info.get("content", "")
            diff = file_info.get("diff", "")

            # Skip deleted files
            if file_info.get("status") == "deleted":
                continue

            findings = await self.review_code(
                code=content,
                filename=fn,
                team_rules=team_rules,
                diff=diff,
            )
            all_findings.extend(findings)

        return all_findings

    def _build_prompt(
        self,
        filename: str,
        code: str,
        diff: str,
        team_rules: str,
    ) -> str:
        """Construct a concise, focused prompt for Gemma 4 E4B."""
        rules_text = f"\nTEAM RULES:\n{team_rules.strip()}\n" if team_rules.strip() else ""
        diff_text = f"\nGIT DIFF CONTEXT:\n```diff\n{diff[:3000]}\n```\n" if diff.strip() else ""
        code_excerpt = code[:6000] if code.strip() else "(See diff context above)"

        return f"""You are Csync AI, a local-first AI code reviewer running Gemma 4 E4B.
Smarter Code Reviews. Stronger Code.
Review this code for:
1. Security (Vulnerabilities, injection, secrets, dangerous calls)
2. Logic Errors (Calculation bugs, incorrect conditions)
3. Edge Cases (Null/None, empty inputs, boundary conditions)
4. Runtime Risks (Unhandled exceptions, resource leaks)
5. Code Quality (Readability, team rules adherence)

RULES:
- Do NOT modify any code automatically.
- Only report genuine, actionable issues.
- Keep titles and explanations concise.
- Respond ONLY with a valid JSON array. No conversational text outside JSON.
{rules_text}
FILE: {filename}
{diff_text}
SOURCE CODE:
```python
{code_excerpt}
```

REQUIRED JSON SCHEMA:
[
  {{
    "filename": "{filename}",
    "line": <integer line number or 1>,
    "category": "Security" | "Logic Errors" | "Edge Cases" | "Runtime Risks" | "Code Quality",
    "severity": "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO",
    "title": "<Concise issue title>",
    "explanation": "<Concise explanation of the risk>",
    "suggestion": "<Concise fix recommendation>",
    "snippet": "<Flagged code snippet>"
  }}
]

If no issues are found, return: []
JSON:"""

    def _parse_and_validate_response(
        self,
        raw_text: str,
        filename: str,
    ) -> List[Dict[str, Any]]:
        """
        Parse raw LLM response into structured findings with error resilience.
        Handles markdown fences, leading/trailing prose, and malformed JSON.
        """
        cleaned = raw_text.strip()
        if not cleaned:
            return []

        # 1. Strip markdown code fences if present (e.g. ```json ... ```)
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if fence_match:
            candidate_json = fence_match.group(1).strip()
        else:
            candidate_json = cleaned

        # 2. Extract JSON array bounds if embedded in explanatory text
        if "[" in candidate_json and "]" in candidate_json:
            first_bracket = candidate_json.find("[")
            last_bracket = candidate_json.rfind("]")
            candidate_json = candidate_json[first_bracket : last_bracket + 1]

        # 3. Attempt JSON parse
        parsed_data = None
        try:
            parsed_data = json.loads(candidate_json)
        except json.JSONDecodeError:
            # Fallback attempt: check if single JSON object was returned instead of array
            if "{" in candidate_json and "}" in candidate_json:
                first_brace = candidate_json.find("{")
                last_brace = candidate_json.rfind("}")
                try:
                    obj = json.loads(candidate_json[first_brace : last_brace + 1])
                    if isinstance(obj, dict):
                        # Could be {"findings": [...]} or a single finding
                        if "findings" in obj and isinstance(obj["findings"], list):
                            parsed_data = obj["findings"]
                        else:
                            parsed_data = [obj]
                except json.JSONDecodeError:
                    pass

        # If completely unparseable, return a graceful informational finding
        if parsed_data is None:
            logger.warning("Malformed JSON response from Gemma: %s", raw_text[:200])
            # If the model explicitly said no issues in text
            lower_raw = raw_text.lower()
            if "no issues" in lower_raw or "looks good" in lower_raw or "lgtm" in lower_raw:
                return []

            return [
                {
                    "filename": filename,
                    "line": 1,
                    "category": "Code Quality",
                    "severity": "INFO",
                    "title": "AI Review Commentary (Unstructured)",
                    "explanation": (
                        "The model produced textual feedback that could not be parsed as strict JSON:\n"
                        f"{raw_text[:400]}"
                    ),
                    "suggestion": "Review the commentary above manually.",
                    "snippet": "",
                }
            ]

        if not isinstance(parsed_data, list):
            return []

        # 4. Normalize and validate each finding
        validated: List[Dict[str, Any]] = []
        for item in parsed_data:
            if not isinstance(item, dict):
                continue

            # Standardize category
            raw_cat = str(item.get("category", "Code Quality")).strip()
            cat = "Code Quality"
            for ac in ALLOWED_CATEGORIES:
                if ac.lower() == raw_cat.lower():
                    cat = ac
                    break

            # Standardize severity
            raw_sev = str(item.get("severity", "MEDIUM")).strip().upper()
            sev = raw_sev if raw_sev in ALLOWED_SEVERITIES else "MEDIUM"

            # Parse line number safely
            line_val = item.get("line")
            try:
                line_num = int(line_val) if line_val is not None else 1
            except (ValueError, TypeError):
                line_num = 1

            finding = {
                "filename": str(item.get("filename") or filename),
                "line": line_num,
                "category": cat,
                "severity": sev,
                "title": str(item.get("title") or "Code Issue Identified"),
                "explanation": str(item.get("explanation") or "No explanation provided."),
                "suggestion": str(item.get("suggestion") or "Review and refactor."),
                "snippet": str(item.get("snippet") or ""),
            }
            validated.append(finding)

        return validated


# Direct helper function
async def review_code(
    code: str,
    filename: str = "snippet.py",
    team_rules: str = "",
    diff: str = "",
) -> List[Dict[str, Any]]:
    """
    Convenience function to review code with the default Gemma 4 E4B reviewer.
    """
    reviewer = CodeReviewer()
    return await reviewer.review_code(
        code=code,
        filename=filename,
        team_rules=team_rules,
        diff=diff,
    )
