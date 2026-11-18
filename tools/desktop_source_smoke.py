"""Surface GUI startup failures as CI annotations as well as ordinary logs."""
import subprocess
import sys

result = subprocess.run([sys.executable, "-m", "subdrive.desktop", "--smoke-test"],
                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
print(result.stdout)
if result.returncode:
    message = result.stdout.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print("::error title=Desktop startup failed::" + message)
sys.exit(result.returncode)
