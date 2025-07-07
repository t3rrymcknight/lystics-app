import requests
import datetime
import json
import os
from collections import defaultdict

# ------------------------------- #
#  Google Apps Script Endpoints   #
# ------------------------------- #
GAS_BASE_URL      = (
    os.getenv("LYSTICS_GAS_BASE_URL")
    or "https://script.google.com/macros/s/AKfycbzLXrJ-DTfLF3MD1aPUBTk1na3kcDfZ5sREppGIuRot500eqRM_7S72kpjZzNl2vLnq/exec"
)
LOG_FUNCTION      = "logAgentAction"
GET_ROWS_FUNCTION = "getRowsNeedingProcessing"
MAX_ROWS_PER_RUN  = 20
COOLDOWN_MINUTES  = 1

# ------------------------------- #
#        Helper Functions         #
# ------------------------------- #

def call_gas_function(function_name: str, params: dict | None = None, timeout: int = 30):
    """POST JSON → Apps‑Script web‑app and return decoded payload.

    The body always contains a `function` key so `doPost` can route, even when
    additional params are empty/None.
    """
    payload: dict = {"function": function_name}
    if params:
        payload.update(params)

    print("\n========== GAS CALL DEBUG ==========")
    print("-> Function:", function_name)
    print("-> URL:", GAS_BASE_URL)
    print("-> Payload:", json.dumps(payload))

    try:
        resp = requests.post(GAS_BASE_URL, json=payload, timeout=timeout)
        print("-> Status code:", resp.status_code)
        print("-> Raw response:", resp.text)

        # raise for HTTP‑level failures first
        resp.raise_for_status()

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{function_name} returned non‑JSON: {resp.text}") from exc

        print("-> Decoded JSON:", json.dumps(data, indent=2))

        if not data.get("success", False):
            raise RuntimeError(f"{function_name} error: {data.get('error', 'Unknown error')}")

        return data.get("result", data)  # Some endpoints wrap in .result
    except requests.RequestException as exc:
        raise RuntimeError(f"{function_name} HTTP error: {exc}") from exc


def log_action(action: str, outcome: str, notes: str, *, agent: str = "Worker") -> None:
    params = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "outcome": outcome,
        "notes": notes,
        "agent": agent,
    }
    try:
        call_gas_function(LOG_FUNCTION, params)
    except Exception as exc:  # noqa: BLE001
        print("⚠️  Failed to log action:", exc)

# ------------------------------- #
#           Main Runner           #
# ------------------------------- #

def run_etsy_agent():
    """Entry‑point for Cloud‑Run container / cron trigger."""

    # ----- Concurrency guard -----
    if call_gas_function("isWorkerActive").get("active"):
        log_action("Batch Skipped", "Worker already active", "")
        return {"status": "skipped", "message": "Worker already running"}

    call_gas_function("markWorkerActive")
    log_action("Batch Start", "Initiated", "", agent="Worker")

    summary_logs: list[str] = []
    processed = 0
    now = datetime.datetime.now()

    try:
        response_json = call_gas_function(GET_ROWS_FUNCTION, {"limit": MAX_ROWS_PER_RUN})
        print("🧪 Raw GAS Response:", json.dumps(response_json, indent=2))

        rows: list[dict] = response_json.get("rows", [])
        print(f"📦 Fetched {len(rows)} rows for processing")

        grouped_rows: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            grouped_rows[str(row.get("status", "")).strip()].append(row)

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
            "Create PDF": "processCreatePDF",
        }

        for status, group in grouped_rows.items():
            if processed >= MAX_ROWS_PER_RUN:
                break

            fn_name = fn_map.get(status)
            if not fn_name:
                # Skip Pending / blank / unknown statuses
                for row in group:
                    log_action(f"Row {row['row']}", "Skipped", f"Status not actionable: {status}")
                continue

            print(
                f"📤 Triggering GAS function: {fn_name} for status group '{status}' ({len(group)} rows)"
            )

            try:
                response = call_gas_function(fn_name)
                if not isinstance(response, dict) or response.get("error"):
                    raise RuntimeError(response.get("error", "Unknown"))

                for row in group:
                    row_number = row.get("row")
                    call_gas_function(
                        "updateLastAttempted",
                        {"row": row_number, "timestamp": now.isoformat()},
                    )
                    call_gas_function("updateRowProgress", {"row": row_number, "progress": "Processing"})
                    log_action(
                        f"Row {row_number}",
                        "Success",
                        f"{status} succeeded via batch call",
                    )
                    summary_logs.append(f"✅ Row {row_number} succeeded for status: {status}")
                    processed += 1
                    if processed >= MAX_ROWS_PER_RUN:
                        break
            except Exception as exc:  # noqa: BLE001
                for row in group:
                    row_number = row.get("row")
                    err_msg = f"❌ Row {row_number} error during batch call: {exc}"
                    log_action(f"Row {row_number}", "Error", err_msg)
                    summary_logs.append(err_msg)
                    manager_handle_issue(row, str(exc))
                    if processed >= MAX_ROWS_PER_RUN:
                        break

        result: dict = {
            "status": "success",
            "rows_processed": processed,
        }
        log_action("Batch Processed", f"{processed} rows", "End of run", agent="Worker")

    except Exception as exc:  # noqa: BLE001
        summary_logs.append(f"🔥 Critical error: {exc}")
        result = {"status": "error", "message": str(exc)}
        log_action("Batch Error", "Critical Failure", str(exc), agent="Worker")

    finally:
        handle_post_run_summary(summary_logs, result)

        if any(tag in log for log in summary_logs for tag in ("❌", "🔥", "error")):
            call_gas_function(
                "sendAgentSummaryEmail",
                {
                    "status": result.get("status"),
                    "logs": summary_logs,
                    "summary": f"{processed} rows processed by Worker at {now:%Y-%m-%d %H:%M}",
                },
            )

        # Fire Manager‑side agents after this batch
        safe_trigger("runMissingDataAdvisor")
        safe_trigger("runManagerPipeline")

    return result


