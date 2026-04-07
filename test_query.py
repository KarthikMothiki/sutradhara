import requests
import time
import sys

resp = requests.post("http://127.0.0.1:8080/api/v1/query", json={"query": "Schedule a meeting with my team for tomorrow and update notion with the agenda."})
print(resp.json())
cid = resp.json()["id"]

for i in range(30):
    res = requests.get(f"http://127.0.0.1:8080/api/v1/query/{cid}")
    data = res.json()
    if data["status"] in ["completed", "failed"]:
        print("Done:", data["status"])
        print("Diagram exist?", bool(data.get("workflow_diagram")))
        if data.get("workflow_diagram"):
            print("Diagram data:", data["workflow_diagram"])
        # wait a bit for trace output, maybe final_response
        print("Final response:")
        print(data["final_response"])
        break
    time.sleep(2)
