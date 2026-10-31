"""
End-to-end live server test for Csync AI.
Tests all button flows: git-info, git-init, review, export, history modal.
"""
import json
import time
import requests
import subprocess
import sys
import os

BASE_URL = "http://127.0.0.1:8000"

def check_server():
    try:
        r = requests.get(f"{BASE_URL}/", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

def run_tests():
    print("=== Csync AI Live Server Test ===\n")
    passed = 0
    failed = 0

    def test(name, result, extra=""):
        nonlocal passed, failed
        status = "PASS" if result else "FAIL"
        icon = "OK" if result else "XX"
        print(f"  [{icon}] {name}: {status}{' - ' + extra if extra else ''}")
        if result:
            passed += 1
        else:
            failed += 1
        return result

    # 1. Dashboard loads
    r = requests.get(f"{BASE_URL}/")
    test("Dashboard loads", r.status_code == 200 and "Csync AI" in r.text)
    test("Tagline in dashboard", "Smarter Code Reviews. Stronger Code." in r.text)

    # 2. Gemma status
    r = requests.get(f"{BASE_URL}/api/status")
    d = r.json()
    test("/api/status responds", r.status_code == 200, f"ollama_online={d.get('ollama_online')}")

    # 3. Git info (Refresh Git button)
    r = requests.get(f"{BASE_URL}/api/git-info?repo_path=.")
    d = r.json()
    test("/api/git-info (Refresh Git)", r.status_code == 200 and d.get("is_repo"), 
         f"branch={d.get('current_branch')}, uncommitted={d.get('uncommitted_count')}")

    # 4. Git info with explicit path
    r = requests.get(f"{BASE_URL}/api/git-info", params={"repo_path": os.getcwd()})
    d = r.json()
    test("/api/git-info with explicit path", r.status_code == 200 and d.get("is_repo"))

    # 5. Git init
    r = requests.post(f"{BASE_URL}/api/git-init", json={"repo_path": "."})
    d = r.json()
    test("/api/git-init route exists", r.status_code == 200, str(d.get("success")))

    # 6. Rules load (Save Rules button)
    r = requests.get(f"{BASE_URL}/api/rules")
    d = r.json()
    test("/api/rules GET (load rules)", r.status_code == 200 and "rules" in d and len(d["rules"]) > 0)

    # 7. Rules save
    rules_content = "# Test rule\n- Do not use eval()"
    r = requests.post(f"{BASE_URL}/api/rules", json={"rules": rules_content})
    d = r.json()
    test("/api/rules POST (save rules)", r.status_code == 200 and d.get("success"))

    # 8. History empty check (Review History modal)
    r = requests.get(f"{BASE_URL}/api/history")
    d = r.json()
    test("/api/history GET (history modal data)", r.status_code == 200 and "history" in d,
         f"{len(d.get('history', []))} records")

    # 9. Review — static scan only, custom snippet (Start Review button)
    r = requests.post(f"{BASE_URL}/api/review", json={
        "scope": "custom",
        "custom_code": "eval(user_input)\npassword = 'secret123'\n",
        "custom_filename": "auth.py",
        "static_only": True
    })
    d = r.json()
    findings_count = len(d.get("findings", []))
    test("/api/review (Start Review - static)", r.status_code == 200 and findings_count >= 1,
         f"{findings_count} findings, status={d.get('status')}")

    # 10. History after review (history modal update)
    r = requests.get(f"{BASE_URL}/api/history")
    d = r.json()
    history_count = len(d.get("history", []))
    test("/api/history after review", history_count >= 1, f"{history_count} records")

    # 11. History item detail (Load Results button)
    if history_count > 0:
        review_id = d["history"][0]["id"]
        r = requests.get(f"{BASE_URL}/api/history/{review_id}")
        d2 = r.json()
        test(f"/api/history/{{id}} (Load Results)", r.status_code == 200 and "findings" in d2,
             f"findings={len(d2.get('findings', []))}")

    # 12. Review — uncommitted changes
    r = requests.post(f"{BASE_URL}/api/review", json={
        "scope": "uncommitted",
        "repo_path": ".",
        "static_only": True
    })
    d = r.json()
    test("/api/review uncommitted scope", r.status_code == 200,
         f"files={d.get('files_count')}, findings={len(d.get('findings', []))}")

    # 13. Review — branch comparison
    r = requests.post(f"{BASE_URL}/api/review", json={
        "scope": "branch",
        "repo_path": ".",
        "base_branch": "main",
        "static_only": True
    })
    d = r.json()
    test("/api/review branch scope", r.status_code == 200,
         f"files={d.get('files_count')}")

    # 14. Export report (Export Report button)
    r = requests.post(f"{BASE_URL}/api/export", json={"markdown": "# Test Report\n\nTest content."})
    test("/api/export (Export Report)", r.status_code == 200 and "csync_ai_report.md" in r.headers.get("Content-Disposition", ""),
         f"content-type={r.headers.get('Content-Type')}")

    print(f"\n{'='*50}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    return failed == 0

if __name__ == "__main__":
    os.chdir(r"C:\Hackathon")
    
    if not check_server():
        print("Server not running at", BASE_URL)
        print("Start it with: python web_app.py")
        sys.exit(1)
    
    success = run_tests()
    sys.exit(0 if success else 1)
