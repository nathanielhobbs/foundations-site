## 3. Types help you avoid “nonsense” operations

A classic beginner mistake is mixing numbers and strings.

Example:

```py
total = 3 * 1.25
line = "Total: $" + total     # TypeError (string + number)
```

Fix it by converting the number to a string:

```py
line = "Total: $" + str(total)
```

---

### Try it
<button class="tryit" data-try="types_try3">Try it: building a message</button>
<script type="text/plain" id="types_try3">
items = 3
price_each = 1.25
total = items * price_each

line = "Total: $" + str(total)
print(line)
</script>

---

### Your task (for Check step)
Compute:

- `total = items * price_each`
- `line = msg + str(total)`

Use the variables already provided in the starter.
