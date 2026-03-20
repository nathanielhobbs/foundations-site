## 1. Creating strings and basic cleanup

Strings store text. You can use single quotes `'...'` or double quotes `"..."`.

Useful basics:
- `len(s)` gives the number of characters
- `s.strip()` removes leading/trailing whitespace

---

### Try it

<button class="tryit" data-try="try01a">Try it: strings + strip</button>
<script type="text/plain" id="try01a">
name = "  Ada  "
print(name)
print(name.strip())
print(len(name), len(name.strip()))
</script>

---

### Your task (for Check step)
Implement `make_greeting(name)`:

- strip whitespace
- if empty after stripping, return `"Hello there!"`
- otherwise return `"Hello, <name>!"`
