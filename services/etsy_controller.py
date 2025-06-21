import requests
import datetime
from openai import OpenAI
import os
import json

GAS_BASE_URL = "https://script.google.com/macros/s/AKfycbxlX6O1yD1HBfixFvI2VzZxP6nQzRe5Sd5hfnQrBxDD8wwGjFkxBMIl_k9yLT9U_iI/exec"
LOG_FUNCTION = "logAgentAction"
GET_ROWS_FUNCTION = "getRowsNeedingProcessing"
MAX_ROWS_PER_RUN = 50
COOLDOWN_MINUTES = 30

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise EnvironmentError("Required environment variable OPENAI_API_KEY is not set")
client = OpenAI(api_key=api_key)

def call_gas_function(function_name, params={}, timeout=30):
    url = f"{GAS_BASE_URL}?function={function_name}"
    try:
        response = requests.post(url, json=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        # Handle the Apps Script doPost wrapper which returns { success, result } or { success, error }
        if not data.get("success", False):
            raise Exception(f"{function_name} error: {data.get('error', 'Unknown error')}")
        # Unwrap the actual function result
        return data.get("result", {})
    except requests.exceptions.RequestException as e:
        raise Exception(f"{function_name} failed: {str(e)}")

def log_action(action, outcome, notes, agent="Worker"):
    params = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "outcome": outcome,
        "notes": notes,
        "agent": agent
    }
    try:
        call_gas_function(LOG_FUNCTION, params)
    except Exception as e:
        print(f"⚠️ Failed to log action: {e}")

