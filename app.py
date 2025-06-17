from flask import Flask, request, jsonify
from PIL import Image
import io
import base64
import os
import json
import requests
import logging
import re

# ✅ Setup logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)


@app.route('/')
def home():
    return "Welcome to TMK Image Resizer & Price Checker!"


# === IMAGE RESIZER JSON ===
@app.route('/resizeJson', methods=['POST'])
def resize_image_json():
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({"error": "No image data found"}), 400

    base64_image = data['image']
    new_width = int(data.get('width', 300))

    try:
        image_bytes = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        return jsonify({"error": f"Image decoding error: {str(e)}"}), 400

    original_width, original_height = img.size
    aspect_ratio = original_width / original_height
    new_height = int(new_width / aspect_ratio)
    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    out_buffer = io.BytesIO()
    try:
        resized_img.save(out_buffer, format="JPEG")
    except Exception as e:
        return jsonify({"error": f"Failed to save resized image: {str(e)}"}), 500

    out_buffer.seek(0)
    resized_base64 = base64.b64encode(out_buffer.read()).decode("utf-8")
    return jsonify({"image": resized_base64}), 200


# === UPSCALER ===
@app.route('/upscaleOne', methods=['POST'])
def upscale_one():
    data = request.get_json()
    if not data or 'image' not in data or 'widthInches' not in data:
        return jsonify({"error": "Missing required fields: image and widthInches"}), 400

    base64_image = data['image']
    format = data.get('format', 'JPEG').upper()
    dpi = int(data.get('dpi', 300))
    width_in = float(data['widthInches'])

    try:
        image_bytes = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGBA") if format == "PNG" else img.convert("RGB")
    except Exception as e:
        return jsonify({"error": f"Failed to decode or open image: {str(e)}"}), 400

    original_width, original_height = img.size
    aspect_ratio = original_height / original_width
    target_width = int(width_in * dpi)
    target_height = int(target_width * aspect_ratio)

    try:
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
        return jsonify({"error": f"Failed to upscale image: {str(e)}"}), 500


# === GOOGLE SHOPPING PRICE CHECK (via Crawlbase Product Offers) ===
@app.route("/api/price-check", methods=["POST"])
def price_check():
    data = request.json
    keyword = data.get("keyword")
    if not keyword:
        return jsonify({"error": "No keyword provided"}), 400

    logging.info(f"🔍 Price check for: {keyword}")

    product_url = get_google_shopping_product_url(keyword)
    if not product_url:
        logging.warning("⚠️ No Google Shopping product URL found for keyword")
        return jsonify({
            "keyword": keyword,
            "min_price": None,
            "max_price": None,
            "avg_price": None,
            "found_prices": []
        }), 200

    prices = scrape_google_product_offers(product_url)

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
    })


def get_google_shopping_product_url(keyword):
    API_TOKEN = os.getenv("CRAWLBASE_TOKEN")
    search_url = f"https://www.google.com/search?tbm=shop&q={keyword}"
    api_url = "https://api.crawlbase.com/scraper"

    params = {
        "token": API_TOKEN,
        "url": search_url,
        "device": "desktop",
        "country": "gb",
        "autoparse": "true"
    }

    try:
        response = requests.get(api_url, params=params, timeout=20)
        response.raise_for_status()
        html = response.text

        match = re.search(r"/shopping/product/\d+/offers", html)
        if match:
            return "https://www.google.com" + match.group(0)
    except Exception as e:
        logging.error(f"❌ Failed to fetch product URL: {str(e)}")

    return None


def scrape_google_product_offers(product_url):
    API_TOKEN = os.getenv("CRAWLBASE_TOKEN")
    api_url = "https://api.crawlbase.com/scraper"

    params = {
        "token": API_TOKEN,
        "url": product_url,
        "scraper": "google_product_offers"
    }

    try:
        response = requests.get(api_url, params=params, timeout=20)
        response.raise_for_status()
        json_data = response.json()

        offers = json_data.get("offers", [])
        prices = [
            float(re.sub(r"[^\d.]", "", offer.get("price", "")))
            for offer in offers if offer.get("price")
        ]

        logging.info(f"💰 Extracted {len(prices)} prices via Crawlbase product offers")
        return prices
    except Exception as e:
        logging.error(f"❌ Crawlbase product offer scrape failed: {str(e)}")
        return []


# === Cloud Run launch ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
