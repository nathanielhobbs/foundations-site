## 1. Values, variables, and `type()`

### Three words you’ll use constantly
- **Value**: the actual data (like `5`, `3.14`, `"hello"`)
- **Type**: what kind of value it is (`int`, `float`, `str`, `bool`, …)
- **Variable**: a **name** that points at a value

When you write:

```py
x = 5
```

you are telling Python: “make the name `x` refer to the value `5`”.

---

### Types matter
Types control what operations make sense.

- numbers can be added: `5 + 2`
- strings can be combined: `"hi" + "there"`
- but mixing types can cause errors (we’ll see that soon)

---

### `type(...)`
Use `type(x)` to ask Python what type a value is.

<button class="tryit" data-try="types_try1">Try it: type()</button>
<script type="text/plain" id="types_try1">
print(type(5))
print(type(3.14))
print(type("hello"))
print(type(True))     # booleans exist even if we postpone them
</script>

---

### Your task (for Check step)
Create four variables with these types:

- `a` is an `int`
- `b` is a `float`
- `c` is a `str`
- `d` is a `bool`

(No need to print anything for the autograder — just set the variables.)

---

## 2. `type()` vs `isinstance()` (and a quick intro to classes)

### Everything is an object (preview)
In Python, *everything is an object* — numbers, strings, lists, functions, etc.

An object has a **type** (also called its **class**). You’ll learn classes properly later, but for now:

- a **class** is like a “blueprint” (e.g., `int`, `str`, `list`)
- an **instance** is a specific object made from that class (e.g., `5` is an instance of `int`)

---

### The key difference
- `type(x)` checks the **exact** class of `x`.
- `isinstance(x, T)` checks whether `x` is an instance of `T` **or any subclass of `T`**.

This matters because Python uses inheritance (we’ll go deeper later). For example, many custom classes can be “kinds of” a base class.

---

### Try it: exact match vs subclass match
<button class="tryit" data-try="types_try2">Try it: isinstance()</button>
<script type="text/plain" id="types_try2">
class Vehicle:
    pass

class Truck(Vehicle):
    pass

my_truck = Truck()

print(type(my_truck) is Truck)           # exact type check
print(type(my_truck) is Vehicle)         # False (not exact)
print(isinstance(my_truck, Truck))       # True
print(isinstance(my_truck, Vehicle))     # True (subclass counts)
</script>

---

### Rule of thumb
- Use **`isinstance`** when you want “is this a kind of X?” (most type-checking)
- Use **`type`** when you specifically need the **exact** class (rare)

---

### Your task (optional)
Make a class `Animal`, then a class `Dog(Animal)`. Create a `Dog()` object and confirm:

- `type(d) is Dog` is `True`
- `type(d) is Animal` is `False`
- `isinstance(d, Dog)` is `True`
- `isinstance(d, Animal)` is `True`

