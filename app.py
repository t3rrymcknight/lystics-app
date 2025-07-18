from flask import Flask, jsonify
import logging
import os

# === Service Routes ===
from services.resize_json_service import resizeJSON
from services.upscaler import upscaleImage
from api.price_check import price_check_bp
from routes.mockups import mockup_bp
from agents.worker_controller import etsy_bp

# ✅ Setup logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# === Global Health and Error Routes ===
@app.route("/healthz", methods=["GET"])
def health():
    return "ok", 200

@app.errorhandler(Exception)
def handle_error(e):
    logging.error(f"Unhandled exception: {e}")
    return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    return "Welcome to Lystics Agent System!"

# === Register External Blueprints ===
app.register_blueprint(price_check_bp)
app.register_blueprint(mockup_bp)
app.register_blueprint(etsy_bp, url_prefix='/agent')

# === Register Service Routes via Function Mapping ===
app.add_url_rule('/resizeJson', view_func=resizeJSON, methods=['POST'])
app.add_url_rule('/upscaleOne', view_func=upscaleImage, methods=['POST'])


# === Launch ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
