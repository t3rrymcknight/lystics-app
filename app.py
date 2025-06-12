from flask import Flask, request, jsonify
from PIL import Image, ImageOps
import io
import base64

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
    new_width = data.get('width', 300)

    try:
        new_width = int(new_width)
    except ValueError:
        return jsonify({"error": "width must be an integer"}), 400

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

    # Calculate target dimensions using original aspect ratio
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
    image_url = data.get("imageDriveUrl")
    mockup_names = data.get("mockups")  # List of mockup names
    mockup_meta = data.get("mockupMeta", {})  # Optional dictionary of {mockup name -> ID}

    if not image_url or not sku or not mockup_names:
        return jsonify({"error": "Missing imageDriveUrl, sku, or mockups[]"}), 400

    try:
        image_blob = requests.get(image_url).content
        image = Image.open(io.BytesIO(image_blob)).convert("RGBA")
    except Exception as e:
        return jsonify({"error": f"Failed to load base image: {str(e)}"}), 400

    output_folder = f"output/{sku}"
    os.makedirs(output_folder, exist_ok=True)

    results = {}
    for mockup_name in mockup_names:
        mockup_id = mockup_meta.get(mockup_name)
        if not mockup_id:
            results[mockup_name] = "No mockup ID found"
            continue

        mockup_folder = f"mockups/{mockup_id}"
        mockup_path = os.path.join(mockup_folder, "mockup.json")
        if not os.path.exists(mockup_path):
            results[mockup_name] = "Missing mockup.json"
            continue

        try:
            with open(mockup_path) as f:
                full_config = json.load(f)

            if isinstance(full_config, dict) and "mockups" in full_config:
                config = full_config["mockups"].get(mockup_name)
            else:
                config = full_config

            if not config or "layers" not in config:
                results[mockup_name] = "Invalid or missing layer definition"
                continue

            base = None
            for layer in config["layers"]:
                name = layer["name"]
                x, y = layer.get("x", 0), layer.get("y", 0)

                if name == "IMAGE":
                    w, h = layer["width"], layer["height"]
                    image_resized = image.resize((w, h), Image.Resampling.LANCZOS)
                    base.paste(image_resized, (x, y), image_resized)
                else:
                    path = os.path.join(mockup_folder, f"{name}.png")
                    overlay = Image.open(path).convert("RGBA")
                    if base is None:
                        base = Image.new("RGBA", overlay.size)
                    base.paste(overlay, (x, y), overlay)

            output_path = os.path.join(output_folder, f"{mockup_name}.jpg")
            base.convert("RGB").save(output_path, "JPEG", quality=95)
            results[mockup_name] = output_path
        except Exception as e:
            results[mockup_name] = f"Failed: {str(e)}"

    return jsonify({"sku": sku, "results": results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
