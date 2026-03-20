## 5. Practice: safe division

Division by zero crashes:

```py
10 / 0  # ZeroDivisionError
```

A common pattern is to **check first**.

---

### Try it

<button class="tryit" data-try="try05a">Try it: guarding a division</button>
<script type="text/plain" id="try05a">
a = 10
b = 0

if b != 0:
    print(a / b)
else:
    print("can't divide by zero")
</script>

---

### Your task (for Check step)
Implement `safe_div(a, b)`:

- if `b` is zero, return `None`
- otherwise return `a / b`
