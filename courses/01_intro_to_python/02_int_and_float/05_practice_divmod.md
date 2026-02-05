## 5. Practice: `//` and `%` (time conversion)

If you have a number of minutes, you can convert it into hours + leftover minutes:

- `hours = minutes // 60`
- `mins  = minutes % 60`

Example:

<button class="tryit" data-try="try05a">Try it</button>
<script type="text/plain" id="try05a">
minutes = 135
hours = minutes // 60
mins = minutes % 60

print(hours)  # 2
print(mins)   # 15
</script>

---

### Your task (for Check step)
Pick any positive integer `minutes`, then compute `hours` and `mins`.
