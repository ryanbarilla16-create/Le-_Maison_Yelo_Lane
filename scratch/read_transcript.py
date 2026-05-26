import json
import sys

path = r"C:\Users\Ryan Bien Barilla\.gemini\antigravity-ide\brain\4378f0eb-afa5-45d6-9ffc-26f8309e0c9c\.system_generated\logs\transcript.jsonl"
out_path = r"c:\Users\Ryan Bien Barilla\OneDrive\Desktop\python web (capstone)\scratch\transcript_debug.txt"

with open(path, "r", encoding="utf-8") as f, open(out_path, "w", encoding="utf-8") as out:
    for line in f:
        data = json.loads(line)
        step = data.get("step_index", 0)
        if step >= 1080:
            out.write(f"=== Step {step} | Source: {data.get('source')} | Type: {data.get('type')} ===\n")
            content = data.get("content", "")
            if content:
                out.write(f"Content:\n{content}\n")
            if "tool_calls" in data:
                out.write(f"Tool Calls: {json.dumps(data['tool_calls'], indent=2)}\n")
            out.write("-" * 50 + "\n")
print("Done writing transcript debug file.")
