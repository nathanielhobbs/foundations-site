## 2. Parameters, defaults, and keyword arguments

- Parameters are the names in the `def` line
- Arguments are the values you pass when calling
- Defaults let callers omit an argument

---

### Try it

<button class="tryit" data-try="try02a">Try it: default parameters</button>
<script type="text/plain" id="try02a">
def tax(total, rate=0.06625):
    return total * rate

print(tax(100))
print(tax(100, rate=0.07))
</script>

---

### Your task (for Check step)
Implement `clamp(x, lo=0, hi=1)`:

- return `lo` if `x < lo`
- return `hi` if `x > hi`
- otherwise return `x`
