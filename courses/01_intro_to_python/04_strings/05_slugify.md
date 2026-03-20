## 5. Practice: slugify (URL-friendly titles)

We often turn titles into “slugs” for URLs.

Rules:
- lowercase
- strip leading/trailing spaces
- spaces become `-`
- keep only letters, digits, and `-`
- collapse multiple `-` into a single `-`
- no leading/trailing `-`

Example:
- `"  Intro to Python!!!  "` → `"intro-to-python"`

---

### Try it

<button class="tryit" data-try="try05a">Try it: a worked example</button>
<script type="text/plain" id="try05a">
def slugify(title):
    title = title.strip().lower()
    out = []
    prev_dash = False
    for ch in title:
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif ch.isspace() or ch == "-":
            if not prev_dash and out:
                out.append("-")
                prev_dash = True
        # else: drop punctuation
    if out and out[-1] == "-":
        out.pop()
    return "".join(out)

print(slugify("  Intro to Python!!!  "))
print(slugify("Data   Science 101"))
</script>

---

### Your task (for Check step)
Implement `slugify(title)` using the rules above.
