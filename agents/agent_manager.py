import datetime
from api.api_gateway import call_gas_function, log_action
from agents.workflow_config import workflow_steps
from agents.task_map import fn_map

def assign_unclaimed_jobs(worker_pool, max_rows_per_worker=50):
    """
    Assigns jobs that have no worker to the least loaded worker in the pool.
    """
    try:
        # Correctly filter for unassigned workers
        result = call_gas_function("getRowsNeedingProcessing", {
            "assigned_worker": "", "limit": 200
        })
        rows = result.get("rows", [])
        if not rows:
            log_action("Manager", "Assignment", "No unclaimed jobs found to assign.", agent="Manager")
            return {}
        log_action("Manager", "Debug", f"Found {len(rows)} unclaimed rows to assign.", agent="Manager")
    except Exception as e:
        log_action("Manager", "Error", f"Failed to fetch unclaimed rows: {e}", agent="Manager")
        return {}

    load_map = getWorkerLoadMap()
    assignments = {}

    for row in rows:
        row_id = row.get("Row")
        least_loaded_worker = sorted(worker_pool, key=lambda w: load_map.get(w, 0))[0]

        if load_map.get(least_loaded_worker, 0) >= max_rows_per_worker:
            log_action("Manager", "Skip", f"Skipped row {row_id} — worker {least_loaded_worker} is at capacity.", agent="Manager")
            continue

        job_id = f"{least_loaded_worker}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{row_id}"

        try:
            call_gas_function("updateRowAssignments", {
                "row": row_id,
                "job_id": job_id,
                "assigned_worker": least_loaded_worker
            })
            assignments[row_id] = least_loaded_worker
            log_action("Manager", "Assignment", f"Assigned row {row_id} to {least_loaded_worker} (Job: {job_id})", agent="Manager")
            load_map[least_loaded_worker] = load_map.get(least_loaded_worker, 0) + 1
        except Exception as e:
            log_action("Manager", "Error", f"Failed to assign row {row_id}: {e}", agent="Manager")

    return assignments

def run_worker_on_assigned_jobs(worker_id):
    """
    Fetches and executes all tasks assigned to a specific worker.
    """
    log_action(f"Worker {worker_id}", "Start Run", "Fetching assigned jobs.", agent=worker_id)
    try:
        result = call_gas_function("getRowsNeedingProcessing", {"assigned_worker": worker_id})
        rows = result.get("rows", [])
        if not rows:
            log_action(f"Worker {worker_id}", "Stop Run", "No assigned jobs found.", agent=worker_id)
            return
    except Exception as e:
        log_action(f"Worker {worker_id}", "Error", f"Could not fetch jobs: {e}", agent=worker_id)
        return

    for row in rows:
        status = row.get("Status")
        row_id = row.get("Row")
        task_function_name = fn_map.get(status)

        if not task_function_name:
            log_action(f"Row {row_id}", "Skipped", f"No function mapped for status: {status}", agent=worker_id)
            continue

        try:
            log_action(f"Row {row_id}", "Processing", f"Executing task: {status}", agent=worker_id)
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": f"Processing: {status}"})
            call_gas_function(task_function_name, {"row": row_id})
            
            next_status = determine_next_status(row.get("Workflow Type"), status)
            final_status = next_status if next_status else "Completed"
            
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": final_status})
            log_action(f"Row {row_id}", "Success", f"Task '{status}' completed. New status: {final_status}", agent=worker_id)

        except Exception as e:
            log_action(f"Row {row_id}", "Error", f"Task '{status}' failed: {e}", agent=worker_id)
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": status}) # Revert status on failure
            incrementProgressErrorCount(row_id)

def run_all_workers(worker_pool):
    """
    Triggers a run for every worker in the provided pool.
    """
    log_action("Manager", "Trigger Workers", f"Starting runs for workers: {', '.join(worker_pool)}", agent="Manager")
    for worker_id in worker_pool:
        run_worker_on_assigned_jobs(worker_id)

