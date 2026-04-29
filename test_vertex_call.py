import os
from google import genai

os.environ["GOOGLE_CLOUD_PROJECT"] = "project-sutradhara"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
client = genai.Client(vertexai=True)

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say hello"
    )
    print("Success: gemini-2.5-flash")
    print(response.text)
except Exception as e:
    print(f"Error gemini-2.5-flash: {e}")

try:
    response = client.models.generate_content(
        model="gemini-1.5-pro-002",
        contents="Say hello"
    )
    print("Success: gemini-1.5-pro-002")
    print(response.text)
except Exception as e:
    print(f"Error gemini-1.5-pro-002: {e}")
