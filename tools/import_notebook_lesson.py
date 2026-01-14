#!/usr/bin/env python3
import argparse, json
from pathlib import Path

import nbformat

def nb_to_prompt_md(nb_path: Path) -> str:
    nb = nbformat.read(nb_path, as_version=4)
    out = []
    for cell in nb.cells:
        if cell.cell_type == "markdown":
            out.append(cell.source.strip())
        elif cell.cell_type == "code":
            src = cell.source.rstrip()
            if src:
                out.append("```python\n" + src + "\n```")

            # include stdout (skip errors by default)
            text_chunks = []
            for o in cell.get("outputs", []):
                if o.get("output_type") == "stream" and o.get("name") == "stdout":
                    t = (o.get("text") or "").rstrip()
                    if t:
                        text_chunks.append(t)
                elif o.get("output_type") == "execute_result":
                    data = o.get("data") or {}
                    t = (data.get("text/plain") or "").rstrip()
                    if t:
                        text_chunks.append(t)

            if text_chunks:
                joined = "\n".join(text_chunks).rstrip()
                out.append("```text\n" + joined + "\n```")

    return "\n\n".join([x for x in out if x])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--course", required=True)
    ap.add_argument("--nb", required=True)
    ap.add_argument("--lesson", required=True, help="lesson folder name, e.g. 02_variables")
    ap.add_argument("--title", required=True)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    base = Path(__file__).resolve().parents[1]
    nb_path = Path(args.nb).resolve()
    lesson_dir = (base / "courses" / args.course / args.lesson)
    lesson_dir.mkdir(parents=True, exist_ok=True)

    prompt_md = nb_to_prompt_md(nb_path)
    (lesson_dir / "prompt.md").write_text(prompt_md + "\n", encoding="utf-8")

    # default starter (you can edit later or generate from tagged cells later)
    starter = (
        '"""\n'
        f'{args.title}\n\n'
        "Write code here.\n"
        '"""\n\n'
        "# Example:\n"
        "print('hello')\n"
    )
    (lesson_dir / "starter.py").write_text(starter, encoding="utf-8")

    # default empty tests (reading-only lesson)
    (lesson_dir / "tests_public").mkdir(exist_ok=True)
    (lesson_dir / "tests_hidden").mkdir(exist_ok=True)

    meta = {
        "title": args.title,
        "is_open": bool(args.open),
        "file": "student.py",
        "steps": [],
        "final_hidden_glob": "tests_hidden/*.py",
    }
    (lesson_dir / "lesson.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    print("Wrote lesson to:", lesson_dir)

if __name__ == "__main__":
    main()
