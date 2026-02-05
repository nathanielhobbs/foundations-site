## 3. Operators + precedence

Python follows a standard **order of operations** (precedence):

1. parentheses: `( ... )`
2. exponent: `**`
3. multiply/divide: `*`, `/`, `//`, `%`
4. add/subtract: `+`, `-`

<button class="tryit" data-try="op_prec">Try it: precedence</button>
<pre id="op_prec"><code>print(2 + 3 * 4)       # 14
print((2 + 3) * 4)     # 20
print(2 ** 3 * 2)      # 16  (power first)
</code></pre>

---

### Your task (for Check step)
Set:

- `expr1` to 14 using `2 + 3 * 4`
- `expr2` to 20 using `(2 + 3) * 4`
- `fd` to `7 // 2`
- `mod` to `7 % 2`
- `power` to `2 ** 5`
