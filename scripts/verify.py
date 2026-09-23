from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
required = [
    ROOT/"backend/app/main.py",
    ROOT/"backend/app/models.py",
    ROOT/"backend/app/security.py",
    ROOT/"frontend/src/App.tsx",
]
missing = [str(p) for p in required if not p.exists()]
if missing:
    print("MISSING:", *missing, sep="\n")
    sys.exit(1)
subprocess.run([sys.executable, "-m", "compileall", "-q", str(ROOT/"backend/app")], check=True)
print("Structural verification PASS")