def run_etsy_agent():
    if call_gas_function("isWorkerActive").get("active"):
        log_action("Batch Skipped", "Worker already active", "")
        return {"status": "skipped", "message": "Worker already running"}

    call_gas_function("markWorkerActive")
    log_action("Batch Start", "Initiated", "", agent="Worker")

    summary_logs = []
    processed = 0
    now = datetime.datetime.now()
    response = None

    try:
        response_json = call_gas_function(GET_ROWS_FUNCTION)
        print("🧪 Raw GAS Response:", json.dumps(response_json, indent=2))

        rows = response_json.get("rows", [])
        print(f"📦 Fetched {len(rows)} rows for processing")

        for r in rows:
            print("🧾 Received Row:", json.dumps(r, indent=2))

        for row in rows:
            if processed >= MAX_ROWS_PER_RUN:
                break

            try:
                row_number = row.get("Row")
                last_attempt = row.get("Last Attempted")
                status = str(row.get("Status") or "").strip()

                print(f"🪪 Row {row_number} | Status: '{status}' | Last Attempted: {last_attempt}")

                if last_attempt:
                    try:
                        last_dt = datetime.datetime.fromisoformat(last_attempt)
                        if (now - last_dt).total_seconds() < COOLDOWN_MINUTES * 60:
                            log_action(f"Row {row_number}", "Skipped", "Cooldown active")
                            continue
                    except:
                        print(f"⚠️ Failed to parse 'Last Attempted' timestamp for row {row_number}")

                # Mark row as processing
                call_gas_function("updateRowStatus", {
                    "row": row_number,
                    "new_status": f"Processing: {status}"
                })
                call_gas_function("updateLastAttempted", {
                    "row": row_number,
                    "timestamp": now.isoformat()
                })
                print(f"🕓 Updated Last Attempted for row {row_number}")

                print(f"🧠 Calling function for status: {status} (Row {row_number})")

                response = None
                if status == "Download Image":
                    print(f"📤 Triggering GAS function: downloadImagesToDrive for row {row_number}")
                    response = call_gas_function("downloadImagesToDrive", {"row": row_number})
                    summary_logs.append(f"📤 Function '{status}' executed for row {row_number}. Response: {response}")
                elif status == "Create Thumbnail":
                    print(f"📤 Triggering GAS function: copyResizeImageAndStoreUrl for row {row_number}")
                    response = call_gas_function("copyResizeImageAndStoreUrl", {"row": row_number})
                    summary_logs.append(f"📤 Function '{status}' executed for row {row_number}. Response: {response}")
                elif status == "Describe Image":
                    print(f"📤 Triggering GAS function: processImagesWithOpenAI for row {row_number}")
                    response = call_gas_function("processImagesWithOpenAI", {"row": row_number})
                    summary_logs.append(f"📤 Function '{status}' executed for row {row_number}. Response: {response}")
                elif status == "Add Mockups":
                    print(f"📤 Triggering GAS function: updateImagesFromMockupFolders for row {row_number}")
                    response = call_gas_function("updateImagesFromMockupFolders", {"row": row_number})
                    summary_logs.append(f"📤 Function '{status}' executed for row {row_number}. Response: {response}")
                elif status == "Ready":
                    print(f"📤 Triggering GAS function: processListings for row {row_number}")
                    response = call_gas_function("processListings", {"row": row_number})
                    summary_logs.append(f"📤 Function '{status}' executed for row {row_number}. Response: {response}")
                else:
                    print(f"❓ Unknown status '{status}' for Row {row_number}")
                    log_action(f"Row {row_number}", "Skipped", f"Status not actionable: {status}")
                    continue

                print(f"🔁 Response from {status} function:", response)

                if not response or not response.get("success", True):
                    raise Exception(f"Function {status} failed silently or returned invalid response: {response}")

                msg = f"✅ Row {row_number} succeeded for status: {status}"
                log_action(f"Row {row_number}", "Success", msg)
                summary_logs.append(msg)
                processed += 1

            except Exception as e:
                err_msg = f"❌ Row {row.get('Row')} error: {e}"
                log_action(f"Row {row.get('Row')}", "Error", err_msg)
                summary_logs.append(err_msg)
                manager_handle_issue(row, str(e))

        result = {"status": "success", "rows_processed": processed, "response": response}
        log_action("Batch Processed", f"{processed} rows", "End of run", agent="Worker")

    except Exception as e:
        summary_logs.append(f"🔥 Critical error: {e}")
        result = {"status": "error", "message": str(e)}
        log_action("Batch Error", "Critical Failure", str(e), agent="Worker")

    finally:
        call_gas_function("markWorkerInactive")
        call_gas_function("sendAgentSummaryEmail", {
            "status": result.get("status"),
            "logs": summary_logs,
            "summary": f"{processed} rows processed by Worker at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        })
        return result

def manager_handle_issue(row, error_msg):
    row_number = row.get("Row")

    try:
        call_gas_function("logManagerThought", {
            "timestamp": datetime.datetime.now().isoformat(),
            "row": row_number,
            "sku": row.get("Title") or "Unknown",
            "thought": f"Investigating error: {error_msg}",
            "confidence": "0.70"
        })
    except Exception as log_err:
        print(f"⚠️ Failed to log to Thinking tab: {log_err}")

    suggestion = suggest_next_action_for_row(row, error_msg)

    if suggestion.get("action") == "reset_status":
        try:
            call_gas_function("updateRowStatus", {
                "row": row_number,
                "new_status": suggestion["new_status"]
            })
            call_gas_function("clearThinkingTab")
            log_action(f"Row {row_number}", "Resolved", suggestion["reason"], agent="Manager")
            return
        except Exception as update_err:
            error_msg = f"Failed to reset status: {update_err}"

    call_gas_function("clearThinkingTab")
    log_action(f"Row {row_number}", "Escalated", suggestion.get("reason") or error_msg, agent="Manager")

    try:
        call_gas_function("sendEscalationEmail", {
            "row": row_number,
            "sku": row.get("Title") or "Unknown",
            "status": row.get("Status"),
            "error": error_msg,
            "suggestion": suggestion.get("reason")
        })
    except Exception as e:
        print(f"⚠️ Failed to send escalation email: {e}")

def suggest_next_action_for_row(row, error_msg):
    try:
        context = f"Row data: {json.dumps(row)}\nError: {error_msg}\n"
        prompt = f"You are a helpful agent managing an Etsy listing pipeline. {context}What is the next action I should take to resolve this? Reply in JSON with action, new_status (if any), and reason."

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an Etsy product operations agent."},
                {"role": "user", "content": prompt}
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
