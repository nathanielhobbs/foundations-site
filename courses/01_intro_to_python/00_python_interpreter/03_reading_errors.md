## 3. Reading errors: `NameError` and `TypeError`

When Python can’t run your code, it prints an **error message** plus a **traceback**.

Two common beginner errors:

### `NameError`
You used a name that doesn’t exist (usually a typo or wrong order).

### `TypeError`
You tried to do an operation on two things that don’t “fit”.

Example:

```py
"3" + 4        # TypeError (string + number)
```

Fix by converting:

```py
int("3") + 4   # 7
```

---

### Try it
<button class="tryit" data-try="repl_try3">Try it: TypeError and fix</button>
<script type="text/plain" id="repl_try3">
print("3" + "4")       # ok (string + string)
# print("3" + 4)       # TypeError
print(int("3") + 4)    # fix
</script>

---

### Your task (for Check step)
In the starter file:
- `items` is a string like `"3"`
- convert it to an integer
- compute `total = items * price_each`
