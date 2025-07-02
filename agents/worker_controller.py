from agents.queue_gas_call import queue_gas_call
# routes/etsy_agent.py
from flask import Blueprint, jsonify, request
from api.api_gateway import run_etsy_agent

etsy_bp = Blueprint('etsy_bp', __name__)

@etsy_bp.route("/runAgent", methods=["POST"])
def run_agent():
    try:
        result = queue_gas_call("run_etsy_agent", lambda name: run_etsy_agent())
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@etsy_bp.route("/runManagerPipeline", methods=["POST"])
def run_manager_pipeline():
    from agents.agent_manager import assign_unclaimed_jobs, runManagerPipeline
    from api.api_gateway import log_action

    try:
        assigned = assign_unclaimed_jobs(["worker1", "worker2"])
        runManagerPipeline()
        log_action("Manager Trigger", "Success", f"Assigned {len(assigned)} jobs + ran Python pipeline", agent="Manager")
        return jsonify({"status": "ok", "assigned": assigned}), 200
    except Exception as e:
        log_action("Manager Trigger", "Error", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
