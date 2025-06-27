from flask import request, jsonify
from PIL import Image
import io
import base64
import logging

def upscaleImage():
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