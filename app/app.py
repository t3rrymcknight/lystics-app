from flask import Flask, request, send_file
from PIL import Image
import io

app = Flask(__name__)

@app.route('/resize', methods=['POST'])
def resize_image():
    # Check if the request contains the file
    if 'file' not in request.files:
        return "No file found in request", 400

    file = request.files['file']
    if file.filename == '':
        return "No selected file", 400

    # Get the requested width from the form (optional)
    requested_width = request.form.get('width')
    if requested_width:
        new_width = int(requested_width)
    else:
        new_width = 300  # fallback or default

    # Open with Pillow
    img = Image.open(file)

    # Preserve aspect ratio by computing new height
    original_width, original_height = img.size
    aspect_ratio = original_width / original_height
    new_height = int(new_width / aspect_ratio)

    # Resize using LANCZOS
    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Return as JPEG in-memory
    img_io = io.BytesIO()
    resized_img.save(img_io, format='JPEG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/jpeg')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
