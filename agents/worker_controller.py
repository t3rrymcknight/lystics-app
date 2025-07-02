from agents.queue_gas_call import queue_gas_call
# routes/etsy_agent.py
from flask import Blueprint, jsonify, request
from api.api_gateway import run_etsy_agent

etsy_bp = Blueprint('etsy_bp', __name__)

@etsy_bp.route("/runAgent", methods=["POST"])
def run_agent():
    try:
        result = run_etsy_agent()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@etsy_bp.route("/runManagerPipeline", methods=["POST"])
def run_manager_pipeline():
    from api.api_gateway import call_gas_function, log_action
    from agents.agent_manager import assign_unclaimed_jobs

    try:
        assigned = assign_unclaimed_jobs(["worker1", "worker2"])
        response = call_gas_function("runManagerPipeline")
        log_action("Manager Trigger", "Success", f"Assigned {len(assigned)} jobs + ran GAS pipeline")
        return jsonify({"status": "ok", "assigned": assigned, "response": response})
    except Exception as e:
        log_action("Manager Trigger", "Error", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
