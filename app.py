from flask import Flask, request, send_file
from PIL import Image
import io

app = Flask(__name__)

@app.route('/')
def index():
    """
    A simple root route so that visiting the base URL 
    won't return the default placeholder page.
    """
    return "Welcome to TMK Image Resizer! Use the /resize endpoint to POST an image."

@app.route('/resize', methods=['POST'])
def resize_image():
    """
    Expects a multipart/form-data POST with:
      - 'file': the image to resize
      - 'width': optional desired new width (integer)

    Returns the resized image in JPEG format.
    """
    # 1. Check if file is present
    if 'file' not in request.files:
        return "No file found in request.", 400

    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return "File is empty.", 400

    # 2. Get desired width from the form (optional), default=300
    requested_width = request.form.get('width')
    if requested_width:
        try:
            new_width = int(requested_width)
        except ValueError:
            return "Width must be an integer.", 400
    else:
        new_width = 300

    # 3. Open image with Pillow
    try:
        img = Image.open(uploaded_file)
    except Exception as e:
        return f"Error opening file: {str(e)}", 400

    # 4. Preserve aspect ratio for new size
    original_width, original_height = img.size
    aspect_ratio = original_width / original_height
    new_height = int(new_width / aspect_ratio)

    # 5. Resize (using LANCZOS for quality)
    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # 6. Convert to BytesIO, return as JPEG
    img_io = io.BytesIO()
    try:
        resized_img.save(img_io, format='JPEG')
    except Exception as e:
        return f"Error converting image: {str(e)}", 500
    
    img_io.seek(0)
    return send_file(img_io, mimetype='image/jpeg')

# Cloud Run requires listening on 0.0.0.0:8080
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
