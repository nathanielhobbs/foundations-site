## 4. Truthiness and input checking

In conditions, Python treats many values as “falsy”:

- `0`, `0.0`
- `""` (empty string)
- empty containers like `[]`, `{}`, `()`
- `None`

Everything else is “truthy”.

---

### Try it

<button class="tryit" data-try="try04a">Try it: truthy vs falsy</button>
<script type="text/plain" id="try04a">
values = [0, 1, "", "hi", [], [1], None, {}, {"x": 1}]
for v in values:
    if v:
        print(v, "is truthy")
    else:
        print(v, "is falsy")
</script>

---

### Your task (for Check step)
Implement `nonempty(s)`:

- return True only if `s` is a string
- and after stripping spaces, it is not empty
