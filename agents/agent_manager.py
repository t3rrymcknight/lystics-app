import datetime
from api.api_gateway import call_gas_function, log_action
from agents.workflow_config import workflow_steps
from agents.task_map import fn_map
from agents.queue_gas_call import queue_gas_call

def assign_unclaimed_jobs(unassigned_rows, worker_pool, load_map, max_rows_per_worker=50):
    """
    Assigns jobs from a provided list of unassigned rows.
    This no longer fetches its own data, making it much faster.
    """
    assignments = {}
    log_action("Manager", "Assignment", f"Attempting to assign {len(unassigned_rows)} unclaimed jobs.", agent="Manager")

    for row in unassigned_rows:
        row_id = row.get("Row")
        least_loaded_worker = sorted(worker_pool, key=lambda w: load_map.get(w, 0))[0]

        if load_map.get(least_loaded_worker, 0) >= max_rows_per_worker:
            continue # Skip if all workers are at capacity

        job_id = f"{least_loaded_worker}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{row_id}"

        try:
            queue_gas_call(
                "updateRowAssignments",
                lambda _: call_gas_function("updateRowAssignments", {
                    "row": row_id,
                    "job_id": job_id,
                    "assigned_worker": least_loaded_worker
                })
            )
            assignments[row_id] = least_loaded_worker
            log_action("Manager", "Assignment", f"Assigned row {row_id} to {least_loaded_worker}", agent="Manager")
            load_map[least_loaded_worker] = load_map.get(least_loaded_worker, 0) + 1
        except Exception as e:
            log_action("Manager", "Error", f"Failed to assign row {row_id}: {e}", agent="Manager")

    return assignments

def run_worker_on_assigned_jobs(worker_id, assigned_rows):
    """
    Processes a provided list of rows for a specific worker.
    """
    log_action(f"Worker {worker_id}", "Start Run", f"Processing {len(assigned_rows)} assigned jobs.", agent=worker_id)
    
    for row in assigned_rows:
        status = row.get("Status")
        row_id = row.get("Row")
        task_function_name = fn_map.get(status)

        if not task_function_name:
            continue

        try:
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": f"Processing: {status}"})
            
            q_result = queue_gas_call(
                task_function_name,
                lambda _: call_gas_function(task_function_name, {"row": row_id})
            )

            if q_result.get("status") != "ok":
                 raise Exception(q_result.get("error", "Unknown error from queue"))

            next_status = determine_next_status(row.get("Workflow Type"), status)
            final_status = next_status if next_status else "Completed"
            
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": final_status})
            log_action(f"Row {row_id}", "Success", f"Task '{status}' completed. New status: {final_status}", agent=worker_id)

        except Exception as e:
            log_action(f"Row {row_id}", "Error", f"Task '{status}' failed: {e}", agent=worker_id)
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": status})
            incrementProgressErrorCount(row_id)

def run_diagnostics(all_rows):
    """
    Runs diagnostic checks on a provided list of all actionable rows.
    """
    log_action("Manager", "Diagnostics Start", f"Running checks on {len(all_rows)} rows.", agent="Manager")
    now = datetime.datetime.utcnow()
    for row in all_rows:
        row_id = row.get("Row")
        status = row.get("Status")
        
        # Check for stale jobs
        if status.startswith("Processing:"):
            last_attempted = row.get("Last Attempted")
            try:
                last_dt = datetime.datetime.fromisoformat(last_attempted) if last_attempted else None
                if last_dt and (now - last_dt).total_seconds() > 900: # 15 minutes
                    reason = f"⚠️ Auto-escalated: Stuck for >15 mins."
                    original_status = status.replace("Processing: ", "")
                    call_gas_function("updateRowStatus", {"row": row_id, "new_status": original_status})
            except (ValueError, TypeError):
                continue

        # Check for repeated failures
        error_count = getProgressErrorCount(row_id)
        if error_count >= 3:
            reason = f"Task '{status}' failed {error_count} times."
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": "Supervisor"})


def runManagerPipeline():
    """
    The main orchestration function. Fetches data once, then processes it.
    """
    log_action("Manager", "Pipeline Start", "Fetching all actionable rows.", agent="Manager")
    
    # --- Step 1: Fetch all actionable data ONCE ---
    try:
        result = call_gas_function("getRowsNeedingProcessing", {})
        all_rows = result.get("rows", [])
        if not all_rows:
            log_action("Manager", "Pipeline Info", "No actionable rows found in the sheet.", agent="Manager")
            return
    except Exception as e:
        log_action("Manager", "Pipeline Error", f"Could not fetch rows: {e}", agent="Manager")
        return

    # --- Step 2: Process the data in memory ---
    worker_pool = ["worker1", "worker2"]
    unassigned_rows = [r for r in all_rows if not r.get("Assigned Worker", "").strip()]
    
    # Create a load map from the fetched data
    load_map = {}
    for r in all_rows:
        worker = r.get("Assigned Worker", "").strip()
        if worker:
            load_map[worker] = load_map.get(worker, 0) + 1

    # Step 2a: Assign jobs
    assign_unclaimed_jobs(unassigned_rows, worker_pool, load_map)

    # Step 2b: Run workers on their assigned jobs
    for worker_id in worker_pool:
        jobs_for_worker = [r for r in all_rows if r.get("Assigned Worker") == worker_id]
        if jobs_for_worker:
            run_worker_on_assigned_jobs(worker_id, jobs_for_worker)

    # Step 2c: Run diagnostics on the initial state
    run_diagnostics(all_rows)

    log_action("Manager", "Pipeline Complete", "Full processing cycle finished.", agent="Manager")


def getWorkerLoadMap():
    # This is now a helper and doesn't call the API
    return {}

def determine_next_status(workflow_type, current_status):
    steps = workflow_steps.get(workflow_type, [])
    try:
        clean_status = current_status.replace("Processing: ", "")
        current_index = steps.index(clean_status)
        return steps[current_index + 1] if current_index + 1 < len(steps) else None
    except (ValueError, IndexError):
        return steps[0] if steps else None

def incrementProgressErrorCount(row_number):
    call_gas_function("incrementProgressErrorCount", {"row": row_number})

def getProgressErrorCount(row_number):
    try:
        return call_gas_function("getProgressErrorCount", {"row": row_number}).get("count", 0)
    except Exception:
        return 0
