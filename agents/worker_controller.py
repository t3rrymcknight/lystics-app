
from flask import Blueprint, jsonify
from agents.agent_manager import assign_unclaimed_jobs, runManagerPipeline
from api.api_gateway import log_action

etsy_bp = Blueprint('etsy_bp', __name__)

@etsy_bp.route("/runManagerPipeline", methods=["POST"])
def run_manager_pipeline():
    """
    This endpoint is now the primary trigger for the manager logic.
    """
    print("⚡️ /runManagerPipeline endpoint hit")
    try:
        # This now correctly calls the Python-based manager logic
        assigned = assign_unclaimed_jobs(["worker1", "worker2"])
        runManagerPipeline()
        log_action(
            "Manager Trigger", 
            "Success", 
            f"Assigned {len(assigned)} jobs + ran Python pipeline", 
            agent="Manager"
        )
        return jsonify({"status": "ok", "assigned": assigned}), 200
    except Exception as e:
        print(f"🚨 HANDLER ERROR: {e}")
        log_action("Manager Trigger", "Error", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500