## 4. Practice: total with tax + tip

A common real-world pattern:

1. start with a base amount
2. compute add-ons with multiplication (tax, tip, discount, …)
3. add everything

Worked example:

<button class="tryit" data-try="try04a">Try it: a worked example</button>
<script type="text/plain" id="try04a">
bill = 20.0
tax_rate = 0.06625
tip_rate = 0.18

tax = bill * tax_rate
tip = bill * tip_rate
total = bill + tax + tip

print(total)
</script>

---

### Your task (for Check step)
Fill in `tax`, `tip`, and `total` in the starter file so the math is correct.
