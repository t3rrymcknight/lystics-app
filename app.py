from flask import Flask, request, jsonify
from PIL import Image
import io
import base64

app = Flask(__name__)

@app.route('/')
def home():
    return "Welcome to TMK Image Resizer!"

@app.route('/resizeJson', methods=['POST'])
def resize_image_json():
    """
    Expects JSON with:
      {
        "image": <base64 image data>,
        "contentType": "image/jpeg" (optional),
        "width": 300 (optional)
      }
    Returns JSON:
      {
        "image": <base64 of resized image>
      }
    """
    # 1) Parse JSON
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

    # 2) Decode the base64 image into bytes
    try:
        image_bytes = base64.b64decode(base64_image)
    except Exception as e:
        return jsonify({"error": f"Failed to decode base64: {str(e)}"}), 400

    # 3) Open with Pillow
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        return jsonify({"error": f"Failed to open image: {str(e)}"}), 400

    # 4) Resize while preserving aspect ratio
    original_width, original_height = img.size
    aspect_ratio = original_width / original_height
    new_height = int(new_width / aspect_ratio)

    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # 5) Convert back to base64
    out_buffer = io.BytesIO()
    try:
        resized_img.save(out_buffer, format="JPEG")
    except Exception as e:
        return jsonify({"error": f"Failed to save resized image: {str(e)}"}), 500

    out_buffer.seek(0)
    resized_base64 = base64.b64encode(out_buffer.read()).decode("utf-8")

    # 6) Return JSON with base64 string
    return jsonify({"image": resized_base64}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
