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


# === MOCKUP GENERATOR ===
@app.route('/generateMockups', methods=['POST'])
def generate_mockups():
    try:
        data = request.get_json(force=True)
        logging.info("📥 Incoming Mockup Request Payload:\n" + json.dumps(data, indent=2))
    except Exception as e:
        return jsonify({"error": f"Failed to parse JSON: {str(e)}"}), 400

    sku = data.get("sku")
    image_url = data.get("imageDriveUrl")
    mockup_names = data.get("mockups", [])
    mockup_json_text = data.get("mockupJson", "")
    mockup_images = data.get("mockupImages", {})

    if not image_url or not sku or not mockup_names or not mockup_json_text or not mockup_images:
        return jsonify({"error": "Missing required fields"}), 400

    try:
        image_blob = requests.get(image_url).content
        product_image = Image.open(io.BytesIO(image_blob)).convert("RGBA")
    except Exception as e:
        return jsonify({"error": f"Failed to load base image: {str(e)}"}), 400

    try:
        full_config = json.loads(mockup_json_text)
        config_map = full_config["mockups"] if "mockups" in full_config else full_config
    except Exception as e:
        return jsonify({"error": f"Invalid mockup JSON: {str(e)}"}), 400

    output = {}
    for mockup_name in mockup_names:
        try:
            if mockup_name not in config_map:
                output[mockup_name] = "Mockup not defined in JSON"
                continue

            config = config_map[mockup_name]
            layers = config.get("layers", [])
            if not layers:
                output[mockup_name] = "No layers defined"
                continue

            canvas = None
            mockup_assets = mockup_images.get(mockup_name, {})

            for layer in layers:
                name = layer["name"]
                x = layer.get("x", 0)
                y = layer.get("y", 0)

                if name == "IMAGE":
                    w, h = layer["width"], layer["height"]
                    resized = product_image.resize((w, h), Image.Resampling.LANCZOS)
                    if canvas is None:
                        canvas = Image.new("RGBA", resized.size)
                    canvas.paste(resized, (x, y), resized)
                else:
                    key = name + ".png"
                    if key not in mockup_assets:
                        output[mockup_name] = f"Missing {key} in mockup assets"
                        break

                    layer_bytes = base64.b64decode(mockup_assets[key])
                    overlay = Image.open(io.BytesIO(layer_bytes)).convert("RGBA")
                    if canvas is None:
                        canvas = Image.new("RGBA", overlay.size)
                    canvas.paste(overlay, (x, y), overlay)

            if canvas:
                out_buffer = io.BytesIO()
                canvas.convert("RGB").save(out_buffer, format="JPEG", quality=95)
                out_buffer.seek(0)
                encoded = base64.b64encode(out_buffer.read()).decode("utf-8")
                output[mockup_name] = encoded
        except Exception as e:
            output[mockup_name] = f"Error generating mockup: {str(e)}"

    return jsonify({"sku": sku, "results": output})


# === PLAYWRIGHT PRICE CHECK ===
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
            page = browser.new_page()
            url = f"https://www.google.com/search?tbm=shop&q={keyword}"
            page.goto(url, timeout=15000)

            # Accept cookies if visible
            try:
                if page.locator('button:has-text("Accept all")').is_visible():
                    page.locator('button:has-text("Accept all")').click()
                    logging.info("🍪 Accepted cookies.")
            except:
                pass

            page.wait_for_selector('div.sh-dgr__grid-result', timeout=10000)

            price_texts = page.locator('span.a8Pemb')
            prices = []
            count = price_texts.count()
            for i in range(count):
                raw = price_texts.nth(i).inner_text().replace('£', '').replace(',', '').strip()
                try:
                    prices.append(float(raw))
                except:
                    continue

            browser.close()

            return jsonify({
                "keyword": keyword,
                "min_price": min(prices) if prices else None,
                "max_price": max(prices) if prices else None,
                "avg_price": round(sum(prices) / len(prices), 2) if prices else None,
                "found_prices": prices
            })
    except Exception as e:
        logging.error(f"❌ Scraping failed: {str(e)}")
        return jsonify({"error": f"Scraping failed: {str(e)}"}), 500


# === Cloud Run launch ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
