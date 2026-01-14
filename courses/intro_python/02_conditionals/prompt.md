# Contitionals (if/elif/else)

Contitionals are words in the language that allows parts of the program to run depending on the conditions.

The full syntax is
```python

if <statment is True>: # check boolean statement
    # code block
elif <another statement is True>: # check another boolean statement
    # code block
elif ...
else: # the default if all else fails
    # code block
```

```python
x = -10
if x > 0:
    print('positive')
else:
    print('negative')
```

```text
negative
```

```python
x = 50

if x > 100:
    print('big')
elif x > 0:
    print('medium')
else:
    print('small')
```

```text
medium
```

```python
x = 3
if x % 2 == 0:
    print('even')
else:
    print('odd')
```

```text
odd
```

```python
print(5/2)
print(5//2)
print(5%2)
```

```text
2.5
2
1
```

```python
def roundUp(x,y):
    left_over = x % y
    if left_over > 0:
        return  x//y + 1
    else:
        return x//y

print(roundUp(5,2))
print(roundUp(4,2))
```

```text
3
2
```

## Nested conditionals and their (and/or) equivalent

There's mulitple valid ways to reach a conlusion of True/False with multiple "parts" of the statement.

```python
def xIsSmallAndeEven(x):
    if x < 100:
        if x % 2 == 0:
            print(str(x)+' is small and also even')

xIsSmallAndeEven(4)
xIsSmallAndeEven(5)
xIsSmallAndeEven(1024)
```

```text
4 is small and also even
```

```python
def xIsSmallAndePos(x):
    if x < 100 and x % 2 == 0:
            print(str(x)+' is small and also even')

xIsSmallAndePos(4)
xIsSmallAndePos(5)
xIsSmallAndePos(1024)
```

```text
4 is small and also even
```

```python
def xIsSmallAndePos(x):
        if x < 100 and not x % 2 == 1:
            print(str(x)+' is small and also even')

xIsSmallAndePos(4)
xIsSmallAndePos(5)
xIsSmallAndePos(1024)
```

```text
x is small and also even
```

```python
def xIsSmallAndePos(x):
        if x < 100 and not x % 2:
            print(str(x)+' is small and also even')

xIsSmallAndePos(4)
xIsSmallAndePos(5)
xIsSmallAndePos(1024)
```

```text
4 is small and also even
```

## python is a "truthy" language

This means that the types in python can *sometimes* intermingle

```python
print(1 + True) # "behaves like" 1 + 1

print(1 == True) # "behaves like" True == True

print(0==False) # "behaves like" False == False

print(''==False) # "behaves like" ....
```

```text
2
True
True
False
```

```python
def xIsSmallOrPos(x):
    if x < 100:
        print('x is small')
    if x % 2 == 0:
        print('x is positive')
        

xIsSmallOrPos(4)
xIsSmallOrPos(5)
xIsSmallOrPos(1024)
```

```text
x is small
x is positive
x is small
x is positive
```

```python
def xIsSmallOrPos(x):
    if x < 100 or x % 2 == 0:
        print('x is small or positive (not sure which)')        

xIsSmallOrPos(4)
xIsSmallOrPos(5)
xIsSmallOrPos(1024)
```

```text
x is small or positive (not sure which)
x is small or positive (not sure which)
x is small or positive (not sure which)
```

# Single line if/else

if A:
   line_a
else:
    line_b

can be compressed to

line_a if A else line_b

```python
x = 0
if x > 10:
    print('big')
else:
    print('small')
```

```text
small
```

```python
x = 0

print('big') if x > 10 else print('small')

print('big' if x>10 else 'small')
```

```text
small
small
```

# Practice

Write a function called "smallPowerOfTwo(x)" which takes a single integer as input, x, and returns the string "small power of 2" if x is 2, 4, 8, 16, 32, 64, 128, or 256.  For all other x, the function should output "not small power of 2".

```python
def smallPowerOfTwo(x: int) -> str:
    if x == 2 or x == 4 or x == 8 or x ==16 or x == 32 or x == 64 or x == 128 or x == 256 and x%2==0:
        print('small power of two')
    else:
        print('not small power of two')
```

```python
def smallPowerOfTwo(x: int) -> str:
    if x == 2 or x == 4 or x == 8 or x ==16 or x == 32 or x == 64 or x == 128 or x == 256:
        print('small power of two')
    else:
        print('not small power of two')
```

```python
def smallPowerOfTwo(x: int) -> str:
    if x == 2:
        print('small power of two')
    elif x == 4:
        print('small power of two')
    elif x == 8:
        print('small power of two')
    elif x == 16:
        print('small power of two')
    elif x == 32:
        print('small power of two')
    elif x == 64:
        print('small power of two')
    elif x == 128:
        print('small power of two')
    elif x == 256:
        print('small power of two')
    else:
        print('not small power of two')
```

```python
def smallPowerOfTwo(x: int) -> str:
    if x in [2,4,8,16,32,64,128,256]:
        print('small power of two')
    else:
        print('not small power of two')
```

## Single line conditionals

```python
x = 10

if x > 0:
    sign = 'positive'
else:
    sign = 'negative'

print(sign)
```

```text
positive
```

```python
x = 10

sign = 'postive' if x > 0 else 'negative'


print(sign)
```

```text
postive
```
