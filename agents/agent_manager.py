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


def assign_unclaimed_jobs(worker_pool, max_rows_per_worker=50):
    from api.api_gateway import call_gas_function, log_action
    import datetime

    try:
        result = call_gas_function("getRowsNeedingProcessing", {
            "job_id": "", "assigned_worker": "", "limit": 200
        })
        print("Raw GAS response:", result)
        log_action("Manager", "Debug", f"Raw GAS response: {result}")
        log_action("Manager", "Debug", f"Raw GAS rows: {result}")
        rows = result.get("rows", [])
        log_action("Manager", "Debug", f"Filtered to {len(rows)} unclaimed rows")
    except Exception as e:
        log_action("Manager", "Error", f"Failed to fetch unclaimed rows: {e}")
        return {}

    load_map = getWorkerLoadMap()
    assignments = {}

    for row in rows:
        row_id = row.get("Row")
        sku = row.get("SKU") or row.get("Title")
        least_loaded = sorted(worker_pool, key=lambda w: load_map.get(w, 0))[0]

        log_action("Manager", "Debug", f"Evaluating row {row_id} — least-loaded: {least_loaded} ({load_map.get(least_loaded, 0)} jobs)")

        if load_map.get(least_loaded, 0) >= max_rows_per_worker:
            log_action("Manager", "Skip", f"Skipped row {row_id} — worker {least_loaded} at cap", agent="Manager")
            continue

        job_id = f"{least_loaded}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{row_id}"

        try:
            call_gas_function("updateRowAssignments", {
                "row": row_id,
                "job_id": job_id,
                "assigned_worker": least_loaded
            })
            assignments[row_id] = least_loaded
            log_action("Manager", "Assignment", f"Assigned row {row_id} to {least_loaded} (Job: {job_id})")
            load_map[least_loaded] = load_map.get(least_loaded, 0) + 1
        except Exception as e:
            log_action("Manager", "Error", f"Failed to assign row {row_id}: {e}")

    return assignments


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

def getWorkerLoadMap():
    from api.api_gateway import call_gas_function
    try:
        result = call_gas_function("getRowsNeedingProcessing", {})
        rows = result.get("rows", [])
    except Exception:
        return {}

    load_map = {}
    for row in rows:
        worker = row.get("Assigned Worker", "").strip()
        if not worker:
            continue
        load_map[worker] = load_map.get(worker, 0) + 1
    return load_map

