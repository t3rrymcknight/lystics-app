from flask import Flask, request, jsonify
from PIL import Image
import io
import base64
import os
import json
import requests
import logging
from bs4 import BeautifulSoup
import re

# ✅ Setup logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# === Health Check Route ===
@app.route("/healthz", methods=["GET"])
def health():
    return "ok", 200

# === Global Error Handler ===
@app.errorhandler(Exception)
def handle_error(e):
    logging.error(f"Unhandled exception: {e}")
    return jsonify({"error": str(e)}), 500

# === Home Route ===
@app.route('/')
def home():
    return "Welcome to TMK Image Resizer & Price Checker!"

# === IMAGE RESIZER ===
@app.route('/resizeJson', methods=['POST'])
def resize_image_json():
    try:
        data = request.get_json(force=True)
        base64_image = data.get('image')
        new_width = int(data.get('width', 300))

        if not base64_image:
            raise ValueError("Missing image data")

        image_bytes = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_bytes))
        input_format = img.format or "JPEG"

        original_width, original_height = img.size
        aspect_ratio = original_width / original_height
        new_height = int(new_width / aspect_ratio)
        resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

        if input_format.upper() == "PNG":
            resized_img = resized_img.convert("RGBA")
        else:
            resized_img = resized_img.convert("RGB")

        out_buffer = io.BytesIO()
        resized_img.save(out_buffer, format=input_format)
        out_buffer.seek(0)
        resized_base64 = base64.b64encode(out_buffer.read()).decode("utf-8")

        return jsonify({"image": resized_base64, "format": input_format}), 200

    except Exception as e:
        logging.error(f"Resize failed: {e}")
        return jsonify({"error": f"Resize failed: {e}"}), 500

# === UPSCALER ===
@app.route('/upscaleOne', methods=['POST'])
def upscale_one():
    try:
        data = request.get_json(force=True)
        base64_image = data.get('image')
        format = data.get('format', 'JPEG').upper()
        dpi = int(data.get('dpi', 300))
        width_in = float(data['widthInches'])

        if not base64_image:
            raise ValueError("Missing image data")

        image_bytes = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGBA") if format == "PNG" else img.convert("RGB")

        original_width, original_height = img.size
        aspect_ratio = original_height / original_width
        target_width = int(width_in * dpi)
        target_height = int(target_width * aspect_ratio)

        upscaled_img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        out_buffer = io.BytesIO()
        save_kwargs = {"format": format, "dpi": (dpi, dpi)}
        if format == "JPEG":
            save_kwargs["quality"] = 95
        upscaled_img.save(out_buffer, **save_kwargs)
        out_buffer.seek(0)
        upscaled_base64 = base64.b64encode(out_buffer.read()).decode("utf-8")
        dimensions = f"{target_width}x{target_height}"
        return jsonify({"image": upscaled_base64, "dimensions": dimensions}), 200

    except Exception as e:
        logging.error(f"Upscale failed: {e}")
        return jsonify({"error": f"Upscale failed: {e}"}), 500

# === PRICE CHECK ===
@app.route("/api/price-check", methods=["POST"])
def price_check():
    data = request.json
    keyword = data.get("keyword")
    if not keyword:
        return jsonify({"error": "No keyword provided"}), 400

    logging.info(f"🔍 Price check for: {keyword}")
    prices = scrape_google_shopping(keyword)

    if not prices:
        logging.warning("⚠️ No prices found or failed to scrape")
        return jsonify({
            "keyword": keyword,
            "min_price": None,
            "max_price": None,
            "avg_price": None,
            "found_prices": []
        }), 200

    return jsonify({
        "keyword": keyword,
        "min_price": min(prices),
        "max_price": max(prices),
        "avg_price": round(sum(prices) / len(prices), 2),
        "found_prices": prices
    }), 200

def scrape_google_shopping(keyword):
    API_TOKEN = os.getenv("CYlpaaQZbbH1k-5wzEAq5Q")  # Replace with correct ENV var
    base_url = "https://api.crawlbase.com/"
    query_url = f"https://www.google.com/search?q={keyword}&tbm=shop"

    params = {
        "token": API_TOKEN,
        "url": query_url,
        "country": "gb",
        "user_agent": "Mozilla/5.0",
        "page_wait": 5000
    }

    try:
        response = requests.get(base_url, params=params, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        price_elements = soup.find_all("span", string=re.compile(r"£\\s?[\\d,.]+"))
        prices = []
        for elem in price_elements:
            try:
                price = float(re.sub(r"[£,]", "", elem.text.strip()))
                prices.append(price)
            except:
                continue

        logging.info(f"💰 Extracted {len(prices)} prices.")
        return prices
    except Exception as e:
        logging.error(f"❌ Crawlbase error: {e}")
        return []

# === MOCKUP ROUTE REGISTRATION ===
from routes.mockups import mockup_bp
app.register_blueprint(mockup_bp)

# === E-AGENT ROUTE REGISTRATION ===
from routes.etsy_agent import etsy_bp
app.register_blueprint(etsy_bp)

# === Launch ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
