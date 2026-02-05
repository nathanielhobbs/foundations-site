## 2. Converting between types

Sometimes you need to convert (cast) a value.

Common converters:
- `int(x)` → integer
- `float(x)` → float
- `str(x)` → string

Examples:

```py
int(3.9)        # 3   (truncates toward 0)
float(3)        # 3.0
str(3.5)        # "3.5"
```

**Important:** converting text only works if the text looks like a number.

<button class="tryit" data-try="types_try2">Try it: conversions</button>
<script type="text/plain" id="types_try2">
print(int(3.9))
print(float(3))
print(str(3.5))

print(int("19"))
print(float("2.5"))

# print(int("2.5"))   # ValueError (can't parse "2.5" as an int)
</script>

---

### Your task (for Check step)
You are given two strings:

- `x_str = "19"`
- `y_str = "2.5"`

Convert them and compute:

- `x` as an `int`
- `y` as a `float`
- `sum_xy = x + y` (a float)
- `y_trunc = int(y)` (truncates)
