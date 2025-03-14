import io
from flask import Flask, request, send_file
from PIL import Image

app = Flask(__name__)

@app.route('/')
def index():
    return "Image Resize Cloud Run Service is up and running!"

@app.route('/resize', methods=['POST'])
def resize():
    if 'file' not in request.files:
        return ("Missing file in form-data. Use key 'file'.", 400)
    file = request.files['file']
    if file.filename == '':
        return ("No file selected.", 400)

    width_str = request.args.get('width', '200')
    try:
        new_width = int(width_str)
    except ValueError:
        return ("Invalid width parameter.", 400)

    image = Image.open(file.stream)
    orig_width, orig_height = image.size
    aspect_ratio = orig_height / orig_width
    new_height = int(new_width * aspect_ratio)

    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    img_io = io.BytesIO()
    image_format = image.format if image.format else 'PNG'
    resized.save(img_io, format=image_format)
    img_io.seek(0)

    return send_file(img_io, mimetype='image/' + image_format.lower())
