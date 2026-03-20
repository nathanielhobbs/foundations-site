## 3. String methods

A few methods you’ll use constantly:

- `s.lower()` / `s.upper()`
- `s.replace(old, new)`
- `s.count(sub)` (counts non-overlapping occurrences)

---

### Try it

<button class="tryit" data-try="try03a">Try it: methods</button>
<script type="text/plain" id="try03a">
s = "  Data Science  "
print(s.strip().lower())
print("banana".count("na"))
print("banana".replace("na", "NA"))
</script>

---

### Your task (for Check step)
Implement `count_vowels(s)` counting vowels a/e/i/o/u (case-insensitive).
