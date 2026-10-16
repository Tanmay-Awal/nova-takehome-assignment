"""Convenience runner for make grade on Windows and Unix alike.
Sets UTF-8 encoding and passes the current virtual environment python cleanly.
"""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main():
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    
    py = sys.executable.replace("\\", "/")
    harness_path = str(ROOT / "harness" / "harness.py").replace("\\", "/")
    harness_arg = f'"{py}" "{harness_path}"'
    
    cmd = [
        sys.executable,
        str(ROOT / "grader" / "run_grader.py"),
        "--harness", harness_arg,
        "--data", str(ROOT / "data" / "scenarios"),
        "--key", str(ROOT / "data" / "scenarios" / "answers"),
        "--mode", sys.argv[1] if len(sys.argv) > 1 else "both",
        "--out", str(ROOT / "report_card.json")
    ]
    
    p = subprocess.run(cmd, env=env)
    sys.exit(p.returncode)

if __name__ == "__main__":
    main()
