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

    # Calculate target width, height via aspect ratio
    target_width = int(width_in * dpi)
    original_width, original_height = img.size
    aspect_ratio = original_height / original_width
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
