workflow_steps = {
    "POD Shirt": [
        "Download Image",
        "Upscale Image",
        "Add Mockups",
        "Generate Mockup JSON",
        "Upload Images",
        "Create JSON"
    ],
    "Coloring Book": [
        "Download Image",
        "Create PDF",
        "Upload Files",
        "Create JSON"
    ],
    "SVG Design": [
        "Download Image",
        "Upload Files",
        "Create JSON"
    ]
}

# Enhanced workflow definition with priority
workflow_steps_with_priority = {
    "POD Shirt": [
        {"step": "Download Image", "priority": "high"},
        {"step": "Upscale Image", "priority": "high"},
        {"step": "Add Mockups", "priority": "medium"},
        {"step": "Generate Mockup JSON", "priority": "medium"},
        {"step": "Upload Images", "priority": "low"},
        {"step": "Create JSON", "priority": "low"}
    ],
    "Coloring Book": [
        {"step": "Download Image", "priority": "high"},
        {"step": "Create PDF", "priority": "high"},
        {"step": "Upload Files", "priority": "medium"},
        {"step": "Create JSON", "priority": "low"}
    ],
    "SVG Design": [
        {"step": "Download Image", "priority": "high"},
        {"step": "Upload Files", "priority": "medium"},
        {"step": "Create JSON", "priority": "low"}
    ]
}
