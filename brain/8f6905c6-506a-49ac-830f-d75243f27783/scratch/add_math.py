with open("orchestrator/orchestrator.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
math_added = False
for line in lines:
    new_lines.append(line)
    if "import logging" in line and not math_added:
        new_lines.append("import math\n")
        math_added = True

with open("orchestrator/orchestrator.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Math import added:", math_added)

