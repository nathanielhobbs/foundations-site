## 1. REPL vs script: expressions and `print()`

Python has two common ways to run code:

### A) The interpreter (Read-Eval-Print Loop aka REPL)
- You type code **one line at a time**
- Python runs it immediately
- If you type an **expression** (like `2 + 3`), Python shows the result

Example REPL session:

```
>>> 2 + 3
5
>>> x = 10
>>> x * 2
20
```

You can test out the REPL in the [Python Sandbox](https://foundations.hobbsresearch.com/sandbox)

### B) A `.py` file (a script)
- Python runs the file **top-to-bottom**
- A file does **not** automatically show expression results
- To see output, you usually use `print(...)`

Example script:

```py
x = 10
x * 2          # nothing shows
print(x * 2)   # this shows
```

---

### Try it
<button class="tryit" data-try="repl_try1">Try it: expressions + print</button>
<script type="text/plain" id="repl_try1">
x = 10
x * 2
print(x * 2)
</script>

---

### Your task (for Check step)
Fill in `result_add`, `result_mul`, and `result_div` below.
