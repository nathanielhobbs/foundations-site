## 5. Practice: combining helpers

In real code, you often write a couple small helpers and then combine them.

Your goal: implement `analyze_text(s)` returning a tuple:

`(num_chars, num_words, avg_word_len)`

Rules:
- `num_chars` is `len(s)`
- `num_words` is the number of words in `s.split()`
- `avg_word_len` is the average word length
- if there are no words, `avg_word_len` should be `0.0`

---

### Try it

<button class="tryit" data-try="try05a">Try it: example output</button>
<script type="text/plain" id="try05a">
def analyze_text(s):
    words = s.split()
    num_chars = len(s)
    if len(words) == 0:
        return (num_chars, 0, 0.0)

    total = 0
    for w in words:
        total += len(w)
    return (num_chars, len(words), total / len(words))

print(analyze_text("data science"))
print(analyze_text("   "))
</script>

---

### Your task (for Check step)
Implement `analyze_text(s)` exactly as described.
