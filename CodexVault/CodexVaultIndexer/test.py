import os
from pathlib import Path

# 1. Define the path
vault_path = Path(
    os.getenv("CODEX_LIBRARY_PATH", "D:/Dev/projects/Completed_Projects/CVIS/Codex")
)

# 2. Iterate and print
# .iterdir() gives you everything in the folder
for item in vault_path.iterdir():
    
    print(f"File found: {item.name}")