def runManagerPipeline():
    from api.api_gateway import call_gas_function, log_action
    from agents.agent_manager import diagnose_row
    import datetime

    try:
        result = call_gas_function("getRowsNeedingProcessing", {})
        rows = result.get("rows", [])
    except Exception as e:
        log_action("Manager", "Error", f"Failed to load rows for pipeline: {e}")
        return

    now = datetime.datetime.utcnow()
    for row in rows:
        row_id = row.get("Row")
        workflow_type = row.get("Workflow Type")
        bot_status = row.get("Bot Status", "")
        last_attempted = row.get("Last Attempted")
        status = row.get("Status")

        # Parse ISO timestamp
        try:
            last_dt = datetime.datetime.fromisoformat(last_attempted)
        except Exception:
            last_dt = None

        minutes_old = (now - last_dt).total_seconds() / 60 if last_dt else None
        stale = bot_status == "Processing" and minutes_old and minutes_old > 15

        if stale:
            log_action(f"Row {row_id}", "Escalated", f"Stuck for {int(minutes_old)} mins", agent="Manager")
            call_gas_function("updateRowStatus", {
                "row": row_id,
                "new_status": status
            })
            call_gas_function("updateRowNotes", {
                "row": row_id,
                "notes": f"⚠️ Auto-escalated after {int(minutes_old)} min idle"
            })
            call_gas_function("sendEscalationEmail", {
                "row": row_id,
                "sku": row.get("SKU", "Unknown"),
                "status": status,
                "error": "Worker stuck",
                "suggestion": "Supervisor intervention needed"
            })
        else:
            diagnosis = diagnose_row(row)

        # Log task priority if available
        try:
            from agents.workflow_config import workflow_steps_with_priority
            priority_step = next((s for s in workflow_steps_with_priority.get(workflow_type, []) if s['step'] == status), None)
            if priority_step and priority_step['priority'] == 'high':
                log_action(f"Row {row_id}", "High Priority", f"Step: {status}", agent="Manager")
        except Exception:
            pass

        # Step index enforcement
        try:
            index = int(call_gas_function("getStepIndex", {"row": row_id}).get("step", 0))
            current_steps = workflow_steps.get(workflow_type, [])
            if index < len(current_steps):
                expected_status = current_steps[index]
                if status != expected_status:
                    log_action(f"Row {row_id}", "Corrected", f"Reset to valid step: {expected_status}")
                    call_gas_function("updateRowStatus", {"row": row_id, "new_status": expected_status})
                    call_gas_function("updateStepIndex", {"row": row_id, "index": index})
        except Exception as e:
            log_action(f"Row {row_id}", "Step Index Check Failed", str(e))
        errors = getProgressErrorCount(row_id)
        if errors >= 3:
            log_action(f"Row {row_id}", "Escalated", f"{status} failed 3 times", agent="Manager")
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": status})
            call_gas_function("sendEscalationEmail", {
                "row": row_id,
                "sku": row.get("SKU", "Unknown"),
                "status": status,
                "error": "Too many failures",
                "suggestion": "Supervisor intervention required"
            })
        else:
            next_status = determine_next_status(workflow_type, status)
            if next_status:
                call_gas_function("updateRowStatus", {"row": row_id, "new_status": next_status})
                log_action(f"Row {row_id}", "Auto-Advanced", f"Moved to next step: {next_status}")
            else:
                log_action(f"Row {row_id}", "Stuck", f"No next step found", agent="Manager")
            if diagnosis["issues"]:
                log_action(f"Row {row_id}", "Diagnosis", diagnosis["likely_cause"], agent="Manager")

    log_action("Manager", "Pipeline", "Completed runManagerPipeline")


def determine_next_status(workflow_type, current_status):
    from agents.workflow_config import workflow_steps
    steps = workflow_steps.get(workflow_type, [])
    if current_status in steps:
        i = steps.index(current_status)
        return steps[i + 1] if i + 1 < len(steps) else None
    return steps[0] if steps else None

def incrementProgressErrorCount(row_number):
    from api.api_gateway import call_gas_function
    call_gas_function("incrementProgressErrorCount", {"row": row_number})

def getProgressErrorCount(row_number):
    from api.api_gateway import call_gas_function
    return call_gas_function("getProgressErrorCount", {"row": row_number}).get("count", 0)

def run_batch_rows():
    """
    New manager trigger to process rows using the worker controller.
    Also logs results and handles archive or escalation logic.
    """
    from api.api_gateway import call_gas_function, log_action
    from worker_controller import run_worker_for_row
    from queue_gas_call import queue_gas_call
    import datetime

    try:
        result = call_gas_function("getRowsNeedingProcessing", {})
        rows = result.get("rows", [])
    except Exception as e:
        log_action("Manager", "Error", f"Failed to fetch rows: {e}")
        return

    now = datetime.datetime.utcnow()
    processed = 0

    for row in rows:
        try:
            row_id = row.get("Row")
            job_id = row.get("Job ID")
            status = row.get("Status")
            log_action(f"Row {row_id}", "Dispatched", f"Status: {status}")

            run_worker_for_row(row)
            processed += 1

            queue_gas_call("writeToLog", {
                "job_id": job_id,
                "message": f"✅ Worker processed: {status}",
                "level": "info"
            })

            if status == "Completed":
                queue_gas_call("archiveRow", {"row": row_id})

        except Exception as e:
            log_action(f"Row {row.get('Row')}", "Error", str(e), agent="Manager")
            queue_gas_call("updateRowError", {
                "row": row.get("Row"),
                "error_message": str(e)
            })

    log_action("Manager", "BatchRun", f"✔️ Finished batch: {processed} rows processed")

