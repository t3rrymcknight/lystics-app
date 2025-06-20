
# services/etsy_controller.py
import requests
from datetime import datetime

GAS_BASE_URL = "https://script.google.com/macros/s/AKfycbxdyW_RnE8LFKrrm1cFE45kia9pdb_5ytzXGdvflZ8C5oHrd-QTYnRKD5OUTW1DKgCd/exec"
ADMIN_EMAIL = "support@tmk.digital"

def call_gas_function(function_name, params={}):
    url = f"{GAS_BASE_URL}?function={function_name}"
    response = requests.post(url, json=params)
    if response.status_code != 200:
        raise Exception(f"{function_name} failed: {response.text}")
    return response.json()

def run_step(name):
    try:
        call_gas_function(name)
        return f"✅ {name} success"
    except Exception as e:
        return f"❌ {name} failed: {e}"

def run_full_etsy_pipeline():
    steps = [
        "downloadImagesToDrive", "copyResizeImageAndStoreUrl", "processImagesWithOpenAI",
        "resetSetManualRowsToCreate", "processCreateFolders", "updateFileNamesWithImageName",
        "moveFilesAndImagesToFolder", "processCreatePDF", "copyUpscaleImageAndStoreVariants",
        "generateMockupsFromDrive", "updateImagesFromMockupFolders",
        "validateListingReadiness", "updateProgressIndicators", "processListings"
    ]
    logs = [run_step(step) for step in steps]
    return {
        "status": "success",
        "logs": logs,
        "summary": f"Etsy Agent completed {len(steps)} steps on {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    }
