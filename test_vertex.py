import os
from google import genai

os.environ["GOOGLE_CLOUD_PROJECT"] = "project-sutradhara"
os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
client = genai.Client(vertexai=True)

try:
    models = list(client.models.list())
    print(f"Total models: {len(models)}")
    for m in models[:10]:
        print(m.name)
except Exception as e:
    print(f"Error: {e}")
