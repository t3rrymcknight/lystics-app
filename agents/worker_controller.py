from flask import Blueprint, jsonify
from agents.agent_manager import runManagerPipeline

etsy_bp = Blueprint('etsy_bp', __name__)

@etsy_bp.route("/runManagerPipeline", methods=["POST"])
def run_manager_pipeline_endpoint():
    """
    This endpoint is the primary trigger for the entire workflow.
    It calls the main orchestrator function in agent_manager.
    """
    print("⚡️ /runManagerPipeline endpoint hit. Starting full workflow.")
    try:
        runManagerPipeline()
        return jsonify({"status": "ok", "message": "Full pipeline executed."}), 200
    except Exception as e:
        print(f"🚨 HANDLER ERROR: {e}")
        try:
            from api.api_gateway import log_action
            log_action("Manager Trigger", "Critical Error", str(e))
        except Exception as log_e:
            print(f"🚨 FAILED TO LOG CRITICAL ERROR: {log_e}")
            
        return jsonify({"status": "error", "message": str(e)}), 500
