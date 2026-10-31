"""
PrivPR Git Handler.

Safely inspects git repositories for uncommitted changes and branch diffs.
Uses GitPython strictly in read-only mode to prevent any execution of
untrusted code from reviewed repositories.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import git
    from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError
except ImportError:  # pragma: no cover
    git = None  # type: ignore
    GitCommandError = Exception  # type: ignore
    InvalidGitRepositoryError = Exception  # type: ignore
    NoSuchPathError = Exception  # type: ignore


class GitHandler:
    """
    Safely reads uncommitted changes and branch diffs from a git repository.

    SECURITY NOTE: This handler NEVER executes scripts, hooks, or code from the
    reviewed repository. It only reads text diffs and file contents.
    """

    def __init__(self, repo_path: str | Path = "."):
        """
        Initialize the GitHandler for a given repository path.

        Args:
            repo_path: Path to the target git repository (defaults to current dir).
        """
        if git is None:
            raise RuntimeError(
                "GitPython is not installed. Please install it with `pip install GitPython`."
            )

        self.repo_path = Path(repo_path).resolve()
        try:
            self.repo = git.Repo(self.repo_path, search_parent_directories=True)
        except (InvalidGitRepositoryError, NoSuchPathError) as err:
            raise ValueError(
                f"Path '{self.repo_path}' is not a valid git repository: {err}"
            ) from err

    @property
    def current_branch(self) -> str:
        """Return the active branch name or commit hash if detached."""
        try:
            return self.repo.active_branch.name
        except TypeError:
            # Detached HEAD
            return self.repo.head.commit.hexsha[:8]
        except Exception:
            return "unknown"

    def get_uncommitted_changes(self) -> List[Dict[str, Any]]:
        """
        Retrieve all uncommitted changes (staged, unstaged, and untracked files).

        Returns:
            List of dictionaries containing:
                - filename: str
                - status: 'modified' | 'added' | 'untracked' | 'deleted'
                - diff: str
                - content: str (current file content if file exists)
        """
        results: Dict[str, Dict[str, Any]] = {}

        # 1. Unstaged diffs (working tree vs index)
        try:
            unstaged_diff_text = self.repo.git.diff()
            parsed_unstaged = self._parse_unified_diff(unstaged_diff_text)
            for item in parsed_unstaged:
                results[item["filename"]] = item
        except GitCommandError:
            pass

        # 2. Staged diffs (index vs HEAD, or initial commit if no HEAD)
        try:
            if self._has_commits():
                staged_diff_text = self.repo.git.diff("--cached", "HEAD")
            else:
                staged_diff_text = self.repo.git.diff("--cached")

            parsed_staged = self._parse_unified_diff(staged_diff_text)
            for item in parsed_staged:
                fn = item["filename"]
                if fn in results:
                    # Append diff if already partially in unstaged
                    results[fn]["diff"] = (
                        results[fn]["diff"] + "\n" + item["diff"]
                    ).strip()
                else:
                    results[fn] = item
        except GitCommandError:
            pass

        # 3. Untracked files (new files not yet added to git)
        try:
            untracked_files = self.repo.untracked_files
            for relative_fn in untracked_files:
                norm_fn = Path(relative_fn).as_posix()
                full_path = Path(self.repo.working_tree_dir or self.repo_path) / relative_fn
                if full_path.is_file():
                    try:
                        content = full_path.read_text(
                            encoding="utf-8", errors="replace"
                        )
                    except Exception:
                        content = ""

                    # Generate synthetic diff for new untracked file
                    diff_lines = [
                        f"--- /dev/null",
                        f"+++ b/{norm_fn}",
                        f"@@ -0,0 +1,{max(1, len(content.splitlines()))} @@",
                    ]
                    diff_lines.extend(f"+{line}" for line in content.splitlines())
                    synthetic_diff = "\n".join(diff_lines)

                    results[norm_fn] = {
                        "filename": norm_fn,
                        "status": "untracked",
                        "diff": synthetic_diff,
                        "content": content,
                    }
        except Exception:
            pass

        # Populate current file content if missing
        self._attach_file_contents(results)

        return list(results.values())

    def get_branch_diff(self, base_branch: str = "main") -> List[Dict[str, Any]]:
        """
        Compare the current branch against a selected base branch.

        Args:
            base_branch: The target base branch to compare against (e.g. 'main', 'master').

        Returns:
            List of dictionaries with changed filenames, status, diff, and content.
        """
        # Validate that base_branch exists in local or remote references
        target_ref = base_branch
        branches = [b.name for b in self.repo.branches]
        if base_branch not in branches:
            # Check remote references (e.g. origin/main)
            remote_matches = [
                r.name for r in self.repo.references if r.name.endswith(f"/{base_branch}")
            ]
            if remote_matches:
                target_ref = remote_matches[0]

        try:
            # Primary: diff current working tree and HEAD against base branch
            diff_text = self.repo.git.diff(target_ref)
        except GitCommandError:
            try:
                # Fallback: 3-dot diff between base branch and HEAD
                diff_text = self.repo.git.diff(f"{target_ref}...HEAD")
            except GitCommandError as exc:
                raise ValueError(
                    f"Could not diff against base branch '{base_branch}'. Verify that the branch exists."
                ) from exc

        parsed_items = self._parse_unified_diff(diff_text)
        results: Dict[str, Dict[str, Any]] = {item["filename"]: item for item in parsed_items}
        self._attach_file_contents(results)

        return list(results.values())

    def get_changed_files(self, base_branch: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Unified helper to get changed files:
        If `base_branch` is specified, compares against that branch;
        otherwise, inspects uncommitted changes.
        """
        if base_branch:
            return self.get_branch_diff(base_branch=base_branch)
        return self.get_uncommitted_changes()

    def _has_commits(self) -> bool:
        """Check if the repository has at least one commit."""
        try:
            _ = self.repo.head.commit
            return True
        except (ValueError, Exception):
            return False

    def _attach_file_contents(self, items_dict: Dict[str, Dict[str, Any]]) -> None:
        """Safely attach current on-disk content for each file."""
        root = Path(self.repo.working_tree_dir or self.repo_path)
        for fn, item in items_dict.items():
            if item.get("content"):
                continue
            full_path = root / fn
            if full_path.is_file():
                try:
                    item["content"] = full_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                except Exception:
                    item["content"] = ""
            else:
                item["content"] = ""

    @staticmethod
    def _parse_unified_diff(diff_text: str) -> List[Dict[str, Any]]:
        """
        Parse multi-file unified git diff output into individual file entries.
        """
        if not diff_text or not diff_text.strip():
            return []

        file_diffs: List[Dict[str, Any]] = []
        raw_sections = re.split(r"(?=^diff --git )", diff_text, flags=re.MULTILINE)

        for section in raw_sections:
            section = section.strip()
            if not section:
                continue

            # Extract filename from "diff --git a/filename b/filename"
            match = re.search(r"^diff --git a/(.*?) b/(.*?)$", section, flags=re.MULTILINE)
            if match:
                b_filename = match.group(2)
                filename = Path(b_filename).as_posix()
            else:
                # Fallback to +++ b/filename
                plus_match = re.search(r"^\+\+\+ b/(.*?)$", section, flags=re.MULTILINE)
                if plus_match:
                    filename = Path(plus_match.group(1)).as_posix()
                else:
                    filename = "unknown"

            # Determine status
            status = "modified"
            if "new file mode" in section or section.startswith("--- /dev/null"):
                status = "added"
            elif "deleted file mode" in section or "+++ /dev/null" in section:
                status = "deleted"

            file_diffs.append(
                {
                    "filename": filename,
                    "status": status,
                    "diff": section,
                    "content": "",
                }
            )

        return file_diffs


# Functional shortcuts
def get_uncommitted_changes(repo_path: str | Path = ".") -> List[Dict[str, Any]]:
    """Retrieve uncommitted changes from repository at repo_path."""
    handler = GitHandler(repo_path)
    return handler.get_uncommitted_changes()


def get_branch_diff(base_branch: str = "main", repo_path: str | Path = ".") -> List[Dict[str, Any]]:
    """Compare current branch against base_branch in repository at repo_path."""
    handler = GitHandler(repo_path)
    return handler.get_branch_diff(base_branch)


def get_changed_files(
    repo_path: str | Path = ".", base_branch: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get changed files (branch comparison or uncommitted)."""
    handler = GitHandler(repo_path)
    return handler.get_changed_files(base_branch)
