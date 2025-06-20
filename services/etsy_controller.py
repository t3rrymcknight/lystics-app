
# services/etsy_controller.py
import requests
import datetime

GAS_BASE_URL = GAS_BASE_URL = "https://script.google.com/macros/s/AKfycbxdyW_RnE8LFKrrm1cFE45kia9pdb_5ytzXGdvflZ8C5oHrd-QTYnRKD5OUTW1DKgCd/exec"
LOG_FUNCTION = "logAgentAction"
GET_ROWS_FUNCTION = "getRowsNeedingProcessing"
ADMIN_EMAIL = "support@tmk.digital"

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
        # 1. Fetch rows that need processing
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
                manager_handle_issue(row, str(e))  # pass to manager

        log_action("Batch Processed", f"{processed} rows", f"in agent run", agent="Worker")
        return {
            "status": "success",
            "rows_processed": processed
        }

    except Exception as e:
        log_action("Batch Error", "Critical Failure", str(e), agent="Worker")
        return {
            "status": "error",
            "message": str(e)
        }

# Placeholder for the manager
def manager_handle_issue(row, error_msg):
    # To be implemented: logs to Thinking tab, tries fix, emails if unresolved
    log_action(f"Row {row.get('Row')}", "Escalated", f"Manager needed: {error_msg}", agent="Manager")