# ------------------------------- #
#     Helper / escalation LO      #
# ------------------------------- #

def safe_trigger(fn_name: str):
    try:
        call_gas_function(fn_name)
        log_action("Manager Agent", "Invoked", f"Triggered {fn_name} after batch", agent="Worker")
    except Exception as exc:  # noqa: BLE001
        log_action("Manager Agent", "Error", f"Failed to trigger {fn_name}: {exc}", agent="Worker")


def manager_handle_issue(row: dict, error_msg: str):
    row_number = row.get("row")

    # 1) Log thinking / increment error count
    try:
        call_gas_function(
            "logManagerThought",
            {
                "timestamp": datetime.datetime.now().isoformat(),
                "row": row_number,
                "sku": "Unknown",  # minimal row object no longer contains Title
                "thought": f"Investigating error: {error_msg}",
                "confidence": "0.70",
            },
        )
        call_gas_function("incrementProgressErrorCount", {"row": row_number})
    except Exception as exc:  # noqa: BLE001
        print("⚠️  Failed to log to Thinking tab:", exc)

    # 2) Determine retry / escalation threshold
    try:
        error_count = call_gas_function("getProgressErrorCount", {"row": row_number}).get("count", 0)
    except Exception:
        error_count = 0

    reason = (
        f"Auto-reset after {error_count} failed attempts" if error_count >= 3 else error_msg
    )

    # 3) Attempt automatic reset if threshold reached
    if error_count >= 3:
        try:
            call_gas_function(
                "updateRowStatus",
                {"row": row_number, "new_status": row.get("status")},
            )
            call_gas_function("clearThinkingTab")
            log_action(f"Row {row_number}", "Resolved", reason, agent="Manager")
            return
        except Exception as exc:  # noqa: BLE001
            error_msg = f"Failed to reset status: {exc}"

    # 4) Escalate to Supervisor
    call_gas_function("clearThinkingTab")
    log_action(f"Row {row_number}", "Escalated", reason, agent="Manager")

    try:
        call_gas_function(
            "sendEscalationEmail",
            {
                "row": row_number,
                "sku": "Unknown",
                "status": row.get("status"),
                "error": error_msg,
                "suggestion": reason,
            },
        )
    except Exception as exc:  # noqa: BLE001
        print("⚠️  Failed to send escalation email:", exc)


# ------------------------------- #
#      Post‑run summary helper    #
# ------------------------------- #

def handle_post_run_summary(logs: list[str], result: dict):
    """Placeholder for any follow‑up summarisation (Slack, BigQuery, etc.)."""
    print("\n===== BATCH SUMMARY =====")
    for line in logs:
        print(line)
    print("Result:", result)
