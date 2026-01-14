#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, json, re, base64

COURSE = "getting_started"
BASE = Path("courses") / COURSE

def slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s_-]", "", s)
    s = re.sub(r"[\s_-]+", "_", s).strip("_")
    return s or "step"

def b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")

def write(path: Path, text: str, force: bool):
    if path.exists() and not force:
        return
    path.write_text(text, encoding="utf-8")

def write_lesson(lesson_slug: str, title: str, steps: list[dict], force: bool):
    root = BASE / lesson_slug
    root.mkdir(parents=True, exist_ok=True)

    write(root / "prompt.md", f"# {title}\n\nClick a step on the left.\n", force)

    lesson = {"title": title, "is_open": True, "steps": []}
    first_starter_path: Path | None = None

    for i, st in enumerate(steps, start=1):
        n = f"{i:02d}"
        step_slug = f"{n}_{slug(st['title'])}"
        md_name = f"{step_slug}.md"
        py_name = f"{step_slug}.py"

        md_path = root / md_name
        py_path = root / py_name

        write(md_path, st["md"].rstrip() + "\n", force)
        write(py_path, st["py"].rstrip() + "\n", force)

        if first_starter_path is None:
            first_starter_path = py_path

        lesson["steps"].append({
            "id": i,
            "title": f"{i}. {st['title']}",
            "kind": "info",
            "prompt_file": md_name,
            "starter_file": py_name,
            "cmd_hint": st.get("cmd_hint", "python main.py"),
        })

    write(root / "lesson.json", json.dumps(lesson, indent=2) + "\n", force)

    # your route requires starter.py
    if first_starter_path:
        write(root / "starter.py", first_starter_path.read_text(encoding="utf-8"), True)
    else:
        write(root / "starter.py", "# (empty)\n", True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    args = ap.parse_args()

    BASE.mkdir(parents=True, exist_ok=True)

    # -------- 00 Terminal basics --------
    write_lesson("00_terminal", "Terminal basics", [
        {
            "title": "What a terminal is",
            "cmd_hint": "pwd",
            "md": """## What a terminal is

A **terminal** is a text-based way to interact with your computer.

- You type a command
- A program runs
- You see output

Most commands follow a pattern like:

~~sh
command --options arguments
~~

On macOS/Linux you usually use **bash** or **zsh**.
On Windows you might use **PowerShell**, **Command Prompt**, or **Git Bash**.
""",
            "py": "# (no python yet)\n",
        },
        {
            "title": "Shells: bash vs zsh vs PowerShell",
            "cmd_hint": "echo hello",
            "md": """## Shells: bash vs zsh vs PowerShell

A **shell** is the program interpreting what you type.

- **bash**: common (Linux/servers)
- **zsh**: default on many macOS installs
- **PowerShell**: Windows-native (different syntax)
- **Git Bash**: bash-like shell on Windows (good for class consistency)

For this course, we’ll try to keep commands compatible with **bash** when possible.
""",
            "py": "# (no python yet)\n",
        },
        {
            "title": "Prompt symbols ($ vs % vs > vs >>>)",
            "cmd_hint": "python",
            "md": """## Prompt symbols ($ vs % vs > vs >>>)

Prompts are visual hints.

- `$` or `%` usually means a **shell** (bash/zsh)
- `>` often appears in Windows shells
- `>>>` means the **Python interpreter (REPL)**

The prompt is not part of the command. Don’t type it when copying.
""",
            "py": "# (no python yet)\n",
        },
        {
            "title": "Commands you’ll actually use",
            "cmd_hint": "mkdir demo && cd demo && pwd",
            "md": """## Commands you’ll actually use

~~sh
pwd        # where am I?
ls         # list files
cd folder  # change directory
mkdir dir  # make directory
cp a b     # copy
mv a b     # move/rename
rm file    # delete (careful)
~~

Try:

~~sh
mkdir demo
cd demo
pwd
~~
""",
            "py": "# (no python yet)\n",
        },
    ], args.force)

    # -------- 01 Windows Git Bash --------
    write_lesson("01_windows_git_bash", "Windows: Git Bash setup", [
        {
            "title": "Install Git for Windows",
            "cmd_hint": "git --version",
            "md": """## Install Git for Windows

Windows users: install **Git for Windows** so you have **Git Bash**.

After installing, open **Git Bash** from the Start menu.

Verify:

~~sh
git --version
~~
""",
            "py": "# (no python yet)\n",
        },
        {
            "title": "Find your home folder",
            "cmd_hint": "pwd",
            "md": """## Find your home folder

In Git Bash:

~~sh
pwd
ls
~~

Your home folder often looks like:

~~text
/c/Users/YourName
~~

That’s normal in Git Bash.
""",
            "py": "# (no python yet)\n",
        },
        {
            "title": "Copy/paste + gotchas",
            "cmd_hint": "ls",
            "md": """## Copy/paste + gotchas

In Git Bash:
- Paste is usually right-click (or Shift+Insert)
- Copy is usually Ctrl+Insert (or right-click)

Common gotcha:
- Windows uses different line endings sometimes. If it matters, we’ll fix it.
""",
            "py": "# (no python yet)\n",
        },
    ], args.force)

    # -------- 02 Miniconda --------
    write_lesson("02_miniconda", "Miniconda install (Mac + Windows)", [
        {
            "title": "Why conda (short version)",
            "cmd_hint": "conda --version",
            "md": """## Why conda (short version)

Conda lets us give everyone the *same* Python + packages.

You will:
1) Install Miniconda once  
2) Create one environment for this course  
3) Use it all semester
""",
            "py": "# (no python yet)\n",
        },
        {
            "title": "Windows install (easy path)",
            "cmd_hint": "python --version",
            "md": """## Windows install (easy path)

1) Install **Miniconda (Python 3.x)** for Windows  
2) Open **Miniconda Prompt** (Start menu)

Verify:

~~sh
conda --version
python --version
~~
""",
            "py": "# (no python yet)\n",
        },
        {
            "title": "Mac install (easy path)",
            "cmd_hint": "python --version",
            "md": """## Mac install (easy path)

1) Install **Miniconda (Python 3.x)** for macOS  
2) Open **Terminal**

Verify:

~~sh
conda --version
python --version
~~
""",
            "py": "# (no python yet)\n",
        },
        {
            "title": "Create + activate the course environment",
            "cmd_hint": "conda create -n foundations python=3.12 -y",
            "md": """## Create + activate the course environment

~~sh
conda create -n foundations python=3.12 -y
conda activate foundations
python --version
~~

If `conda activate` fails on macOS, close/reopen Terminal and try again.
""",
            "py": "# (no python yet)\n",
        },
    ], args.force)

    # -------- 03 Python interpreter --------
    try_code = "x = 10\nprint(x * 3)\n"
    write_lesson("03_python_interpreter", "The Python interpreter", [
        {
            "title": "Interpreter vs script",
            "cmd_hint": "python main.py",
            "md": """## Interpreter vs script

Two ways you’ll run Python:

### 1) Interpreter (REPL)
You type Python and it runs immediately.
You’ll usually see:

~~text
>>>
~~

### 2) Script
You run a file:

~~sh
python myfile.py
~~
""",
            "py": "print('Hello from a script.')\n",
        },
        {
            "title": "Prompts: $ / % / >>>",
            "cmd_hint": "python",
            "md": """## Prompts: $ / % / >>>

- `$` / `%` = your **shell**
- `>>>` = the **Python interpreter**

Example:

~~text
$ python
>>> 2 + 2
4
>>> exit()
$
~~
""",
            "py": "print('Shell prompt is not Python; >>> is Python.')\n",
        },
        {
            "title": "Try it buttons",
            "cmd_hint": "python main.py",
            "md": f"""## Try it buttons

Click this:

<button class="tryit" data-code-b64="{b64(try_code)}">Try it: load code</button>

Then press **Run**.
""",
            "py": try_code,
        },
    ], args.force)

    # -------- 04 Types --------
    t1 = "x = 5\nprint(type(x))\n"
    t2 = "s = 'hello'\nprint(type(s))\nprint(s.upper())\n"
    write_lesson("04_types", "Types, classes, objects", [
        {
            "title": "Everything is an object",
            "cmd_hint": "python main.py",
            "md": f"""## Everything is an object

In Python, values are **objects**.
Each object has a **type**.

<button class="tryit" data-code-b64="{b64(t1)}">Try it</button>
""",
            "py": t1,
        },
        {
            "title": "Classes are like factories",
            "cmd_hint": "python main.py",
            "md": """## Classes are like factories

A class is like a factory that produces objects.

~~py
x = int("12")
y = float("3.5")
print(x, y)
~~
""",
            "py": 'x = int("12")\ny = float("3.5")\nprint(x, y)\n',
        },
        {
            "title": "Methods live on objects",
            "cmd_hint": "python main.py",
            "md": f"""## Methods live on objects

Objects come with built-in behavior (methods).

<button class="tryit" data-code-b64="{b64(t2)}">Try it</button>
""",
            "py": t2,
        },
    ], args.force)

    # -------- 05 Numbers --------
    n1 = "a = 7\nb = 2\nprint(a / b)\nprint(a // b)\nprint(a % b)\n"
    n2 = "x = 0.1 + 0.2\nprint(x)\nprint(round(x, 2))\n"
    write_lesson("05_numbers", "Numbers (int, float)", [
        {
            "title": "int vs float",
            "cmd_hint": "python main.py",
            "md": f"""## int vs float

- `int` = whole numbers
- `float` = decimals

<button class="tryit" data-code-b64="{b64(n1)}">Try it: / vs // vs %</button>
""",
            "py": n1,
        },
        {
            "title": "Rounding (practical)",
            "cmd_hint": "python main.py",
            "md": f"""## Rounding (practical)

Floats are approximate.

<button class="tryit" data-code-b64="{b64(n2)}">Try it</button>
""",
            "py": n2,
        },
    ], args.force)

    # -------- 06 Operators --------
    o1 = "a = 7\nb = 3\nprint(a+b, a-b, a*b, a/b, a//b, a%b, a**b)\n"
    o2 = "print(2 + 3 * 4)\nprint((2 + 3) * 4)\n"
    o3 = "x = 5\nprint(x > 3)\nprint(x == 5)\n\nis_raining = False\nhas_umbrella = True\nprint(is_raining or has_umbrella)\n"
    write_lesson("06_operators", "Operators (math + comparisons + boolean)", [
        {
            "title": "Arithmetic operators",
            "cmd_hint": "python main.py",
            "md": f"""## Arithmetic operators

<button class="tryit" data-code-b64="{b64(o1)}">Try it</button>
""",
            "py": o1,
        },
        {
            "title": "Precedence",
            "cmd_hint": "python main.py",
            "md": f"""## Precedence

<button class="tryit" data-code-b64="{b64(o2)}">Try it</button>
""",
            "py": o2,
        },
        {
            "title": "Comparisons + boolean logic",
            "cmd_hint": "python main.py",
            "md": f"""## Comparisons + boolean logic

<button class="tryit" data-code-b64="{b64(o3)}">Try it</button>
""",
            "py": o3,
        },
    ], args.force)

    print(f"OK: created/updated courses/{COURSE}")

if __name__ == "__main__":
    main()
