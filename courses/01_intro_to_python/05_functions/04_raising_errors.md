## 4. Raising errors for bad input

Sometimes the best behavior for “bad input” is to stop immediately.

Example:

```py
if len(nums) == 0:
    raise ValueError("nums must be non-empty")
```

---

### Try it

<button class="tryit" data-try="try04a">Try it: mean with an error</button>
<script type="text/plain" id="try04a">
def mean(nums):
    if len(nums) == 0:
        raise ValueError("nums must be non-empty")
    return sum(nums) / len(nums)

print(mean([1, 2, 3]))
</script>

---

### Your task (for Check step)
Implement `mean(nums)`:

- raise `ValueError` if `nums` is empty
- otherwise return the average (as a float)
