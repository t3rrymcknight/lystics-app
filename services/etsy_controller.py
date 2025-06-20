# services/etsy_controller.py
import requests
import datetime
import openai
import os

GAS_BASE_URL = "https://script.google.com/macros/s/AKfycbxdyW_RnE8LFKrrm1cFE45kia9pdb_5ytzXGdvflZ8C5oHrd-QTYnRKD5OUTW1DKgCd/exec"
LOG_FUNCTION = "logAgentAction"
GET_ROWS_FUNCTION = "getRowsNeedingProcessing"
ADMIN_EMAIL = "support@tmk.digital"

openai.api_key = os.getenv("OPENAI_API_KEY")

def call_gas_function(function_name, params={}, timeout=30):
    url = f"{GAS_BASE_URL}?function={function_name}"
    try:
        response = requests.post(url, json=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
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
    log_action("Batch Start", "Initiated", "", agent="Worker")

    try:
        rows = call_gas_function(GET_ROWS_FUNCTION).get("rows", [])
        processed = 0

        for row in rows:
            try:
                status = row.get("Status")
                sku = row.get("SKU") or row.get("variantSKU") or row.get("Title") or "?"

                if status == "Download Image":
                    call_gas_function("downloadImagesToDrive", {"sku": sku})
                elif status == "Create Thumbnail":
                    call_gas_function("copyResizeImageAndStoreUrl", {"sku": sku})
                elif status == "Describe Image":
                    call_gas_function("processImagesWithOpenAI", {"sku": sku})
                elif status == "Add Mockups":
                    call_gas_function("updateImagesFromMockupFolders", {"sku": sku})
                elif status == "Ready":
                    call_gas_function("processListings", {"sku": sku})
                else:
                    log_action(f"Row {row.get('Row')}", "Skipped", f"Status is not actionable: {status}")
                    continue

                log_action(f"Row {row.get('Row')}", "Success", f"{sku} processed for {status}")
                processed += 1

            except Exception as e:
                log_action(f"Row {row.get('Row')}", "Error", str(e))
                manager_handle_issue(row, str(e))

        log_action("Batch Processed", f"{processed} rows", f"in agent run", agent="Worker")
        return {"status": "success", "rows_processed": processed}

    except Exception as e:
        log_action("Batch Error", "Critical Failure", str(e), agent="Worker")
        return {"status": "error", "message": str(e)}

def manager_handle_issue(row, error_msg):
    sku = row.get("SKU") or row.get("variantSKU") or "?"
    row_number = row.get("Row")

    try:
        call_gas_function("logManagerThought", {
            "timestamp": datetime.datetime.now().isoformat(),
            "row": row_number,
            "sku": sku,
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
            "sku": sku,
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

        response = openai.ChatCompletion.create(
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
