import requests
import datetime
import os
import json

# ------------------------------- #
#  Google Apps Script Endpoints   #
# ------------------------------- #
GAS_BASE_URL        = "https://script.google.com/macros/s/AKfycbxPFzs5AVCAqqEs3Xr4REe0GPZdcBmAoaZ5xCtGmvAdQ51FWNsU9cbZ7pnlsqJb1Nwz/exec"
LOG_FUNCTION        = "logAgentAction"
GET_ROWS_FUNCTION   = "getRowsNeedingProcessing"
MAX_ROWS_PER_RUN    = 20
COOLDOWN_MINUTES    = 1

# ------------------------------- #
#        Helper Functions         #
# ------------------------------- #
def call_gas_function(function_name, params=None, timeout=30):
    if params is None:
        params = {}
    url = f"{GAS_BASE_URL}?function={function_name}"

    try:
        response = requests.post(url, json=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if not data.get("success", False):
            raise Exception(f"{function_name} error: {data.get('error', 'Unknown error')}")
        return data.get("result", {})
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
        response_json = call_gas_function(GET_ROWS_FUNCTION)
        print("🧪 Raw GAS Response:", json.dumps(response_json, indent=2))

        rows = response_json.get("rows", [])
        print(f"📦 Fetched {len(rows)} rows for processing")

        from collections import defaultdict
        grouped_rows = defaultdict(list)
        for row in rows:
            grouped_rows[str(row.get("Status") or "").strip()].append(row)

        fn_map = {
            "Download Image": "downloadImagesToDrive",
            "Create Thumbnail": "copyResizeImageAndStoreUrl",
            "Describe Image": "processImagesWithOpenAI",
            "Add Mockups": "updateImagesFromMockupFolders",
            "Upscale Image": "copyUpscaleImageAndStoreVariants",
            "Generate Mockup JSON": "generateMockupJson",
            "Upload Files": "uploadDigitalFiles",
            "Upload Images": "uploadImageAssets",
            "Vectorize": "vectorizeSourceSvg",
            "Create Description": "findReplaceInDescription",
            "Create Folder": "processCreateFolders",
            "Rename Files": "updateFileNamesWithImageName",
            "Move Files": "moveFilesAndImagesToFolder",
            "Generate Mockups": "generateMockupsFromDrive",
            "Create JSON": "buildMockupJsonFromFolderStructure",
            "Create PDF": "processCreatePDF"
        }

        for status, group in grouped_rows.items():
            if processed >= MAX_ROWS_PER_RUN:
                break

            fn_name = fn_map.get(status)
            if not fn_name:
                for row in group:
                    log_action(f"Row {row['Row']}", "Skipped", f"Status not actionable: {status}")
                continue

            try:
                print(f"📤 Triggering GAS function: {fn_name} for status group '{status}' ({len(group)} rows)")
                response = call_gas_function(fn_name)

                if response is None:
                    raise Exception(f"Function {status} failed to return any response.")
                if not isinstance(response, dict) or response.get("error"):
                    raise Exception(f"Function {status} returned error: {response.get('error', 'Unknown')}")

                for row in group:
                    row_number = row.get("Row")
                    call_gas_function("updateLastAttempted", {
                        "row": row_number,
                        "timestamp": now.isoformat()
                    })
                    call_gas_function("updateRowProgress", {"row": row_number, "progress": "Processing"})
                    log_action(f"Row {row_number}", "Success", f"{status} succeeded via batch call")
                    summary_logs.append(f"✅ Row {row_number} succeeded for status: {status}")
                    processed += 1
                    if processed >= MAX_ROWS_PER_RUN:
                        break

            except Exception as e:
                for row in group:
                    row_number = row.get("Row")
                    err_msg = f"❌ Row {row_number} error during batch call: {e}"
                    log_action(f"Row {row_number}", "Error", err_msg)
                    summary_logs.append(err_msg)
                    manager_handle_issue(row, str(e))
                    if processed >= MAX_ROWS_PER_RUN:
                        break

        result = {"status": "success", "rows_processed": processed, "response": response}
        log_action("Batch Processed", f"{processed} rows", "End of run", agent="Worker")

    except Exception as e:
        summary_logs.append(f"🔥 Critical error: {e}")
        result = {"status": "error", "message": str(e)}
        log_action("Batch Error", "Critical Failure", str(e), agent="Worker")

    finally:
        call_gas_function("markWorkerInactive")

        if any("❌" in log or "error" in log.lower() or "🔥" in log for log in summary_logs):
            call_gas_function("sendAgentSummaryEmail", {
                "status": result.get("status"),
                "logs":   summary_logs,
                "summary": f"{processed} rows processed by Worker at "
                           f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
            })

        try:
            call_gas_function("runMissingDataAdvisor")
            log_action("Manager Agent", "Invoked", "Triggered after batch run", agent="Worker")
        except Exception as e:
            log_action("Manager Agent", "Error", f"Failed to trigger runMissingDataAdvisor: {e}", agent="Worker")

        try:
            call_gas_function("runManagerPipeline")
            log_action("Manager Agent", "Invoked", "Triggered runManagerPipeline after batch", agent="Worker")
        except Exception as e:
            log_action("Manager Agent", "Error", f"Failed to trigger runManagerPipeline: {e}", agent="Worker")

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
