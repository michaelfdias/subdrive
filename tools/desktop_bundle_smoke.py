"""Launch the actual frozen GUI and require a clean exit on each native runner."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import json

if sys.platform == "darwin":
    executable = Path("dist/SubDrive Desktop.app/Contents/MacOS/SubDrive-Desktop")
else:
    executable = Path("dist/SubDrive-Desktop" + (".exe" if os.name == "nt" else ""))
with tempfile.TemporaryDirectory() as folder:
    report = Path(folder) / "result.json"
    result = subprocess.run([str(executable.resolve()), "--self-test", str(report)], timeout=120)
    data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {"success": False, "log": "No test report was produced"}
    print(data["log"])
    if result.returncode or not data["success"]:
        message = str(data["log"]).replace("%", "%25").replace("\n", "%0A")
        print("::error title=Bundled desktop test failed::" + message)
        raise SystemExit(result.returncode or 1)
print("Desktop bundle launched and exited successfully:", executable)
