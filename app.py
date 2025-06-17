from flask import Flask, request, jsonify
from PIL import Image
import io
import base64
import os
import json
import requests
import logging
from playwright.sync_api import sync_playwright

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


# === GOOGLE SHOPPING PRICE SCRAPER USING PLAYWRIGHT ===
@app.route("/api/price-check", methods=["POST"])
def price_check():
    data = request.json
    keyword = data.get("keyword")
    if not keyword:
        return jsonify({"error": "No keyword provided"}), 400

    logging.info(f"🔍 Price check for: {keyword}")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                url = f"https://www.google.com/search?tbm=shop&q={keyword}"
                page.goto(url, timeout=15000)

                # Try accept cookies
                try:
                    if page.locator('button:has-text("Accept all")').is_visible():
                        page.locator('button:has-text("Accept all")').click()
                        logging.info("🍪 Accepted cookies.")
                except:
                    pass

                page.wait_for_selector('div.sh-dgr__grid-result, span.a8Pemb', timeout=10000)
                price_texts = page.locator('span.a8Pemb')
                if price_texts.count() == 0:
                    price_texts = page.locator('div.sh-osd__price')  # fallback

                prices = []
                for i in range(price_texts.count()):
                    raw = price_texts.nth(i).inner_text().replace('£', '').replace('€', '').replace(',', '').strip()
                    try:
                        prices.append(float(raw))
                    except:
                        continue
            finally:
                browser.close()

        logging.info(f"💰 Extracted {len(prices)} prices.")
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

    except Exception as e:
        logging.error(f"❌ Scraping failed: {str(e)}")
        return jsonify({"error": f"Scraping failed: {str(e)}"}), 500


# === Cloud Run launch ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
