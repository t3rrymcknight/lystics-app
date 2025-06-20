# routes/etsy_agent.py
from flask import Blueprint, jsonify, request
from services.etsy_controller import run_etsy_agent

etsy_bp = Blueprint('etsy_bp', __name__)

@etsy_bp.route("/runAgent", methods=["POST"])
def run_agent():
    try:
        result = run_etsy_agent()
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
