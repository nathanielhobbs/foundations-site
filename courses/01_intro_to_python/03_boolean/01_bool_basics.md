## 1. True/False and `bool(...)`

The boolean type (`bool`) has only two values:

- `True`
- `False`

`bool(x)` converts **any** value to a boolean using Python’s “truthiness” rules.

---

### Try it

<button class="tryit" data-try="try01a">Try it: bool conversion</button>
<script type="text/plain" id="try01a">
values = [0, 1, -3, "", "hi", [], [1], None]
for v in values:
    print(v, "->", bool(v))
</script>

---

### Your task (for Check step)
Write `as_bool(x)` that returns the boolean value of `x`.
