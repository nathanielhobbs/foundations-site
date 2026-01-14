#!/usr/bin/env python3
import argparse, json, re
from pathlib import Path

def slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "_", s)
    return s.strip("_") or "step"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--course", required=True)
    ap.add_argument("--lesson", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--steps-json", required=True, help='JSON array of step titles')
    ap.add_argument("--root", default="courses")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    steps = json.loads(args.steps_json)
    if not isinstance(steps, list) or not all(isinstance(x, str) for x in steps):
        raise SystemExit("--steps-json must be a JSON array of strings")

    root = Path(args.root) / args.course / args.lesson
    root.mkdir(parents=True, exist_ok=True)

    lesson = {
        "title": args.title,
        "is_open": True,
        "steps": []
    }

    # top-level prompt
    (root / "prompt.md").write_text(
        f"# {args.title}\n\nClick a step on the left.\n\nUse **Run** to execute. Use **Check step** to mark complete.\n",
        encoding="utf-8"
    )

    # always provide starter.py so your route doesn't 500
    first_starter_path = None

    for i, title in enumerate(steps, start=1):
        n = f"{i:02d}"
        base = f"{n}_{slug(title)}"
        md_name = f"{base}.md"
        py_name = f"{base}.py"

        md_path = root / md_name
        py_path = root / py_name

        if args.force or not md_path.exists():
            md_path.write_text(
                f"## {i}. {title}\n\n"
                f"Explain this step here.\n\n"
                "```py\n"
                "# put a small example here\n"
                "```\n",
                encoding="utf-8"
            )
        if args.force or not py_path.exists():
            py_path.write_text(
                f"# Step {i}: {title}\n\n"
                "# put runnable code here\n",
                encoding="utf-8"
            )

        if first_starter_path is None:
            first_starter_path = py_path

        lesson["steps"].append({
            "id": i,
            "title": f"{i}. {title}",
            "kind": "info",
            "prompt_file": md_name,
            "starter_file": py_name,
            "cmd_hint": "python main.py"
        })

    (root / "lesson.json").write_text(json.dumps(lesson, indent=2), encoding="utf-8")

    # keep route happy
    if first_starter_path:
        (root / "starter.py").write_text(first_starter_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"OK: wrote {root}")

if __name__ == "__main__":
    main()
