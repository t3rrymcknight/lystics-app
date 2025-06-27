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
