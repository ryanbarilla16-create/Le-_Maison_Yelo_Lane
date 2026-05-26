import re

with open("routes/portals/__init__.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if "supplier" in line.lower():
            print(f"Line {i}: {line.strip()}")
