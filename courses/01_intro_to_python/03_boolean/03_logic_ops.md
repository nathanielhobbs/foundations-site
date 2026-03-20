## 3. Logical operators (`and`, `or`, `not`)

- `A and B` is True only if both are True
- `A or B` is True if either is True
- `not A` flips True/False

These operators **short-circuit**:
- `A and B` does not evaluate `B` if `A` is False
- `A or B` does not evaluate `B` if `A` is True

---

### Try it

<button class="tryit" data-try="try03a">Try it: and/or/not</button>
<script type="text/plain" id="try03a">
total = 80
is_member = True

print(total >= 100 or is_member)
print(not is_member)
print((total >= 100) and is_member)
</script>

---

### Your task (for Check step)
Implement `should_apply_discount(total, is_member)`:

- If `total >= 100`, discount applies
- If `is_member` is True, discount applies (even if total is smaller)
- Otherwise, no discount
