## 2. Code runs top-to-bottom

In a file, Python runs the first line, then the second line, then the third line…

That means:

- You must assign a variable **before** you use it.
- If you try to use a name too early, you’ll get a **NameError**.

Example:

```py
total = price * qty   # NameError (price not defined yet)
price = 1.50
qty = 4
```

Fix by putting the assignments first:

```py
price = 1.50
qty = 4
total = price * qty
```

---

### Try it
<button class="tryit" data-try="repl_try2">Try it: top-to-bottom</button>
<script type="text/plain" id="repl_try2">
# Run this once as-is, then fix the order.
total = price * qty
price = 1.50
qty = 4
print(total)
</script>

---

### Your task (for Check step)
The starter file has the same “wrong order” bug.
Reorder the lines so the file runs and `total` is correct.
