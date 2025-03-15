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

    # Convert file to an Image object
    img = Image.open(file)

    # Example: keep aspect ratio with a new height of 300
    original_width, original_height = img.size
    aspect_ratio = original_width / original_height
    new_height = 300
    new_width = int(new_height * aspect_ratio)

    # Resize image using Pillow’s LANCZOS
    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Save to a BytesIO stream
    img_io = io.BytesIO()
    resized_img.save(img_io, format='JPEG')  # or PNG
    img_io.seek(0)

    # Return the resized image
    return send_file(
        img_io, 
        mimetype='image/jpeg', 
        as_attachment=False, 
        download_name='resized.jpg'
    )

if __name__ == '__main__':
    # For local testing only
    app.run(host='0.0.0.0', port=8080, debug=True)
