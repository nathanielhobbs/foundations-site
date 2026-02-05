## 2. `int` vs `float`

Two core numeric types:
- `int` = whole numbers (…, -2, -1, 0, 1, 2, …)
- `float` = decimal numbers (3.14, 0.5, …)

### Division is the classic “gotcha”
- `/` is **true division** → result is a `float`
- `//` is **floor division** → result is an `int`
- `%` gives the remainder → result is an `int`

<button class="tryit" data-try="try02a">Try it: division types</button>
<script type="text/plain" id="try02a">
i = 7
j = 2

print(i / j)    # 3.5
print(i // j)   # 3
print(i % j)    # 1

print(type(i), type(i / j))
</script>

---

### Converting types (casting)
- `float(i)` turns an int into a float
- `int(x)` turns a float into an int by truncating toward 0

Example:

```py
int(3.9)   # 3
int(-3.9)  # -3
```

---

### Your task (for Check step)
Fill in:

- `true_div` as `i / j`
- `floor_div` as `i // j`
- `remainder` as `i % j`
- `as_float` as `float(i)`
- `trunc_int` as `int(i/j)`