def runManagerPipeline():
    """
    The main orchestration function. Assigns jobs, runs workers, and runs diagnostics.
    """
    worker_pool = ["worker1", "worker2"]
    log_action("Manager", "Pipeline Start", "Assigning jobs and triggering workers.", agent="Manager")
    
    # Step 1: Assign any unclaimed jobs
    assign_unclaimed_jobs(worker_pool)
    
    # Step 2: Run all workers to process their queues
    run_all_workers(worker_pool)
    
    # Step 3: Run diagnostics on the current state of all rows
    run_diagnostics()

    log_action("Manager", "Pipeline Complete", "Full processing cycle finished.", agent="Manager")

def run_diagnostics():
    """
    Runs the diagnostic and state management pipeline for all active rows.
    This function checks for stale jobs, corrects statuses, and escalates issues.
    """
    log_action("Manager", "Diagnostics Start", "Running manager diagnostic checks.", agent="Manager")
    try:
        # Get all actionable rows, regardless of worker
        result = call_gas_function("getRowsNeedingProcessing", {})
        rows = result.get("rows", [])
    except Exception as e:
        log_action("Manager", "Error", f"Failed to load rows for diagnostics: {e}", agent="Manager")
        return

    now = datetime.datetime.utcnow()
    for row in rows:
        row_id = row.get("Row")
        status = row.get("Status")
        last_attempted = row.get("Last Attempted")

        # Check for stale jobs
        if status.startswith("Processing:"):
            try:
                last_dt = datetime.datetime.fromisoformat(last_attempted) if last_attempted else None
                minutes_old = (now - last_dt).total_seconds() / 60 if last_dt else -1
                if minutes_old > 15:
                    reason = f"⚠️ Auto-escalated: Stuck in '{status}' for {int(minutes_old)} mins."
                    original_status = status.replace("Processing: ", "")
                    log_action(f"Row {row_id}", "Escalated", reason, agent="Manager")
                    call_gas_function("updateRowStatus", {"row": row_id, "new_status": original_status})
                    call_gas_function("updateRowNotes", {"row": row_id, "notes": reason})
            except (ValueError, TypeError):
                continue # Ignore if timestamp is invalid

        # Check for repeated failures
        error_count = getProgressErrorCount(row_id)
        if error_count >= 3:
            reason = f"Task '{status}' failed {error_count} times. Needs manual review."
            log_action(f"Row {row_id}", "Escalated", reason, agent="Manager")
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": "Supervisor"})
            call_gas_function("sendEscalationEmail", {
                "row": row_id, "sku": row.get("SKU", "Unknown"), "status": status,
                "error": reason, "suggestion": "Supervisor intervention required."
            })

    log_action("Manager", "Diagnostics Complete", "Finished manager diagnostic checks.", agent="Manager")


def getWorkerLoadMap():
    """
    Gets a map of how many active jobs each worker is assigned.
    """
    try:
        result = call_gas_function("getRowsNeedingProcessing", {})
        rows = result.get("rows", [])
    except Exception:
        return {}

    load_map = {}
    for row in rows:
        worker = row.get("Assigned Worker", "").strip()
        if worker:
            load_map[worker] = load_map.get(worker, 0) + 1
    return load_map

def determine_next_status(workflow_type, current_status):
    """
    Determines the next status in a workflow.
    """
    steps = workflow_steps.get(workflow_type, [])
    try:
        clean_status = current_status.replace("Processing: ", "")
        current_index = steps.index(clean_status)
        return steps[current_index + 1] if current_index + 1 < len(steps) else None
    except (ValueError, IndexError):
        return steps[0] if steps else None

def incrementProgressErrorCount(row_number):
    """
    Increments the error count for a specific row in the sheet.
    """
    call_gas_function("incrementProgressErrorCount", {"row": row_number})

def getProgressErrorCount(row_number):
    """
    Retrieves the current error count for a specific row.
    """
    try:
        return call_gas_function("getProgressErrorCount", {"row": row_number}).get("count", 0)
    except Exception:
        return 0
