import subprocess
from pathlib import Path

file_path = Path(r"d:\RAYSAN\ai-2d-checker\services\storage\uploads\ba0d4bbe5bc6cc1c5a7866ee6e2ee08051823d2c4feec72de077ae949ea86155.icd")

res = subprocess.run(["C:/ICADSX/bin/ICD2STP.exe", str(file_path)], capture_output=True, text=True, cwd="C:/ICADSX/bin")
print(f"Code 1: {res.returncode}")
print(f"Stdout 1: {res.stdout}")
print(f"Stderr 1: {res.stderr}")

res2 = subprocess.run(["C:/ICADSX/bin/ICD2STP.exe", "-i", str(file_path)], capture_output=True, text=True, cwd="C:/ICADSX/bin")
print(f"Code 2: {res2.returncode}")

res3 = subprocess.run(["C:/ICADSX/bin/ICD2STP.exe", str(file_path), str(file_path.with_suffix('.step'))], capture_output=True, text=True, cwd="C:/ICADSX/bin")
print(f"Code 3: {res3.returncode}")
