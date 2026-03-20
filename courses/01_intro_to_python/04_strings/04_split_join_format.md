## 4. Split, join, and formatting

- `s.split()` breaks a string into a list of words (by whitespace)
- `sep.join(items)` joins strings together
- f-strings embed values: `f"Total: {total:.2f}"`

---

### Try it

<button class="tryit" data-try="try04a">Try it: split + join + f-strings</button>
<script type="text/plain" id="try04a">
line = "a,b,c"
parts = line.split(",")
print(parts)
print("|".join(parts))

total = 12.5
print(f"Total: ${total:.2f}")
</script>

---

### Your task (for Check step)
Implement `csv_row(values)`:

- `values` is a list of items (numbers/strings/etc.)
- return a single string with items joined by commas
- convert each item to a string

Example: `csv_row([1, "Ada", 3.5])` → `"1,Ada,3.5"`
