import io
import json
import base64
import requests
from PIL import Image

def generate_mockups(sku, image_url, mockup_json, mockup_images, mockup_names):
    output = {}

    try:
        json_data = json.loads(mockup_json)
        structure = json_data.get("mockups", {})
    except Exception as e:
        print(f"❌ Failed to parse mockup_json: {e}")
        return {}

    # Download user image
    try:
        response = requests.get(image_url)
        user_img = Image.open(io.BytesIO(response.content)).convert("RGBA")
    except Exception as e:
        print(f"❌ Failed to fetch user image: {e}")
        return {}

    for mockup_name in mockup_names:
        try:
            layers = structure.get(mockup_name, {}).get("layers", [])
            if not layers:
                print(f"⚠️ No layers for {mockup_name}")
                continue

            mockup_folder = mockup_images.get(mockup_name, {})
            base_img = None
            overlay_img = None

            for layer in layers:
                lname = layer.get("name")

                # Load BASE
                if lname == "BASE":
                    base_file = next((v for k, v in mockup_folder.items() if "base" in k.lower()), None)
                    if not base_file:
                        print(f"❌ No BASE layer for {mockup_name}")
                        continue
                    base_img = Image.open(io.BytesIO(base64.b64decode(base_file))).convert("RGBA")

                # Paste user image
                elif lname == "IMAGE" and base_img:
                    x = int(layer.get("x", 0))
                    y = int(layer.get("y", 0))
                    w = int(layer.get("width", 300))
                    h = int(layer.get("height", 300))

                    resized_user_img = user_img.resize((w, h), Image.Resampling.LANCZOS)
                    base_img.paste(resized_user_img, (x, y), resized_user_img)

                # Optional TOP layer
                elif lname == "TOP" and base_img:
                    top_file = next((v for k, v in mockup_folder.items() if "top" in k.lower()), None)
                    if top_file:
                        overlay_img = Image.open(io.BytesIO(base64.b64decode(top_file))).convert("RGBA")
                        base_img = Image.alpha_composite(base_img, overlay_img)

            if base_img:
                final_buffer = io.BytesIO()
                base_img = base_img.convert("RGB")  # convert to JPEG
                base_img.save(final_buffer, format="JPEG", quality=95)
                base64_output = base64.b64encode(final_buffer.getvalue()).decode("utf-8")
                output[mockup_name] = base64_output

        except Exception as e:
            print(f"❌ Error processing {mockup_name}: {e}")
            continue

    return output
