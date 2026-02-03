"""Simple script to test the redaction service manually."""

import requests
import base64
import fitz

# Service URL
BASE_URL = "http://localhost:8080"
API_KEY = "dev-secret"

# Create a simple test PDF
print("Creating test PDF...")
doc = fitz.open()
page = doc.new_page(width=612, height=792)  # US Letter
page.insert_text((72, 72), "Sensitive information to redact", fontsize=12)
pdf_bytes = doc.tobytes()
doc.close()

# Encode to base64
pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

# Test health endpoint
print("\n1. Testing /health endpoint...")
response = requests.get(f"{BASE_URL}/health")
print(f"   Status: {response.status_code}")
print(f"   Response: {response.json()}")

# Test redaction
print("\n2. Testing /redact endpoint...")
payload = {
    "pdf_data": pdf_base64,
    "redaction_rectangles": [
        {
            "page_index": 0,
            "bbox": [72, 708, 272, 720]  # Cover text area (bottom-left origin)
        }
    ]
}

response = requests.post(
    f"{BASE_URL}/redact",
    headers={"X-Redaction-Key": API_KEY},
    json=payload
)

print(f"   Status: {response.status_code}")
if response.status_code == 200:
    result = response.json()
    print(f"   Stats: {result['stats']}")
    
    # Save redacted PDF
    redacted_bytes = base64.b64decode(result["redacted_pdf"])
    with open("test_redacted.pdf", "wb") as f:
        f.write(redacted_bytes)
    print("   Saved redacted PDF to test_redacted.pdf")
else:
    print(f"   Error: {response.text}")

print("\nDone!")
