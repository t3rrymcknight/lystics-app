import requests
import datetime
import os
import json
from openai import OpenAI

# ------------------------------- #
#  Google Apps Script Endpoints   #
# ------------------------------- #
GAS_BASE_URL        = "https://script.google.com/macros/s/AKfycbw7kHU5FzsWElC7QFL9iZcD_8bCK8BLmQMC1ds1-iJZKvIGRvkkp4cW7t2gEz9n5YL9/exec"
LOG_FUNCTION        = "logAgentAction"
GET_ROWS_FUNCTION   = "getRowsNeedingProcessing"
MAX_ROWS_PER_RUN    = 20
COOLDOWN_MINUTES    = 1

# ------------------------------- #
#        Helper Functions         #
# ------------------------------- #
def call_gas_function(function_name, params=None, timeout=30):
    """
    Generic caller for GAS web-app functions.
    """
    if params is None:
        params = {}
    url = f"{GAS_BASE_URL}?function={function_name}"

    try:
        response = requests.post(url, json=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        # Every GAS doPost returns { success, result } or { success, error }
        if not data.get("success", False):
            raise Exception(f"{function_name} error: {data.get('error', 'Unknown error')}")
        return data.get("result", {})     # unwrap the payload
    except requests.exceptions.RequestException as e:
        raise Exception(f"{function_name} failed: {str(e)}")

def log_action(action, outcome, notes, agent="Worker"):
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
#           Main Runner           #
# ------------------------------- #
def run_etsy_agent():
    # 1. Concurrency guard
    if call_gas_function("isWorkerActive").get("active"):
        log_action("Batch Skipped", "Worker already active", "")
        return {"status": "skipped", "message": "Worker already running"}

    call_gas_function("markWorkerActive")
    log_action("Batch Start", "Initiated", "", agent="Worker")

    summary_logs = []
    processed    = 0
    now          = datetime.datetime.now()
    response     = None

    try:
        # 2. Fetch rows
        response_json = call_gas_function(GET_ROWS_FUNCTION)
        print("🧪 Raw GAS Response:", json.dumps(response_json, indent=2))

        rows = response_json.get("rows", [])
        print(f"📦 Fetched {len(rows)} rows for processing")

        for r in rows:
            print("🧾 Received Row:", json.dumps(r, indent=2))

        # 3. Per-row loop
        for row in rows:
            if processed >= MAX_ROWS_PER_RUN:
                break

            row_number   = row.get("Row")
            last_attempt = row.get("Last Attempted")
            status       = str(row.get("Status") or "").strip()

            print(f"🪪 Row {row_number} | Status: '{status}' | Last Attempted: {last_attempt}")

            # Cool-down
            if last_attempt:
                try:
                    last_dt = datetime.datetime.fromisoformat(last_attempt)
                    if (now - last_dt).total_seconds() < COOLDOWN_MINUTES * 60:
                        log_action(f"Row {row_number}", "Skipped", "Cooldown active")
                        continue
                except ValueError:
                    print(f"⚠️ Failed to parse 'Last Attempted' timestamp for row {row_number}")

            # Mark “processing”
            call_gas_function("updateLastAttempted", {
                "row":       row_number,
                "timestamp": now.isoformat()
            })
            call_gas_function("updateRowProgress", {"row": row_number, "progress": "Processing"})
            print(f"🕓 Updated Last Attempted for row {row_number}")

            # Dispatch
            try:
                if status == "Download Image":
                    fn_name = "downloadImagesToDrive"
                elif status == "Create Thumbnail":
                    fn_name = "copyResizeImageAndStoreUrl"
                elif status == "Describe Image":
                    fn_name = "processImagesWithOpenAI"
                elif status == "Add Mockups":
                    fn_name = "updateImagesFromMockupFolders"
                elif status == "Ready":
                    fn_name = "processListings"
                else:
                    print(f"❓ Unknown status '{status}' for Row {row_number}")
                    log_action(f"Row {row_number}", "Skipped", f"Status not actionable: {status}")
                    continue

                print(f"📤 Triggering GAS function: {fn_name} for row {row_number}")
                response = call_gas_function(fn_name, {"row": row_number})
                print(f"🔁 Response from {status} function:", response)

                if response is None:
                    raise Exception(f"Function {status} failed to return any response.")

                if not isinstance(response, dict) or response.get("error"):
                    raise Exception(f"Function {status} returned error: {response.get('error', 'Unknown')}")

                # Consider it success if no error was returned

                msg = f"✅ Row {row_number} succeeded for status: {status}"
                log_action(f"Row {row_number}", "Success", msg)
                summary_logs.append(msg)
                processed += 1

            except Exception as e:
                err_msg = f"❌ Row {row_number} error: {e}"
                log_action(f"Row {row_number}", "Error", err_msg)
                summary_logs.append(err_msg)
                manager_handle_issue(row, str(e))

        result = {"status": "success", "rows_processed": processed, "response": response}
        log_action("Batch Processed", f"{processed} rows", "End of run", agent="Worker")

    except Exception as e:
        summary_logs.append(f"🔥 Critical error: {e}")
        result = {"status": "error", "message": str(e)}
        log_action("Batch Error", "Critical Failure", str(e), agent="Worker")

    finally:
        # 4. Tear-down
        call_gas_function("markWorkerInactive")
        call_gas_function("sendAgentSummaryEmail", {
            "status": result.get("status"),
            "logs":   summary_logs,
            "summary": f"{processed} rows processed by Worker at "
                       f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        })
        return result

# ------------------------------- #
#         Error Escalation        #
# ------------------------------- #
def manager_handle_issue(row, error_msg):
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

    suggestion = suggest_next_action_for_row(row, error_msg)

    try:
        error_count = call_gas_function("getProgressErrorCount", {"row": row_number}).get("count", 0)
    except Exception as e:
        error_count = 0

    if error_count >= 3:
        suggestion["action"] = "reset_status"
        suggestion["new_status"] = row.get("Status")  # fallback to current
        suggestion["reason"] = "Auto-reset after 3 failed attempts"

    try:
        call_gas_function("updateRowNotes", {"row": row_number, "notes": suggestion.get("reason")})
    except Exception as e:
        print(f"⚠️ Failed to update row notes: {e}")

    if suggestion.get("action") == "reset_status":
        try:
            call_gas_function("updateRowStatus", {
                "row":        row_number,
                "new_status": suggestion["new_status"]
            })
            call_gas_function("clearThinkingTab")
            log_action(f"Row {row_number}", "Resolved", suggestion["reason"], agent="Manager")
            return
        except Exception as update_err:
            error_msg = f"Failed to reset status: {update_err}"

    call_gas_function("clearThinkingTab")
    log_action(f"Row {row_number}", "Escalated",
               suggestion.get("reason") or error_msg,
               agent="Manager")

    try:
        call_gas_function("sendEscalationEmail", {
            "row":    row_number,
            "sku":    row.get("Title") or "Unknown",
            "status": row.get("Status"),
            "error":  error_msg,
            "suggestion": suggestion.get("reason")
        })
    except Exception as e:
        print(f"⚠️ Failed to send escalation email: {e}")

# ------------------------------- #
#     LLM-Assisted Suggestions    #
# ------------------------------- #
def suggest_next_action_for_row(row, error_msg):
    """
    Ask the LLM how to resolve a failed row.  Returns a dict like:
    { action, new_status?, reason }
    """
    try:
        api_key = call_gas_function("getOpenAIKey").get("key")
        client = OpenAI(api_key=api_key)

        context = (
            f"Row data: {json.dumps(row)}\n"
            f"Error: {error_msg}\n\n"
            "You are a helpful agent managing an Etsy listing pipeline. "
            "What is the next action I should take to resolve this? "
            "Reply in JSON with fields: action, new_status (if any), reason."
        )

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an Etsy product operations agent."},
                {"role": "user",   "content": context}
            ],
            temperature=0.3
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        return {
            "action": "escalate",
            "reason": f"LLM failed or returned unparseable output: {e}"
        }