"""
Sample file for Pull Request review demonstration in Csync AI.
Contains sample patterns to demonstrate security, edge case, and code quality detection.
"""

import os


def process_payment(account_id: str, amount: float):
    # 1. Debug print statement (Code Quality smell)
    print(f"[DEBUG] Processing payment of ${amount} for account: {account_id}")

    # 2. SQL injection hazard (Security issue)
    query = f"SELECT balance FROM accounts WHERE id = '{account_id}'"

    # 3. Hardcoded test credential (Security issue)
    api_token = "ghp_123456789012345678901234567890123456"

    # 4. Unsafe eval execution
    eval("print('Payment verified')")

    return {"status": "success", "account": account_id, "amount": amount}
