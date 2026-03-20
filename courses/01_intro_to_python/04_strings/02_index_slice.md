## 2. Indexing, slicing, and empty strings

- `s[0]` is the first character
- `s[-1]` is the last character
- `s[a:b]` is a slice (b is not included)

Strings are **immutable**: you can't change a character in-place.

---

### Try it

<button class="tryit" data-try="try02a">Try it: indexing + slicing</button>
<script type="text/plain" id="try02a">
s = "Python"
print(s[0], s[-1])
print(s[1:4])
print(s[:2])
print(s[2:])
</script>

---

### Your task (for Check step)
Implement `first_last(s)` returning `(first, last)`.

- If `s` is empty, return `("", "")`.
