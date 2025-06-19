# routes/mockups.py

from flask import Blueprint, request, jsonify
from services.mockup_generator import generate_mockups  # You may need to create this

mockup_bp = Blueprint('mockup', __name__)

@mockup_bp.route('/generateMockups', methods=['POST'])
def handle_generate_mockups():
    try:
        data = request.get_json()
        sku = data.get('sku')
        image_url = data.get('imageDriveUrl')
        mockup_json = data.get('mockupJson')
        mockup_images = data.get('mockupImages')
        mockup_names = data.get('mockups')

        if not all([sku, image_url, mockup_json, mockup_images]):
            return jsonify({'error': 'Missing required fields'}), 400

        results = generate_mockups(sku, image_url, mockup_json, mockup_images, mockup_names)

        return jsonify({ 'results': results }), 200

    except Exception as e:
        return jsonify({ 'error': str(e) }), 500
