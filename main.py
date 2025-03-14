import io
from flask import Flask, request, send_file, abort
from PIL import Image

app = Flask(__name__)

@app.route('/', methods=['GET'])
def index():
    return "Image Resize Function is up and running!"

@app.route('/resize', methods=['POST'])
def resize():
    # Check if a file was sent in the request
    if 'file' not in request.files:
        return ("Missing file in form-data. Use key 'file'.", 400)
    
    file = request.files['file']
    if file.filename == '':
        return ("No file selected.", 400)
    
    # Get the desired width from the query parameter (default: 200)
    width_str = request.args.get('width', '200')
    try:
        new_width = int(width_str)
    except ValueError:
        return ("Invalid width parameter.", 400)
    
    try:
        # Open the image using Pillow
        image = Image.open(file.stream)
        orig_width, orig_height = image.size
        aspect_ratio = orig_height / orig_width
        new_height = int(new_width * aspect_ratio)
        
        # Resize the image using a high-quality filter
        resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Save the resized image to an in-memory bytes buffer
        img_io = io.BytesIO()
        image_format = image.format if image.format else 'PNG'
        resized.save(img_io, format=image_format)
        img_io.seek(0)
        
        # Return the resized image
        return send_file(img_io, mimetype='image/' + image_format.lower())
    except Exception as e:
        return (f"Error processing image: {str(e)}", 500)

# This is the entry point for Cloud Functions (2nd gen)
def main(request):
    return app(request)
