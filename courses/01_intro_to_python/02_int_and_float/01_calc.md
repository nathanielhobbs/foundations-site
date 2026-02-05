## 1. Python as a calculator

When you write arithmetic in Python, you’re writing **expressions**.
An expression is something Python can evaluate to a value.

Examples of expressions:
- `2 + 3`
- `10 / 4`
- `3 * (5 + 1)`

### Basic operators
- `+` add
- `-` subtract
- `*` multiply
- `/` divide (**always returns a float**)
- `//` floor division (drops the fractional part)
- `%` modulo (remainder)
- `**` exponent (power)

---

### Try it
<button class="tryit" data-try="try01a">Try it: basic arithmetic</button>
<script type="text/plain" id="try01a">
x = 8
y = 3

print(x + y)
print(x - y)
print(x * y)
print(x / y)   # float
print(x // y)  # int
print(x % y)   # int
print(x ** y)
</script>

---

### Your task (for Check step)
Pick any integers for `a` and `b`, then compute the five result variables
using the operators in the comments.

(You can print numbers to sanity-check, but avoid printing text.)
