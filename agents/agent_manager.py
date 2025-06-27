


def handle_post_run_summary(summary_logs, result):
    import datetime
    from api.api_gateway import call_gas_function, log_action

    # Final cleanup
    call_gas_function("markWorkerInactive")

    if any("❌" in log or "error" in log.lower() or "🔥" in log for log in summary_logs):
        call_gas_function("sendAgentSummaryEmail", {
            "status": result.get("status"),
            "logs": summary_logs,
            "summary": f"{result.get('rows_processed', 0)} rows processed by Worker at "
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


def assign_unclaimed_jobs(worker_pool):
    """
    Assigns unclaimed rows to available workers using round-robin strategy.
    """
    from api.api_gateway import call_gas_function, log_action
    import datetime

    try:
        result = call_gas_function("getRowsNeedingProcessing", {
            "job_id": "", "assigned_worker": "", "limit": 50
        })
        rows = result.get("rows", [])
    except Exception as e:
        log_action("Manager", "Error", f"Failed to fetch unclaimed rows: {e}")
        return

    assignments = {}
    worker_index = 0

    for row in rows:
        row_id = row.get("Row")
        sku = row.get("SKU") or row.get("Title")
        assigned_worker = worker_pool[worker_index % len(worker_pool)]
        job_id = f"{assigned_worker}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{row_id}"

        try:
            call_gas_function("updateRowAssignments", {
                "row": row_id,
                "job_id": job_id,
                "assigned_worker": assigned_worker
            })
            assignments[row_id] = assigned_worker
            log_action("Manager", "Assignment", f"Assigned row {row_id} to {assigned_worker} (Job: {job_id})")
            worker_index += 1
        except Exception as e:
            log_action("Manager", "Error", f"Failed to assign row {row_id}: {e}")

    return assignments

from agents.workflow_config import workflow_steps


from agents.workflow_config import workflow_steps

def diagnose_row(row):
    """
    Returns a dictionary explaining the row's current issues or progress blockers.
    """
    result = {
        "row": row.get("Row"),
        "status": row.get("Status"),
        "workflow_type": row.get("Workflow Type"),
        "bot_status": row.get("Bot Status"),
        "last_attempted": row.get("Last Attempted"),
        "issues": [],
        "likely_cause": ""
    }

    steps_required = workflow_steps.get(result["workflow_type"], [])
    current_status = result["status"]

    if not steps_required:
        result["issues"].append("Unknown workflow type")
        result["likely_cause"] = "Workflow type not defined"
        return result

    if current_status not in steps_required:
        result["issues"].append("Status not valid for this workflow type")
        result["likely_cause"] = "Incorrect or outdated status"
        return result

    # Check if essential fields are missing
    if current_status == "Create PDF" and not row.get("Drive URL"):
        result["issues"].append("Missing Drive URL for source image")
        result["likely_cause"] = "Cannot create PDF without image"
    elif current_status == "Upload Files" and not row.get("Mockups Folder ID") and not row.get("Folder ID"):
        result["issues"].append("Missing folder ID")
        result["likely_cause"] = "No output folder to upload to"

    return result
