# docker_grader.py
import os, re, shutil, subprocess, tempfile
from pathlib import Path
from typing import Dict, Any
import shutil


GRADER_IMAGE = os.environ.get("GRADER_IMAGE", "foundations-grader:py312")
DOCKER_BIN = os.environ.get("DOCKER_BIN") or shutil.which("docker") or "/usr/bin/docker"

def run_pytest_in_docker(files: Dict[str, str], *, timeout_s: int = 10) -> Dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="foundations_grade_"))
    try:
        # Make mount traversable even under userns setups
        os.chmod(tmp, 0o755)

        for name, content in files.items():
            p = tmp / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

        cmd = [
            DOCKER_BIN, "run", "--rm",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--network", "none",
            "--cpus", "1",
            "--memory", "256m",
            "--pids-limit", "128",
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "-v", f"{tmp}:/work:rw",
            "-w", "/work",
            GRADER_IMAGE,
            "pytest", "-q", "--disable-warnings",
        ]

        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")

        def grab(pattern: str) -> int:
            m = re.search(pattern, out)
            return int(m.group(1)) if m else 0

        passed  = grab(r"(\d+)\s+passed")
        failed  = grab(r"(\d+)\s+failed")
        skipped = grab(r"(\d+)\s+skipped")
        errors  = grab(r"(\d+)\s+error")

        return {
            "exit_code": p.returncode,
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "errors": errors,
            "total": passed + failed + skipped + errors,
            "output": out.strip(),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

