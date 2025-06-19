# services/mockup_generator.py

def generate_mockups(sku, image_url, mockup_json, mockup_images, mockup_names):
    # TODO: Implement your image merging + layer composition here
    # This returns a dict like: { "Mockup 1": base64_img, "Mockup 2": base64_img }
    output = {}

    # parse mockup_json, extract each mockup's layers
    # use PIL or OpenCV to layer the base, image (with x,y,width,height), then top
    # build result as: output[mockup_name] = base64_encoded_image

    return output
