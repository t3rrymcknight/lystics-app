from flask import Flask, request, jsonify
from PIL import Image, ImageOps
import io
import base64
import os
import json
import requests  # Required for downloading Drive image

app = Flask(__name__)

@app.route('/')
def home():
    return "Welcome to TMK Image Resizer!"

@app.route('/resizeJson', methods=['POST'])
def resize_image_json():
    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({"error": "No image data found"}), 400

    base64_image = data['image']
    content_type = data.get('contentType', 'image/jpeg')
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

@app.route('/generateMockups', methods=['POST'])
def generate_mockups():
    data = request.get_json()
    sku = data.get("sku")
    image_b64 = data.get("image")  # main product image in base64
    mockup_defs = data.get("mockups")  # dict of {mockupName: config with layers}

    if not sku or not image_b64 or not mockup_defs:
        return jsonify({"error": "Missing required fields (sku, image, mockups)"}), 400

    try:
        image_bytes = base64.b64decode(image_b64)
        base_image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception as e:
        return jsonify({"error": f"Failed to decode base image: {str(e)}"}), 400

    results = {}

    for mockup_name, config in mockup_defs.items():
        layers = config.get("layers")
        if not layers:
            results[mockup_name] = "Invalid or missing layers"
            continue

        try:
            canvas = None
            for layer in layers:
                name = layer["name"]
                x, y = layer.get("x", 0), layer.get("y", 0)

                if name == "IMAGE":
                    w, h = layer["width"], layer["height"]
                    resized = base_image.resize((w, h), Image.Resampling.LANCZOS)
                    if canvas is None:
                        canvas = Image.new("RGBA", resized.size)
                    canvas.paste(resized, (x, y), resized)
                else:
                    overlay_b64 = layer.get("overlay")  # passed from Apps Script
                    if not overlay_b64:
                        continue
                    overlay_img = Image.open(io.BytesIO(base64.b64decode(overlay_b64))).convert("RGBA")
                    if canvas is None:
                        canvas = Image.new("RGBA", overlay_img.size)
                    canvas.paste(overlay_img, (x, y), overlay_img)

            out_buffer = io.BytesIO()
            canvas.convert("RGB").save(out_buffer, "JPEG", quality=95)
            out_buffer.seek(0)
            b64_result = base64.b64encode(out_buffer.read()).decode("utf-8")
            results[mockup_name] = b64_result
        except Exception as e:
            results[mockup_name] = f"Failed to render: {str(e)}"

    return jsonify({"sku": sku, "results": results}), 200


# ✅ Cloud Run compliant launch
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
