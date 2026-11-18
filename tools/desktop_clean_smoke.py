"""Verify portable Linux startup in an unmodified Ubuntu image; report CI errors."""
from pathlib import Path
import subprocess
import sys

result = subprocess.run(["docker", "run", "--rm", "-v", str(Path("dist").resolve()) + ":/app:ro",
    "-e", "QT_QPA_PLATFORM=offscreen", "ubuntu:22.04", "/app/SubDrive-Desktop", "--smoke-test"],
    text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
print(result.stdout)
if result.returncode:
    message = result.stdout.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::error title=Clean Linux startup failed::" + message)
sys.exit(result.returncode)
