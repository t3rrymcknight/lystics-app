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
