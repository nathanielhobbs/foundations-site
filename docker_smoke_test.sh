#!/bin/bash

set -a; source .env; set +a

python - <<'PY'
from docker_grader import run_pytest_in_docker

res = run_pytest_in_docker({
  "student.py": "def add(a,b):\n    return a+b\n",
  "test_hw.py": "from student import add\n\ndef test_add():\n    assert add(2,2)==4\n"
})

print(res["exit_code"], res["passed"], res["failed"], res["output"])
PY

