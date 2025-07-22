import requests
import datetime
import os
import json

# ------------------------------- #
#  Google Apps Script Endpoints   #
# ------------------------------- #
GAS_BASE_URL        = "https://script.google.com/macros/s/AKfycbxMmR1RCvdzLVdX6F2cntbfyC2VNSn38OO3b6dCsDjqMu_0T5L9h-AfRtGyAjHgPMYz/exec"
LOG_FUNCTION        = "logAgentAction"

# ------------------------------- #
#        Helper Functions         #
# ------------------------------- #
def call_gas_function(function_name, params=None, timeout=30):
    """
    Calls a Google Apps Script web app function with proper POST body and debug logging.
    """
    url = GAS_BASE_URL  # ❗ No longer appending ?function=... to the URL

    if params is None:
        params = {}
    params["function"] = function_name  # ✅ Ensure function name is in the POST body

    print("\n========== GAS CALL DEBUG ==========")
    print(f"→ Function: {function_name}")
    print(f"→ URL: {url}")
    print(f"→ Payload: {json.dumps(params)}")

    try:
        response = requests.post(url, json=params, timeout=timeout)

        print(f"→ Status Code: {response.status_code}")
        print(f"→ Raw Response: {response.text}")

        data = response.json()
        print("→ Parsed JSON Response:", json.dumps(data, indent=2))

        if not data.get("success", False):
            raise Exception(f"{function_name} error: {data.get('error', 'Unknown error')}")

        return data.get("result", data)

    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP request to GAS failed: {e}")
        raise
    except Exception as e:
        print(f"❌ GAS function error: {e}")
        raise


def log_action(action, outcome, notes, agent="Worker"):
    """
    Logs an action to the Google Sheet.
    """
    params = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action":    action,
        "outcome":   outcome,
        "notes":     notes,
        "agent":     agent
    }
    try:
        call_gas_function(LOG_FUNCTION, params)
    except Exception as e:
        print(f"⚠️ Failed to log action: {e}")

# ------------------------------- #
#         Error Escalation        #
# ------------------------------- #
def manager_handle_issue(row, error_msg):
    """
    Handles errors and escalates them to the manager.
    """
    row_number = row.get("Row")

    try:
        call_gas_function("logManagerThought", {
            "timestamp": datetime.datetime.now().isoformat(),
            "row":       row_number,
            "sku":       row.get("Title") or "Unknown",
            "thought":   f"Investigating error: {error_msg}",
            "confidence": "0.70"
        })
        call_gas_function("incrementProgressErrorCount", {"row": row_number})
    except Exception as log_err:
        print(f"⚠️ Failed to log to Thinking tab: {log_err}")

    try:
        error_count = call_gas_function("getProgressErrorCount", {"row": row_number}).get("count", 0)
    except Exception:
        error_count = 0

    reason = f"Auto-reset after {error_count} failed attempts" if error_count >= 3 else error_msg

    try:
        call_gas_function("updateRowNotes", {"row": row_number, "notes": reason})
    except Exception as e:
        print(f"⚠️ Failed to update row notes: {e}")

    if error_count >= 3:
        try:
            call_gas_function("updateRowStatus", {
                "row": row_number,
                "new_status": row.get("Status")
            })
            call_gas_function("clearThinkingTab")
            log_action(f"Row {row_number}", "Resolved", reason, agent="Manager")
            return
        except Exception as update_err:
            error_msg = f"Failed to reset status: {update_err}"

    call_gas_function("clearThinkingTab")
    log_action(f"Row {row_number}", "Escalated", reason, agent="Manager")

    try:
        call_gas_function("sendEscalationEmail", {
            "row": row_number,
            "sku": row.get("Title") or "Unknown",
            "status": row.get("Status"),
            "error": error_msg,
            "suggestion": reason
        })
    except Exception as e:
        print(f"⚠️ Failed to send escalation email: {e}")
