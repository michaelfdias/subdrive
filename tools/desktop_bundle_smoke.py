"""Launch the actual frozen GUI and require a clean exit on each native runner."""
import os
from pathlib import Path
import subprocess
import sys

if sys.platform == "darwin":
    executable = Path("dist/SubDrive Desktop.app/Contents/MacOS/SubDrive-Desktop")
else:
    executable = Path("dist/SubDrive-Desktop" + (".exe" if os.name == "nt" else ""))
subprocess.run([str(executable.resolve()), "--smoke-test"], check=True, timeout=90)
print("Desktop bundle launched and exited successfully:", executable)
