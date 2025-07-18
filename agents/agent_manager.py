import datetime
import json
from api.api_gateway import call_gas_function, log_action
from agents.workflow_config import workflow_steps
from agents.task_map import fn_map
from agents.queue_gas_call import queue_gas_call

def assign_unclaimed_jobs(unassigned_rows, worker_pool, load_map, max_rows_per_worker=50):
    """
    Assigns jobs from a provided list of unassigned rows.
    """
    assignments = {}
    log_action("Manager", "Assignment", f"Attempting to assign {len(unassigned_rows)} unclaimed jobs.", agent="Manager")

    for row in unassigned_rows:
        row_id = row.get("Row")
        least_loaded_worker = sorted(worker_pool, key=lambda w: load_map.get(w, 0))[0]

        if load_map.get(least_loaded_worker, 0) >= max_rows_per_worker:
            continue

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

        error_count = getProgressErrorCount(row_id)
        if error_count >= 3:
            reason = f"Task '{status}' failed {error_count} times."
            call_gas_function("updateRowStatus", {"row": row_id, "new_status": "Supervisor"})


def runManagerPipeline():
    """
    The main orchestration function. Fetches data once, then processes it.
    """
    log_action("Manager", "Pipeline Start", "Fetching all actionable rows.", agent="Manager")
    
    try:
        result = call_gas_function("getRowsNeedingProcessing", {})
        log_action("Manager", "Data Received", f"Received {len(result.get('rows', []))} rows from GAS.", agent="Manager")
        if result.get('rows'):
            log_action("Manager", "Data Sample", json.dumps(result['rows'][0], indent=2), agent="Manager")

        all_rows = result.get("rows", [])
        if not all_rows:
            log_action("Manager", "Pipeline Info", "No actionable rows found in the sheet.", agent="Manager")
            return
    except Exception as e:
        log_action("Manager", "Pipeline Error", f"Could not fetch rows: {e}", agent="Manager")
        return

    worker_pool = ["worker1", "worker2"]
    unassigned_rows = [r for r in all_rows if not r.get("Assigned Worker", "").strip()]
    
    load_map = {}
    for r in all_rows:
        worker = r.get("Assigned Worker", "").strip()
        if worker:
            load_map[worker] = load_map.get(worker, 0) + 1

    assign_unclaimed_jobs(unassigned_rows, worker_pool, load_map)
    
    # We must refetch data after assignments to ensure workers get the new jobs
    try:
        result = call_gas_function("getRowsNeedingProcessing", {})
        all_rows_after_assign = result.get("rows", [])
    except Exception as e:
        log_action("Manager", "Pipeline Error", f"Could not refetch rows after assignment: {e}", agent="Manager")
        return

    for worker_id in worker_pool:
        jobs_for_worker = [r for r in all_rows_after_assign if r.get("Assigned Worker") == worker_id]
        if jobs_for_worker:
            run_worker_on_assigned_jobs(worker_id, jobs_for_worker)

    run_diagnostics(all_rows_after_assign)

    log_action("Manager", "Pipeline Complete", "Full processing cycle finished.", agent="Manager")

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
