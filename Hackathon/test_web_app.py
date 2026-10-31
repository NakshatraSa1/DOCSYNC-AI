"""
Test Suite for Csync AI Web Application.

Verifies:
1. Web server initialization and template serving.
2. API endpoints: /api/status, /api/git-info, /api/rules, /api/history, /api/review, /api/export.
3. Review History modal behavior: empty state message, history persistence, pop-up retrieval.
"""

from __future__ import annotations

import json
from pathlib import Path

from starlette.testclient import TestClient

from history_manager import history_manager
import web_app


def test_web_application_endpoints():
    print("\n--- Running Test: Csync AI Web Application ---")
    client = TestClient(web_app.app)

    # 1. Test HTML Dashboard
    resp_home = client.get("/")
    assert resp_home.status_code == 200
    html = resp_home.text
    assert "Csync AI" in html
    assert "Smarter Code Reviews. Stronger Code." in html
    assert "Review History" in html
    assert "No reviews yet. Your completed reviews will appear here." in html
    assert "gemmaStatusPill" in html
    assert "reviewHistoryModal" in html
    print("Dashboard HTML template verification: PASSED")

    # 2. Test /api/status
    resp_status = client.get("/api/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert "ollama_online" in status_data
    assert status_data["model_name"] == "gemma4:e4b"
    print(f"API /api/status verification: PASSED (Ollama Online: {status_data['ollama_online']})")

    # 3. Test /api/git-info
    resp_git = client.get("/api/git-info")
    assert resp_git.status_code == 200
    git_data = resp_git.json()
    assert "is_repo" in git_data
    print("API /api/git-info verification: PASSED")

    # 4. Test /api/rules
    resp_rules = client.get("/api/rules")
    assert resp_rules.status_code == 200
    rules_data = resp_rules.json()
    assert "rules" in rules_data
    print("API /api/rules GET verification: PASSED")

    # 5. Test /api/history initial empty or real state
    # Reset history for test to verify exact required empty state
    history_manager.clear()
    resp_hist_empty = client.get("/api/history")
    assert resp_hist_empty.status_code == 200
    assert len(resp_hist_empty.json()["history"]) == 0
    print("API /api/history empty state: PASSED")

    # 6. Test /api/review in static-only mode for fast verification
    test_code = """
def authenticate(token):
    eval("verify(token)")
    print("token:", token)
"""
    resp_review = client.post(
        "/api/review",
        json={
            "scope": "custom",
            "custom_code": test_code,
            "custom_filename": "auth_service.py",
            "static_only": True,
        },
    )
    assert resp_review.status_code == 200
    review_data = resp_review.json()
    assert review_data["target_name"] == "auth_service.py"
    assert len(review_data["findings"]) >= 2
    assert review_data["counts"]["CRITICAL"] >= 1  # eval()
    assert review_data["counts"]["LOW"] >= 1       # print()
    assert "markdown_report" in review_data
    print(f"API /api/review execution: PASSED ({len(review_data['findings'])} findings)")

    # 7. Test /api/history now has the real review
    resp_hist_filled = client.get("/api/history")
    assert resp_hist_filled.status_code == 200
    history_list = resp_hist_filled.json()["history"]
    assert len(history_list) == 1
    assert history_list[0]["target_name"] == "auth_service.py"
    assert history_list[0]["status"] == "FAILED"
    print("API /api/history retrieval of real review: PASSED")

    # 8. Test /api/history/{id}
    rev_id = history_list[0]["id"]
    resp_item = client.get(f"/api/history/{rev_id}")
    assert resp_item.status_code == 200
    assert resp_item.json()["id"] == rev_id
    print("API /api/history/{id} detail retrieval: PASSED")

    # 9. Test /api/export
    resp_export = client.post(
        "/api/export",
        json={"markdown": review_data["markdown_report"]},
    )
    assert resp_export.status_code == 200
    assert "attachment; filename=\"csync_ai_report.md\"" in resp_export.headers.get("content-disposition", "")
    print("API /api/export report download: PASSED")

    print("\n==================================================")
    print(" ALL CSYNC AI WEB APPLICATION TESTS PASSED! ")
    print("==================================================\n")


if __name__ == "__main__":
    test_web_application_endpoints()
