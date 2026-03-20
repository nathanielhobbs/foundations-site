## 3. Return values vs side effects

Some functions **return a new value**. Others **modify** an input (a side effect).

Lists are mutable, so it's easy to accidentally modify one.

---

### Try it

<button class="tryit" data-try="try03a">Try it: returning a new list</button>
<script type="text/plain" id="try03a">
def add_item_new(lst, item):
    return lst + [item]

a = [1, 2]
b = add_item_new(a, 3)
print("a:", a)
print("b:", b)
</script>

---

### Your task (for Check step)
Write `append_new(lst, item)` that returns a **new list** with `item` appended,
without changing `lst`.
