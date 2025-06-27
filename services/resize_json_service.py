from flask import request, jsonify
from PIL import Image
import io
import base64
import logging

def resizeJSON():
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