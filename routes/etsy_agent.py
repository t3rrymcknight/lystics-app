# routes/etsy_agent.py
from flask import Blueprint, request, jsonify
from services.etsy_controller import run_full_etsy_pipeline

etsy_bp = Blueprint('etsy_bp', __name__)

@etsy_bp.route("/runAgent", methods=["POST"])
def run_agent():
    try:
        result = run_full_etsy_pipeline()
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
