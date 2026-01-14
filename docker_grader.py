# docker_grader.py
import os, re, shutil, subprocess, tempfile
from pathlib import Path
from typing import Dict, Any
import shutil


GRADER_IMAGE = os.environ.get("GRADER_IMAGE", "foundations-grader:py312")
DOCKER_BIN = os.environ.get("DOCKER_BIN") or shutil.which("docker") or "/usr/bin/docker"


def run_python_in_docker(code: str, timeout_s: int = 3, args=None) -> dict:
    import os, tempfile, subprocess, shutil

    args = args or []

    tmpdir = tempfile.mkdtemp(prefix="pyexec_")
    try:
        os.chmod(tmpdir, 0o755)

        main_py = os.path.join(tmpdir, "main.py")
        with open(main_py, "w", encoding="utf-8") as f:
            f.write(code or "")
        os.chmod(main_py, 0o644)

        docker_bin = os.environ.get("DOCKER_BIN", "/usr/bin/docker")
        image = os.environ.get("GRADER_IMAGE", "foundations-grader:py312")

        inner_cmd = ["python", "main.py", *args]
        cmd = [
            docker_bin, "run", "--rm",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--network", "none",
            "--cpus=1",
            "--memory=256m",
            "--pids-limit=128",
            "--security-opt", "no-new-privileges",
            "--cap-drop=ALL",
            "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=64m",
            "-v", f"{tmpdir}:/work:ro",
            "-w", "/work",
            image,
            *inner_cmd,
        ]

        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        return {
            "exit_code": p.returncode,
            "stdout": p.stdout or "",
            "stderr": p.stderr or "",
            "cmd_display": "$ " + " ".join(inner_cmd),
        }

    except subprocess.TimeoutExpired as e:
        return {
            "exit_code": 124,
            "stdout": (e.stdout or "") if getattr(e, "stdout", None) else "",
            "stderr": ((e.stderr or "") if getattr(e, "stderr", None) else "") + "\nTimed out.\n",
            "cmd_display": "$ python main.py " + " ".join(args),
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


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

