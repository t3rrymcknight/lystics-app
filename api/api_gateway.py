import requests
import datetime
import os
import json

# ------------------------------- #
#  Google Apps Script Endpoints   #
# ------------------------------- #
GAS_BASE_URL        = "https://script.google.com/macros/s/AKfycbwgUgALGV2aACKoGg0a9tOlY2BDj5xx_lTV_ukoLFHUGDFdZvOlBh_qYTYwXXNeo0bl/exec"
LOG_FUNCTION        = "logAgentAction"

# ------------------------------- #
#        Helper Functions         #
# ------------------------------- #
def call_gas_function(function_name, params=None, timeout=30):
    """
    Calls a function in the Google Apps Script project.
    """
    url = f"{GAS_BASE_URL}?function={function_name}"

    print("\n========== GAS CALL DEBUG ==========")
    print(f"-> Function: {function_name}")
    print(f"-> URL: {url}")
    print(f"-> Params: {json.dumps(params) if params else '{}'}")

    try:
        if not params or (isinstance(params, dict) and not params):
            # No params: use GET
            response = requests.get(url, timeout=timeout)
        else:
            # With params: use POST
            response = requests.post(url, json=params, timeout=timeout)

        print(f"-> Status code: {response.status_code}")
        print(f"-> Raw response: {response.text}")

        try:
            data = response.json()
            print("-> Decoded JSON:", json.dumps(data, indent=2))
        except Exception as e:
            print(f"-> JSON decode error: {e}")
            data = {}

        response.raise_for_status()

        if not data.get("success", False):
            raise Exception(f"{function_name} error: {data.get('error', 'Unknown error')}")
        
        return data.get("result", data)
    except requests.exceptions.RequestException as e:
        print(f"❌ {function_name} failed: {str(e)}")
        raise Exception(f"{function_name} failed: {str(e)}")

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