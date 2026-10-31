"""
Csync AI Review History Manager.

Persists real review runs to a local JSON file.
Ensures zero fake data and provides reliable retrieval for the Review History pop-up panel.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

HISTORY_FILE = Path(".csync_history.json")


class HistoryManager:
    """Manages persistent review history on disk."""

    def __init__(self, file_path: Path = HISTORY_FILE):
        self.file_path = file_path

    def _read_data(self) -> List[Dict[str, Any]]:
        """Read all review history records."""
        if not self.file_path.is_file():
            return []
        try:
            content = self.file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    def _write_data(self, data: List[Dict[str, Any]]) -> None:
        """Write records to history file."""
        try:
            self.file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get_all(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get all review history items, newest first.
        Returns actual completed reviews.
        """
        records = self._read_data()
        records.sort(key=lambda x: x.get("timestamp_epoch", 0), reverse=True)
        return records[:limit]

    def get_by_id(self, review_id: str) -> Optional[Dict[str, Any]]:
        """Find a specific review by its unique identifier."""
        records = self._read_data()
        for item in records:
            if item.get("id") == review_id:
                return item
        return None

    def add_entry(
        self,
        target_name: str,
        review_type: str,
        findings: List[Dict[str, Any]],
        markdown_report: str,
        files_count: int = 1,
        engine: str = "Gemma 4 E4B + Scanner",
    ) -> Dict[str, Any]:
        """
        Record a genuine review session in the history.
        """
        now = time.time()
        readable_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))

        # Calculate counts
        counts = {
            "CRITICAL": sum(1 for f in findings if f.get("severity") == "CRITICAL"),
            "HIGH": sum(1 for f in findings if f.get("severity") == "HIGH"),
            "MEDIUM": sum(1 for f in findings if f.get("severity") == "MEDIUM"),
            "LOW": sum(1 for f in findings if f.get("severity") == "LOW"),
            "INFO": sum(1 for f in findings if f.get("severity") == "INFO"),
        }

        # Status verdict
        if counts["CRITICAL"] > 0 or counts["HIGH"] > 0:
            status = "FAILED"
        elif counts["MEDIUM"] > 0:
            status = "WARNINGS"
        else:
            status = "PASSED"

        entry: Dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "timestamp": readable_time,
            "timestamp_epoch": now,
            "target_name": target_name,
            "review_type": review_type,
            "files_count": files_count,
            "findings_count": len(findings),
            "counts": counts,
            "status": status,
            "engine": engine,
            "findings": findings,
            "markdown_report": markdown_report,
        }

        records = self._read_data()
        records.insert(0, entry)
        # Cap history to 100 entries
        self._write_data(records[:100])
        return entry

    def clear(self) -> None:
        """Clear review history."""
        self._write_data([])


# Global default instance
history_manager = HistoryManager()
