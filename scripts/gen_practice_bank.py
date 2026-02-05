#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import random
import textwrap
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
OUT_DEFAULT = ROOT / "practice_bank" / "_generated"

DIFF_ORDER = ["easy", "medium", "hard"]
TARGET_PER_TOPIC = {"easy": 3, "medium": 2, "hard": 1}

TOPIC_ORDER = [
    "basics",
    "numbers",
    "strings",
    "lists",
    "tuples",
    "dicts",
    "functions",
    "conditionals",
    "loops",
    "nested_loops",
    "comprehensions",
    "exceptions",
    "cli",
]


@dataclass
class Spec:
    slug: str           # topic/difficulty/name
    title: str
    topic: str
    difficulty: str
    prompt: str
    starter: str
    tests: str

    @property
    def path(self) -> Path:
        return Path(*self.slug.split("/")).with_suffix(".toml")


@dataclass(frozen=True)
class Template:
    topic: str
    difficulty: str
    fn: callable


REGISTRY: list[Template] = []


def template(topic: str, difficulty: str):
    def deco(fn):
        REGISTRY.append(Template(topic=topic, difficulty=difficulty, fn=fn))
        return fn
    return deco


def clean(s: str) -> str:
    return textwrap.dedent(s).strip("\n") + "\n"


def write_toml(out_dir: Path, s: Spec):
    p = out_dir / s.path
    p.parent.mkdir(parents=True, exist_ok=True)

    toml = f'''slug = "{s.slug}"
title = "{s.title}"
topic = "{s.topic}"
difficulty = "{s.difficulty}"

prompt = """\n{clean(s.prompt)}"""

starter_code = """\n{clean(s.starter).replace("\t","    ")}"""

tests = """\n{clean(s.tests).replace("\t","    ")}"""
'''
    p.write_text(toml, encoding="utf-8")


def slugname(base: str, i: int) -> str:
    return f"{base}_{i:03d}"


# ------------------------- BASICS -------------------------

@template("basics", "easy")
def t_basics_full_name(r: random.Random, i: int) -> Spec:
    first = r.choice(["Ada", "Grace", "Linus", "Alan", "Katherine"])
    last = r.choice(["Lovelace", "Hopper", "Torvalds", "Turing", "Johnson"])
    base = "basics/easy/full_name"
    slug = f"{base}/{slugname('problem', i)}"
    expected = f"{first} {last}"
    return Spec(
        slug=slug,
        title="Make a full name",
        topic="basics",
        difficulty="easy",
        prompt=f"Write `full_name(first, last)` that returns a string like `{expected}`.",
        starter="""\
def full_name(first, last):
    # TODO
    pass
""",
        tests=f"""\
assert full_name({first!r}, {last!r}) == {expected!r}
assert full_name("A", "B") == "A B"
""",
    )

@template("basics", "easy")
def t_basics_area_rect(r: random.Random, i: int) -> Spec:
    w = r.randint(1, 12)
    h = r.randint(1, 12)
    base = "basics/easy/area_rect"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Area of a rectangle",
        topic="basics",
        difficulty="easy",
        prompt="Write `area_rect(w, h)` that returns the area (w*h).",
        starter="""\
def area_rect(w, h):
    # TODO
    pass
""",
        tests=f"""\
assert area_rect({w}, {h}) == {w*h}
assert area_rect(1, 1) == 1
""",
    )

@template("basics", "easy")
def t_basics_format_money(r: random.Random, i: int) -> Spec:
    dollars = r.randint(0, 200)
    cents = r.randint(0, 99)
    amount = dollars + cents / 100.0
    base = "basics/easy/format_money"
    slug = f"{base}/{slugname('problem', i)}"
    expected = f"${amount:.2f}"
    return Spec(
        slug=slug,
        title="Format money",
        topic="basics",
        difficulty="easy",
        prompt="Write `format_money(x)` that returns a string like `$12.34` (always 2 decimals).",
        starter="""\
def format_money(x):
    # TODO
    pass
""",
        tests=f"""\
assert format_money({amount}) == {expected!r}
assert format_money(0) == "$0.00"
assert format_money(1.2) == "$1.20"
""",
    )

@template("basics", "medium")
def t_basics_f_to_c(r: random.Random, i: int) -> Spec:
    f = r.randint(-20, 120)
    c = (f - 32) * 5/9
    base = "basics/medium/f_to_c"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Fahrenheit to Celsius",
        topic="basics",
        difficulty="medium",
        prompt="Write `f_to_c(f)` that converts Fahrenheit to Celsius. Return a float.",
        starter="""\
def f_to_c(f):
    # TODO
    pass
""",
        tests=f"""\
out = f_to_c({f})
assert abs(out - ({c})) < 1e-9
assert abs(f_to_c(32) - 0) < 1e-9
""",
    )

@template("basics", "medium")
def t_basics_split_bill(r: random.Random, i: int) -> Spec:
    total = r.randint(10, 200)
    people = r.randint(2, 8)
    share = total / people
    base = "basics/medium/split_bill"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Split a bill",
        topic="basics",
        difficulty="medium",
        prompt="Write `split_bill(total, people)` that returns how much each person pays (a float).",
        starter="""\
def split_bill(total, people):
    # TODO
    pass
""",
        tests=f"""\
out = split_bill({total}, {people})
assert abs(out - ({share})) < 1e-9
""",
    )

@template("basics", "hard")
def t_basics_seconds_to_hms(r: random.Random, i: int) -> Spec:
    total = r.randint(0, 5*3600 + 59*60 + 59)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    base = "basics/hard/seconds_to_hms"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Seconds to (h, m, s)",
        topic="basics",
        difficulty="hard",
        prompt="Write `seconds_to_hms(total)` that returns a tuple `(hours, minutes, seconds)`.",
        starter="""\
def seconds_to_hms(total):
    # TODO
    pass
""",
        tests=f"""\
assert seconds_to_hms({total}) == ({h}, {m}, {s})
assert seconds_to_hms(0) == (0, 0, 0)
assert seconds_to_hms(60) == (0, 1, 0)
""",
    )


# ------------------------- NUMBERS -------------------------

@template("numbers", "easy")
def t_numbers_add(r: random.Random, i: int) -> Spec:
    a = r.randint(-50, 50)
    b = r.randint(-50, 50)
    base = "numbers/easy/add"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Add two numbers",
        topic="numbers",
        difficulty="easy",
        prompt=f"Write `add(a, b)` that returns the sum.\n\nExample: `add({a}, {b})` → `{a+b}`.",
        starter="""\
def add(a, b):
    # TODO
    pass
""",
        tests=f"""\
assert add({a}, {b}) == {a+b}
assert add(0, 0) == 0
assert add(-1, 1) == 0
""",
    )

@template("numbers", "easy")
def t_numbers_round2(r: random.Random, i: int) -> Spec:
    x = float(f"{r.uniform(-100, 100):.4f}")
    expected = round(x, 2)
    base = "numbers/easy/round2"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Round to 2 decimals",
        topic="numbers",
        difficulty="easy",
        prompt="Write `round2(x)` that returns `x` rounded to 2 decimal places.",
        starter="""\
def round2(x):
    # TODO
    pass
""",
        tests=f"""\
assert round2({x}) == {expected}
assert round2(1.234) == 1.23
assert round2(1.235) == 1.24
""",
    )

@template("numbers", "easy")
def t_numbers_abs_diff(r: random.Random, i: int) -> Spec:
    a = r.randint(-100, 100)
    b = r.randint(-100, 100)
    base = "numbers/easy/abs_diff"
    slug = f"{base}/{slugname('problem', i)}"
    expected = abs(a - b)
    return Spec(
        slug=slug,
        title="Absolute difference",
        topic="numbers",
        difficulty="easy",
        prompt="Write `abs_diff(a, b)` that returns `|a - b|`.",
        starter="""\
def abs_diff(a, b):
    # TODO
    pass
""",
        tests=f"""\
assert abs_diff({a}, {b}) == {expected}
assert abs_diff(5, 5) == 0
""",
    )

@template("numbers", "medium")
def t_numbers_percent_change(r: random.Random, i: int) -> Spec:
    old = r.randint(1, 200)
    new = r.randint(1, 200)
    expected = (new - old) / old
    base = "numbers/medium/percent_change"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Percent change",
        topic="numbers",
        difficulty="medium",
        prompt="Write `percent_change(old, new)` that returns `(new-old)/old` as a float.",
        starter="""\
def percent_change(old, new):
    # TODO
    pass
""",
        tests=f"""\
out = percent_change({old}, {new})
assert abs(out - ({expected})) < 1e-9
""",
    )

@template("numbers", "medium")
def t_numbers_mean3(r: random.Random, i: int) -> Spec:
    a, b, c = [r.randint(-50, 50) for _ in range(3)]
    expected = (a + b + c) / 3
    base = "numbers/medium/mean3"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Mean of three",
        topic="numbers",
        difficulty="medium",
        prompt="Write `mean3(a, b, c)` that returns the average of three numbers (a float).",
        starter="""\
def mean3(a, b, c):
    # TODO
    pass
""",
        tests=f"""\
out = mean3({a}, {b}, {c})
assert abs(out - ({expected})) < 1e-9
""",
    )

@template("numbers", "hard")
def t_numbers_gcd(r: random.Random, i: int) -> Spec:
    a = r.randint(10, 200)
    b = r.randint(10, 200)

    def gcd(x, y):
        while y:
            x, y = y, x % y
        return abs(x)

    expected = gcd(a, b)
    base = "numbers/hard/gcd"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Greatest common divisor",
        topic="numbers",
        difficulty="hard",
        prompt="Write `gcd(a, b)` that returns the greatest common divisor of two positive integers.",
        starter="""\
def gcd(a, b):
    # TODO
    pass
""",
        tests=f"""\
assert gcd({a}, {b}) == {expected}
assert gcd(12, 18) == 6
assert gcd(7, 13) == 1
""",
    )


# ------------------------- STRINGS -------------------------

@template("strings", "easy")
def t_strings_reverse(r: random.Random, i: int) -> Spec:
    s = r.choice(["banana", "mississippi", "abracadabra", "committee", "bookkeeper"])
    base = "strings/easy/reverse"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Reverse a string",
        topic="strings",
        difficulty="easy",
        prompt="Write `reverse(s)` that returns the reversed string.",
        starter="""\
def reverse(s):
    # TODO
    pass
""",
        tests=f"""\
assert reverse({s!r}) == {s[::-1]!r}
assert reverse("") == ""
assert reverse("a") == "a"
""",
    )

@template("strings", "easy")
def t_strings_count_vowels(r: random.Random, i: int) -> Spec:
    s = r.choice(["banana", "education", "queueing", "rhythm", "mississippi"])
    vowels = set("aeiouAEIOU")
    expected = sum(1 for ch in s if ch in vowels)
    base = "strings/easy/count_vowels"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Count vowels",
        topic="strings",
        difficulty="easy",
        prompt="Write `count_vowels(s)` that returns how many vowels are in `s` (a,e,i,o,u).",
        starter="""\
def count_vowels(s):
    # TODO
    pass
""",
        tests=f"""\
assert count_vowels({s!r}) == {expected}
assert count_vowels("xyz") == 0
assert count_vowels("AEIOU") == 5
""",
    )

@template("strings", "easy")
def t_strings_ends_with(r: random.Random, i: int) -> Spec:
    s = r.choice(["foundation", "programming", "hello world", "mississippi"])
    suffix = r.choice([s[-1], s[-2:], "xyz"])
    expected = s.endswith(suffix)
    base = "strings/easy/ends_with"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Ends with?",
        topic="strings",
        difficulty="easy",
        prompt="Write `ends_with(s, suffix)` that returns True if `s` ends with `suffix`.",
        starter="""\
def ends_with(s, suffix):
    # TODO
    pass
""",
        tests=f"""\
assert ends_with({s!r}, {suffix!r}) == {expected}
assert ends_with("abc", "c") is True
assert ends_with("abc", "bc") is True
assert ends_with("abc", "d") is False
""",
    )

@template("strings", "medium")
def t_strings_count_words(r: random.Random, i: int) -> Spec:
    s = r.choice([
        "a b c",
        "  too   many   spaces  ",
        "hello world",
        "one",
        "",
    ])
    expected = len([w for w in s.strip().split() if w])
    base = "strings/medium/count_words"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Count words",
        topic="strings",
        difficulty="medium",
        prompt="Write `count_words(s)` that returns how many words are in `s`. Words are separated by whitespace.",
        starter="""\
def count_words(s):
    # TODO
    pass
""",
        tests=f"""\
assert count_words({s!r}) == {expected}
assert count_words("a  b   c") == 3
assert count_words("") == 0
""",
    )

@template("strings", "medium")
def t_strings_title_case(r: random.Random, i: int) -> Spec:
    s = r.choice([
        "foundations of business programming",
        "hello world",
        "  multiple   spaces here ",
    ])
    expected = " ".join([w[:1].upper() + w[1:].lower() for w in s.strip().split()])
    base = "strings/medium/title_case"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Title case",
        topic="strings",
        difficulty="medium",
        prompt="Write `title_case(s)` that capitalizes each word (first letter uppercase, rest lowercase).",
        starter="""\
def title_case(s):
    # TODO
    pass
""",
        tests=f"""\
assert title_case({s!r}) == {expected!r}
assert title_case("hELLo") == "Hello"
""",
    )

@template("strings", "hard")
def t_strings_rle(r: random.Random, i: int) -> Spec:
    s = r.choice(["aaabbc", "mississippi", "hhhhii", "a", ""])
    # run-length encode as list of (char, count)
    enc = []
    if s:
        cur = s[0]
        cnt = 1
        for ch in s[1:]:
            if ch == cur:
                cnt += 1
            else:
                enc.append((cur, cnt))
                cur, cnt = ch, 1
        enc.append((cur, cnt))
    base = "strings/hard/run_length_encode"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Run-length encode",
        topic="strings",
        difficulty="hard",
        prompt="Write `rle(s)` that returns a list of `(char, count)` pairs for consecutive runs.\n\nExample: `rle('aaabbc') -> [('a',3), ('b',2), ('c',1)]`",
        starter="""\
def rle(s):
    # TODO
    pass
""",
        tests=f"""\
assert rle({s!r}) == {enc!r}
assert rle("") == []
assert rle("a") == [("a", 1)]
""",
    )


# ------------------------- LISTS -------------------------

@template("lists", "easy")
def t_lists_sum_no_sum(r: random.Random, i: int) -> Spec:
    nums = [r.randint(-9, 9) for _ in range(6)]
    expected = 0
    for x in nums:
        expected += x
    base = "lists/easy/sum_list"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Sum a list (no sum())",
        topic="lists",
        difficulty="easy",
        prompt="Write `sum_list(nums)` that returns the sum of the numbers in the list. (Don’t use `sum()`.)",
        starter="""\
def sum_list(nums):
    # TODO
    pass
""",
        tests=f"""\
assert sum_list({nums!r}) == {expected}
assert sum_list([]) == 0
assert sum_list([5]) == 5
""",
    )

@template("lists", "easy")
def t_lists_max_no_max(r: random.Random, i: int) -> Spec:
    nums = [r.randint(-20, 20) for _ in range(7)]
    expected = nums[0]
    for x in nums[1:]:
        if x > expected:
            expected = x
    base = "lists/easy/max_list"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Max in a list (no max())",
        topic="lists",
        difficulty="easy",
        prompt="Write `max_list(nums)` that returns the largest value. Assume `nums` is non-empty. (Don’t use `max()`.)",
        starter="""\
def max_list(nums):
    # TODO
    pass
""",
        tests=f"""\
assert max_list({nums!r}) == {expected}
assert max_list([1]) == 1
""",
    )

@template("lists", "easy")
def t_lists_count_occurrences(r: random.Random, i: int) -> Spec:
    nums = [r.randint(1, 5) for _ in range(10)]
    target = r.choice(nums)
    expected = 0
    for x in nums:
        if x == target:
            expected += 1
    base = "lists/easy/count_occurrences"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Count occurrences",
        topic="lists",
        difficulty="easy",
        prompt="Write `count_occurrences(nums, target)` that returns how many times `target` appears in `nums`.",
        starter="""\
def count_occurrences(nums, target):
    # TODO
    pass
""",
        tests=f"""\
assert count_occurrences({nums!r}, {target}) == {expected}
assert count_occurrences([], 3) == 0
""",
    )

@template("lists", "medium")
def t_lists_two_sum_indices(r: random.Random, i: int) -> Spec:
    nums = [2, 7, 11, 15]
    target = 9
    base = "lists/medium/two_sum_indices"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Two Sum (indices)",
        topic="lists",
        difficulty="medium",
        prompt="Given `nums` and `target`, return a tuple `(i, j)` such that `nums[i] + nums[j] == target` and `i != j`.\nAssume exactly one solution exists. Return smaller index first.",
        starter="""\
def two_sum(nums, target):
    # TODO
    pass
""",
        tests=f"""\
assert two_sum({nums!r}, {target}) == (0, 1)
assert two_sum([3, 2, 4], 6) == (1, 2)
""",
    )

@template("lists", "medium")
def t_lists_dedup_preserve(r: random.Random, i: int) -> Spec:
    nums = [r.randint(1, 6) for _ in range(12)]
    seen = set()
    expected = []
    for x in nums:
        if x not in seen:
            seen.add(x)
            expected.append(x)
    base = "lists/medium/dedup_preserve"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Deduplicate (keep order)",
        topic="lists",
        difficulty="medium",
        prompt="Write `dedup(nums)` that returns a new list with duplicates removed, keeping the first occurrence order.",
        starter="""\
def dedup(nums):
    # TODO
    pass
""",
        tests=f"""\
assert dedup({nums!r}) == {expected!r}
assert dedup([]) == []
""",
    )

@template("lists", "hard")
def t_lists_merge_sorted(r: random.Random, i: int) -> Spec:
    a = sorted([r.randint(0, 20) for _ in range(6)])
    b = sorted([r.randint(0, 20) for _ in range(6)])
    expected = sorted(a + b)
    base = "lists/hard/merge_sorted"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Merge two sorted lists",
        topic="lists",
        difficulty="hard",
        prompt="Write `merge_sorted(a, b)` where `a` and `b` are sorted lists, and return a single sorted merged list.",
        starter="""\
def merge_sorted(a, b):
    # TODO
    pass
""",
        tests=f"""\
assert merge_sorted({a!r}, {b!r}) == {expected!r}
assert merge_sorted([], [1,2]) == [1,2]
assert merge_sorted([1,2], []) == [1,2]
""",
    )


# ------------------------- TUPLES -------------------------

@template("tuples", "easy")
def t_tuples_swap(r: random.Random, i: int) -> Spec:
    a = r.randint(-20, 20)
    b = r.randint(-20, 20)
    base = "tuples/easy/swap"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Swap a pair",
        topic="tuples",
        difficulty="easy",
        prompt="Write `swap(pair)` where `pair` is a tuple `(a, b)` and you return `(b, a)`.",
        starter="""\
def swap(pair):
    # TODO
    pass
""",
        tests=f"""\
assert swap(({a}, {b})) == ({b}, {a})
assert swap((1, 2)) == (2, 1)
""",
    )

@template("tuples", "easy")
def t_tuples_midpoint(r: random.Random, i: int) -> Spec:
    x1, y1 = r.randint(-10, 10), r.randint(-10, 10)
    x2, y2 = r.randint(-10, 10), r.randint(-10, 10)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    base = "tuples/easy/midpoint"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Midpoint of two points",
        topic="tuples",
        difficulty="easy",
        prompt="Write `midpoint(p, q)` where `p` and `q` are `(x, y)` tuples. Return the midpoint `(mx, my)` as floats.",
        starter="""\
def midpoint(p, q):
    # TODO
    pass
""",
        tests=f"""\
out = midpoint(({x1}, {y1}), ({x2}, {y2}))
assert abs(out[0] - ({mx})) < 1e-9
assert abs(out[1] - ({my})) < 1e-9
""",
    )

@template("tuples", "easy")
def t_tuples_first_last(r: random.Random, i: int) -> Spec:
    s = r.choice(["banana", "hello", "a", "mississippi"])
    base = "tuples/easy/first_last"
    slug = f"{base}/{slugname('problem', i)}"
    expected = (s[0], s[-1]) if s else ("", "")
    return Spec(
        slug=slug,
        title="First and last character",
        topic="tuples",
        difficulty="easy",
        prompt="Write `first_last(s)` that returns a tuple `(first, last)`. If `s` is empty, return `('', '')`.",
        starter="""\
def first_last(s):
    # TODO
    pass
""",
        tests=f"""\
assert first_last({s!r}) == {expected!r}
assert first_last("") == ("", "")
""",
    )

@template("tuples", "medium")
def t_tuples_sort_by_second(r: random.Random, i: int) -> Spec:
    pairs = [(r.randint(0, 9), r.randint(0, 9)) for _ in range(6)]
    expected = sorted(pairs, key=lambda t: t[1])
    base = "tuples/medium/sort_by_second"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Sort by second value",
        topic="tuples",
        difficulty="medium",
        prompt="Write `sort_by_second(pairs)` that returns a new list of tuples sorted by the second element.",
        starter="""\
def sort_by_second(pairs):
    # TODO
    pass
""",
        tests=f"""\
assert sort_by_second({pairs!r}) == {expected!r}
""",
    )

@template("tuples", "medium")
def t_tuples_bounding_box(r: random.Random, i: int) -> Spec:
    pts = [(r.randint(-5, 5), r.randint(-5, 5)) for _ in range(7)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    expected = (min(xs), min(ys), max(xs), max(ys))
    base = "tuples/medium/bounding_box"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Bounding box",
        topic="tuples",
        difficulty="medium",
        prompt="Write `bounding_box(points)` that returns `(min_x, min_y, max_x, max_y)` for a list of `(x, y)` points.",
        starter="""\
def bounding_box(points):
    # TODO
    pass
""",
        tests=f"""\
assert bounding_box({pts!r}) == {expected!r}
""",
    )

@template("tuples", "hard")
def t_tuples_perimeter(r: random.Random, i: int) -> Spec:
    pts = [(0, 0), (3, 0), (3, 4)]  # fixed: 3-4-5 triangle, perimeter 12
    expected = 12.0
    base = "tuples/hard/polygon_perimeter"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Polygon perimeter",
        topic="tuples",
        difficulty="hard",
        prompt="Write `perimeter(points)` that returns the perimeter of a polygon given a list of `(x, y)` points in order.\nConnect the last point back to the first. Return a float.",
        starter="""\
def perimeter(points):
    # TODO
    pass
""",
        tests=f"""\
out = perimeter({pts!r})
assert abs(out - ({expected})) < 1e-9
""",
    )


# ------------------------- DICTS -------------------------

@template("dicts", "easy")
def t_dicts_lookup_default(r: random.Random, i: int) -> Spec:
    d = {"a": 1, "b": 2}
    base = "dicts/easy/lookup_default"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Dictionary lookup with default",
        topic="dicts",
        difficulty="easy",
        prompt="Write `lookup(d, key, default)` that returns `d[key]` if present, otherwise `default` (don’t use `dict.get`).",
        starter="""\
def lookup(d, key, default):
    # TODO
    pass
""",
        tests="""\
assert lookup({"a":1,"b":2}, "a", 99) == 1
assert lookup({"a":1,"b":2}, "z", 99) == 99
""",
    )

@template("dicts", "easy")
def t_dicts_count_chars(r: random.Random, i: int) -> Spec:
    s = r.choice(["banana", "mississippi", "abba", "aab"])
    expected = {}
    for ch in s:
        expected[ch] = expected.get(ch, 0) + 1
    base = "dicts/easy/count_chars"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Count characters",
        topic="dicts",
        difficulty="easy",
        prompt="Write `count_chars(s)` that returns a dict mapping each character to its count.",
        starter="""\
def count_chars(s):
    # TODO
    pass
""",
        tests=f"""\
assert count_chars({s!r}) == {expected!r}
assert count_chars("") == {{}}
""",
    )

@template("dicts", "easy")
def t_dicts_key_in_dict(r: random.Random, i: int) -> Spec:
    d = {"x": 10, "y": 20}
    key = r.choice(["x", "z"])
    expected = key in d
    base = "dicts/easy/has_key"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Has key?",
        topic="dicts",
        difficulty="easy",
        prompt="Write `has_key(d, key)` that returns True if `key` is in `d`, otherwise False.",
        starter="""\
def has_key(d, key):
    # TODO
    pass
""",
        tests=f"""\
assert has_key({d!r}, {key!r}) == {expected}
assert has_key({d!r}, "x") is True
""",
    )

@template("dicts", "medium")
def t_dicts_freq(r: random.Random, i: int) -> Spec:
    words = r.choice([
        ["red", "blue", "red", "green", "blue", "red"],
        ["a", "b", "a", "c", "b", "a", "d"],
        ["cat", "dog", "cat", "cat", "bird"],
    ])
    expected = {}
    for w in words:
        expected[w] = expected.get(w, 0) + 1
    base = "dicts/medium/frequency"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Frequency dictionary",
        topic="dicts",
        difficulty="medium",
        prompt="Write `freq(items)` that returns a dict mapping each item to how many times it occurs.",
        starter="""\
def freq(items):
    # TODO
    pass
""",
        tests=f"""\
assert freq({words!r}) == {expected!r}
assert freq([]) == {{}}
""",
    )

@template("dicts", "medium")
def t_dicts_merge_add(r: random.Random, i: int) -> Spec:
    d1 = {"a": 1, "b": 2}
    d2 = {"b": 5, "c": 7}
    expected = {"a": 1, "b": 7, "c": 7}
    base = "dicts/medium/merge_add"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Merge dicts by adding values",
        topic="dicts",
        difficulty="medium",
        prompt="Write `merge_add(d1, d2)` that returns a dict with keys from both. If a key is in both, add the values.",
        starter="""\
def merge_add(d1, d2):
    # TODO
    pass
""",
        tests=f"""\
assert merge_add({d1!r}, {d2!r}) == {expected!r}
""",
    )

@template("dicts", "hard")
def t_dicts_most_common(r: random.Random, i: int) -> Spec:
    d = r.choice([
        {"a": 5, "b": 1, "c": 3},
        {"x": 2, "y": 9, "z": 9},
    ])
    # tie-break: smallest key (string) if equal max
    mx = max(d.values())
    candidates = sorted([k for k, v in d.items() if v == mx])
    expected = candidates[0]
    base = "dicts/hard/most_common"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Most common key",
        topic="dicts",
        difficulty="hard",
        prompt="Write `most_common(d)` that returns the key with the largest value.\nIf tied, return the lexicographically smallest key.",
        starter="""\
def most_common(d):
    # TODO
    pass
""",
        tests=f"""\
assert most_common({d!r}) == {expected!r}
assert most_common({{"a":1,"b":1}}) == "a"
""",
    )


# ------------------------- FUNCTIONS -------------------------

@template("functions", "easy")
def t_functions_product_args(r: random.Random, i: int) -> Spec:
    nums = [r.randint(1, 9) for _ in range(4)]
    expected = 1
    for x in nums:
        expected *= x
    base = "functions/easy/product_args"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Product of *args",
        topic="functions",
        difficulty="easy",
        prompt="Write `product(*args)` that returns the product of all numbers. If no args, return 1.",
        starter="""\
def product(*args):
    # TODO
    pass
""",
        tests=f"""\
assert product(*{nums!r}) == {expected}
assert product() == 1
assert product(5) == 5
""",
    )

@template("functions", "easy")
def t_functions_avg_args(r: random.Random, i: int) -> Spec:
    nums = [r.randint(1, 20) for _ in range(5)]
    expected = sum(nums) / len(nums)
    base = "functions/easy/avg_args"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Average of *args",
        topic="functions",
        difficulty="easy",
        prompt="Write `avg(*args)` that returns the average. Assume at least one arg.",
        starter="""\
def avg(*args):
    # TODO
    pass
""",
        tests=f"""\
out = avg(*{nums!r})
assert abs(out - ({expected})) < 1e-9
""",
    )

@template("functions", "easy")
def t_functions_format_kwargs(r: random.Random, i: int) -> Spec:
    base = "functions/easy/format_kwargs"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Format **kwargs",
        topic="functions",
        difficulty="easy",
        prompt="Write `format_kwargs(**kwargs)` that returns a string like `a=1,b=2` with keys sorted alphabetically.",
        starter="""\
def format_kwargs(**kwargs):
    # TODO
    pass
""",
        tests="""\
assert format_kwargs(b=2, a=1) == "a=1,b=2"
assert format_kwargs() == ""
""",
    )

@template("functions", "medium")
def t_functions_compose(r: random.Random, i: int) -> Spec:
    base = "functions/medium/compose"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Compose two functions",
        topic="functions",
        difficulty="medium",
        prompt="Write `compose(f, g)` that returns a new function `h(x)` which computes `f(g(x))`.",
        starter="""\
def compose(f, g):
    # TODO
    pass
""",
        tests="""\
def inc(x): return x+1
def dbl(x): return 2*x
h = compose(dbl, inc)   # dbl(inc(x))
assert h(3) == 8
""",
    )

@template("functions", "medium")
def t_functions_apply_n(r: random.Random, i: int) -> Spec:
    n = r.randint(2, 5)
    base = "functions/medium/apply_n"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Apply a function n times",
        topic="functions",
        difficulty="medium",
        prompt=f"Write `apply_n(f, x, n)` that applies `f` to `x` exactly `n` times.\nExample: if `f(x)=x+1`, then `apply_n(f, 10, {n}) = {10+n}`.",
        starter="""\
def apply_n(f, x, n):
    # TODO
    pass
""",
        tests=f"""\
def inc(x): return x+1
assert apply_n(inc, 10, {n}) == {10+n}
assert apply_n(inc, 0, 0) == 0
""",
    )

@template("functions", "hard")
def t_functions_memoize(r: random.Random, i: int) -> Spec:
    base = "functions/hard/memoize"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Memoize (cache) a function",
        topic="functions",
        difficulty="hard",
        prompt="Write `memoize(f)` that returns a new function which caches results by argument.\nAssume `f` takes a single hashable argument.",
        starter="""\
def memoize(f):
    # TODO
    pass
""",
        tests="""\
calls = {"n": 0}
def f(x):
    calls["n"] += 1
    return x*x

g = memoize(f)
assert g(3) == 9
assert g(3) == 9
assert calls["n"] == 1
assert g(4) == 16
assert calls["n"] == 2
""",
    )


# ------------------------- CONDITIONALS -------------------------

@template("conditionals", "easy")
def t_conditionals_clamp(r: random.Random, i: int) -> Spec:
    x = r.randint(-20, 20)
    lo = r.randint(-10, 0)
    hi = r.randint(1, 10)
    if lo > hi:
        lo, hi = hi, lo
    expected = x
    if expected < lo: expected = lo
    if expected > hi: expected = hi
    base = "conditionals/easy/clamp"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Clamp a number",
        topic="conditionals",
        difficulty="easy",
        prompt="Write `clamp(x, lo, hi)` that returns `x` but forced into the inclusive range `[lo, hi]`.",
        starter="""\
def clamp(x, lo, hi):
    # TODO
    pass
""",
        tests=f"""\
assert clamp({x}, {lo}, {hi}) == {expected}
assert clamp(5, 0, 10) == 5
assert clamp(-1, 0, 10) == 0
assert clamp(999, 0, 10) == 10
""",
    )

@template("conditionals", "easy")
def t_conditionals_sign(r: random.Random, i: int) -> Spec:
    x = r.randint(-10, 10)
    expected = -1 if x < 0 else 1 if x > 0 else 0
    base = "conditionals/easy/sign"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Sign of a number",
        topic="conditionals",
        difficulty="easy",
        prompt="Write `sign(x)` that returns -1 if x<0, 0 if x==0, and 1 if x>0.",
        starter="""\
def sign(x):
    # TODO
    pass
""",
        tests=f"""\
assert sign({x}) == {expected}
assert sign(-5) == -1
assert sign(0) == 0
assert sign(7) == 1
""",
    )

@template("conditionals", "easy")
def t_conditionals_is_even(r: random.Random, i: int) -> Spec:
    x = r.randint(-50, 50)
    expected = (x % 2 == 0)
    base = "conditionals/easy/is_even"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Is even?",
        topic="conditionals",
        difficulty="easy",
        prompt="Write `is_even(n)` that returns True if n is even, otherwise False.",
        starter="""\
def is_even(n):
    # TODO
    pass
""",
        tests=f"""\
assert is_even({x}) == {expected}
assert is_even(0) is True
assert is_even(3) is False
""",
    )

@template("conditionals", "medium")
def t_conditionals_grade_letter(r: random.Random, i: int) -> Spec:
    score = r.randint(0, 100)
    def grade(s):
        if s >= 90: return "A"
        if s >= 80: return "B"
        if s >= 70: return "C"
        if s >= 60: return "D"
        return "F"
    expected = grade(score)
    base = "conditionals/medium/grade_letter"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Letter grade",
        topic="conditionals",
        difficulty="medium",
        prompt="Write `grade(score)` using this scale: 90+=A, 80+=B, 70+=C, 60+=D, else F.",
        starter="""\
def grade(score):
    # TODO
    pass
""",
        tests=f"""\
assert grade({score}) == {expected!r}
assert grade(90) == "A"
assert grade(59) == "F"
""",
    )

@template("conditionals", "medium")
def t_conditionals_triangle_type(r: random.Random, i: int) -> Spec:
    a, b, c = r.randint(1, 10), r.randint(1, 10), r.randint(1, 10)
    # ensure a valid triangle by fixing c if needed
    if a + b <= c:
        c = max(1, a + b - 1)
    if a == b == c:
        expected = "equilateral"
    elif a == b or b == c or a == c:
        expected = "isosceles"
    else:
        expected = "scalene"
    base = "conditionals/medium/triangle_type"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Triangle type",
        topic="conditionals",
        difficulty="medium",
        prompt="Write `triangle_type(a, b, c)` that returns 'equilateral', 'isosceles', or 'scalene'. Assume inputs form a valid triangle.",
        starter="""\
def triangle_type(a, b, c):
    # TODO
    pass
""",
        tests=f"""\
assert triangle_type({a}, {b}, {c}) == {expected!r}
assert triangle_type(2,2,3) == "isosceles"
""",
    )

@template("conditionals", "hard")
def t_conditionals_median3(r: random.Random, i: int) -> Spec:
    a, b, c = r.randint(-20, 20), r.randint(-20, 20), r.randint(-20, 20)
    expected = sorted([a, b, c])[1]
    base = "conditionals/hard/median3"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Median of three",
        topic="conditionals",
        difficulty="hard",
        prompt="Write `median3(a, b, c)` that returns the middle value (not min, not max). Don’t sort.",
        starter="""\
def median3(a, b, c):
    # TODO
    pass
""",
        tests=f"""\
assert median3({a}, {b}, {c}) == {expected}
assert median3(1, 2, 3) == 2
assert median3(3, 1, 2) == 2
""",
    )


# ------------------------- LOOPS -------------------------

@template("loops", "easy")
def t_loops_factorial(r: random.Random, i: int) -> Spec:
    n = r.randint(3, 8)
    expected = 1
    for k in range(1, n+1):
        expected *= k
    base = "loops/easy/factorial"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Factorial",
        topic="loops",
        difficulty="easy",
        prompt="Write `factorial(n)` that returns `n!` using a loop. Assume `n >= 0`.",
        starter="""\
def factorial(n):
    # TODO
    pass
""",
        tests=f"""\
assert factorial({n}) == {expected}
assert factorial(0) == 1
assert factorial(1) == 1
""",
    )

@template("loops", "easy")
def t_loops_sum_to_n(r: random.Random, i: int) -> Spec:
    n = r.randint(1, 50)
    expected = n * (n + 1) // 2
    base = "loops/easy/sum_to_n"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Sum 1..n",
        topic="loops",
        difficulty="easy",
        prompt="Write `sum_to_n(n)` that returns `1 + 2 + ... + n` using a loop. Assume `n >= 0`.",
        starter="""\
def sum_to_n(n):
    # TODO
    pass
""",
        tests=f"""\
assert sum_to_n({n}) == {expected}
assert sum_to_n(0) == 0
""",
    )

@template("loops", "easy")
def t_loops_count_digits(r: random.Random, i: int) -> Spec:
    n = r.randint(0, 10**6)
    expected = len(str(n))
    base = "loops/easy/count_digits"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Count digits",
        topic="loops",
        difficulty="easy",
        prompt="Write `count_digits(n)` that returns how many digits are in the nonnegative integer `n`.\n(For example, `count_digits(0) == 1`.)",
        starter="""\
def count_digits(n):
    # TODO
    pass
""",
        tests=f"""\
assert count_digits({n}) == {expected}
assert count_digits(0) == 1
""",
    )

@template("loops", "medium")
def t_loops_is_prime(r: random.Random, i: int) -> Spec:
    n = r.randint(2, 80)
    def is_prime(x):
        if x < 2: return False
        k = 2
        while k*k <= x:
            if x % k == 0:
                return False
            k += 1
        return True
    expected = is_prime(n)
    base = "loops/medium/is_prime"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Is prime?",
        topic="loops",
        difficulty="medium",
        prompt="Write `is_prime(n)` that returns True if n is prime, else False. Assume n is an int.",
        starter="""\
def is_prime(n):
    # TODO
    pass
""",
        tests=f"""\
assert is_prime({n}) == {expected}
assert is_prime(2) is True
assert is_prime(4) is False
""",
    )

@template("loops", "medium")
def t_loops_reverse_int(r: random.Random, i: int) -> Spec:
    n = r.randint(0, 99999)
    expected = int(str(n)[::-1])
    base = "loops/medium/reverse_int"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Reverse digits",
        topic="loops",
        difficulty="medium",
        prompt="Write `reverse_int(n)` that reverses the digits of a nonnegative integer.\nExample: 120 -> 21",
        starter="""\
def reverse_int(n):
    # TODO
    pass
""",
        tests=f"""\
assert reverse_int({n}) == {expected}
assert reverse_int(120) == 21
assert reverse_int(0) == 0
""",
    )

@template("loops", "hard")
def t_loops_fib(r: random.Random, i: int) -> Spec:
    n = r.randint(0, 20)
    def fib(k):
        a, b = 0, 1
        for _ in range(k):
            a, b = b, a + b
        return a
    expected = fib(n)
    base = "loops/hard/fibonacci"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Fibonacci number",
        topic="loops",
        difficulty="hard",
        prompt="Write `fib(n)` that returns the nth Fibonacci number with `fib(0)=0`, `fib(1)=1`. Use a loop.",
        starter="""\
def fib(n):
    # TODO
    pass
""",
        tests=f"""\
assert fib({n}) == {expected}
assert fib(0) == 0
assert fib(1) == 1
assert fib(7) == 13
""",
    )


# ------------------------- NESTED LOOPS -------------------------

@template("nested_loops", "easy")
def t_nested_first_index(r: random.Random, i: int) -> Spec:
    s = r.choice(["banana", "committee", "mississippi"])
    target = r.choice(list(set(s)))
    idx = next(k for k, ch in enumerate(s) if ch == target)
    base = "nested_loops/easy/first_index"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="First index with enumerate()",
        topic="nested_loops",
        difficulty="easy",
        prompt="Write `first_index(s, ch)` that returns the first index where `s[index] == ch`. Assume `ch` occurs at least once.",
        starter="""\
def first_index(s, ch):
    # TODO
    pass
""",
        tests=f"""\
assert first_index({s!r}, {target!r}) == {idx}
assert first_index("abc", "a") == 0
""",
    )

@template("nested_loops", "easy")
def t_nested_count_pairs_sum(r: random.Random, i: int) -> Spec:
    nums = [r.randint(0, 9) for _ in range(7)]
    target = r.randint(0, 18)
    expected = 0
    for a in range(len(nums)):
        for b in range(a+1, len(nums)):
            if nums[a] + nums[b] == target:
                expected += 1
    base = "nested_loops/easy/count_pairs_sum"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Count pairs that sum to target",
        topic="nested_loops",
        difficulty="easy",
        prompt="Write `count_pairs(nums, target)` that counts pairs (i<j) with nums[i]+nums[j]==target.",
        starter="""\
def count_pairs(nums, target):
    # TODO
    pass
""",
        tests=f"""\
assert count_pairs({nums!r}, {target}) == {expected}
""",
    )

@template("nested_loops", "easy")
def t_nested_find_in_grid(r: random.Random, i: int) -> Spec:
    grid = ["axc", "def", "gxh"]
    ch = r.choice(["a", "x", "h"])
    # find first (row,col)
    pos = None
    for r_i, row in enumerate(grid):
        for c_i, v in enumerate(row):
            if v == ch:
                pos = (r_i, c_i)
                break
        if pos:
            break
    base = "nested_loops/easy/find_in_grid"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Find a character in a grid",
        topic="nested_loops",
        difficulty="easy",
        prompt="Given `grid` as a list of equal-length strings, write `find_char(grid, ch)` that returns `(row, col)` of the first match, or `None` if not found.",
        starter="""\
def find_char(grid, ch):
    # TODO
    pass
""",
        tests=f"""\
assert find_char({grid!r}, {ch!r}) == {pos!r}
assert find_char({grid!r}, "Z") is None
""",
    )

@template("nested_loops", "medium")
def t_nested_mult_table(r: random.Random, i: int) -> Spec:
    n = r.randint(3, 6)
    expected = [[(i*j) for j in range(1, n+1)] for i in range(1, n+1)]
    base = "nested_loops/medium/mult_table"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Multiplication table",
        topic="nested_loops",
        difficulty="medium",
        prompt="Write `mult_table(n)` that returns an `n x n` list of lists where entry `[i][j]` is `(i+1)*(j+1)`.",
        starter="""\
def mult_table(n):
    # TODO
    pass
""",
        tests=f"""\
assert mult_table({n}) == {expected!r}
""",
    )

@template("nested_loops", "medium")
def t_nested_transpose(r: random.Random, i: int) -> Spec:
    m = [[1, 2, 3], [4, 5, 6]]
    expected = [[1, 4], [2, 5], [3, 6]]
    base = "nested_loops/medium/transpose"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Transpose a matrix",
        topic="nested_loops",
        difficulty="medium",
        prompt="Write `transpose(m)` where `m` is a list-of-lists matrix. Return the transposed matrix.",
        starter="""\
def transpose(m):
    # TODO
    pass
""",
        tests=f"""\
assert transpose({m!r}) == {expected!r}
""",
    )

@template("nested_loops", "hard")
def t_nested_ttt_winner(r: random.Random, i: int) -> Spec:
    board = [
        ["X", "X", "X"],
        ["O", "", "O"],
        ["", "", ""],
    ]
    expected = "X"
    base = "nested_loops/hard/tictactoe_winner"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Tic-tac-toe winner",
        topic="nested_loops",
        difficulty="hard",
        prompt="Write `winner(board)` for a 3x3 tic-tac-toe board (list of lists of 'X','O',''). Return 'X', 'O', or None.",
        starter="""\
def winner(board):
    # TODO
    pass
""",
        tests=f"""\
assert winner({board!r}) == {expected!r}
assert winner([["","",""],["","",""],["","",""]]) is None
""",
    )


# ------------------------- COMPREHENSIONS -------------------------

@template("comprehensions", "easy")
def t_comp_squares(r: random.Random, i: int) -> Spec:
    n = r.randint(5, 12)
    expected = [k*k for k in range(1, n+1)]
    base = "comprehensions/easy/squares"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Squares with a list comprehension",
        topic="comprehensions",
        difficulty="easy",
        prompt="Write `squares(n)` that returns `[1^2, 2^2, ..., n^2]`. (Try a list comprehension.)",
        starter="""\
def squares(n):
    # TODO
    pass
""",
        tests=f"""\
assert squares({n}) == {expected!r}
""",
    )

@template("comprehensions", "easy")
def t_comp_evens(r: random.Random, i: int) -> Spec:
    nums = [r.randint(0, 20) for _ in range(10)]
    expected = [x for x in nums if x % 2 == 0]
    base = "comprehensions/easy/evens"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Filter evens",
        topic="comprehensions",
        difficulty="easy",
        prompt="Write `evens(nums)` that returns a new list of only the even numbers (try a comprehension).",
        starter="""\
def evens(nums):
    # TODO
    pass
""",
        tests=f"""\
assert evens({nums!r}) == {expected!r}
""",
    )

@template("comprehensions", "easy")
def t_comp_lengths(r: random.Random, i: int) -> Spec:
    words = r.choice([["a", "bb", "ccc"], ["hello", "world"], []])
    expected = [len(w) for w in words]
    base = "comprehensions/easy/lengths"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Word lengths",
        topic="comprehensions",
        difficulty="easy",
        prompt="Write `lengths(words)` that returns a list of lengths of each word (try a comprehension).",
        starter="""\
def lengths(words):
    # TODO
    pass
""",
        tests=f"""\
assert lengths({words!r}) == {expected!r}
""",
    )

@template("comprehensions", "medium")
def t_comp_invert_dict(r: random.Random, i: int) -> Spec:
    d = r.choice([
        {"a": 1, "b": 2, "c": 3},
        {"x": "red", "y": "blue", "z": "green"},
    ])
    inv = {v: k for k, v in d.items()}
    base = "comprehensions/medium/invert_dict"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Invert a dict",
        topic="comprehensions",
        difficulty="medium",
        prompt="Write `invert(d)` that returns a new dict mapping values to keys. Assume all values are unique.",
        starter="""\
def invert(d):
    # TODO
    pass
""",
        tests=f"""\
assert invert({d!r}) == {inv!r}
""",
    )

@template("comprehensions", "medium")
def t_comp_filter_dict(r: random.Random, i: int) -> Spec:
    d = {"a": 1, "b": 5, "c": 2, "d": 9}
    threshold = r.choice([2, 5, 7])
    expected = {k: v for k, v in d.items() if v >= threshold}
    base = "comprehensions/medium/filter_dict"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Filter a dict by value",
        topic="comprehensions",
        difficulty="medium",
        prompt="Write `filter_ge(d, threshold)` that keeps only items where value >= threshold (try a dict comprehension).",
        starter="""\
def filter_ge(d, threshold):
    # TODO
    pass
""",
        tests=f"""\
assert filter_ge({d!r}, {threshold}) == {expected!r}
""",
    )

@template("comprehensions", "hard")
def t_comp_unique_sorted(r: random.Random, i: int) -> Spec:
    nums = [r.randint(0, 10) for _ in range(15)]
    expected = sorted(set(nums))
    base = "comprehensions/hard/unique_sorted"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Unique + sorted",
        topic="comprehensions",
        difficulty="hard",
        prompt="Write `unique_sorted(nums)` that returns the unique values in ascending order.\n(Try a set + sorted.)",
        starter="""\
def unique_sorted(nums):
    # TODO
    pass
""",
        tests=f"""\
assert unique_sorted({nums!r}) == {expected!r}
assert unique_sorted([]) == []
""",
    )


# ------------------------- EXCEPTIONS -------------------------

@template("exceptions", "easy")
def t_exc_safe_int(r: random.Random, i: int) -> Spec:
    s = r.choice(["42", "-7", "003", "nope", "12.5"])
    expected = None
    try:
        expected = int(s)
    except Exception:
        expected = None
    base = "exceptions/easy/safe_int"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Safe int conversion",
        topic="exceptions",
        difficulty="easy",
        prompt="Write `safe_int(s)` that returns `int(s)` if possible, otherwise returns `None`.",
        starter="""\
def safe_int(s):
    # TODO
    pass
""",
        tests=f"""\
assert safe_int({s!r}) == {expected!r}
assert safe_int("10") == 10
assert safe_int("no") is None
""",
    )

@template("exceptions", "easy")
def t_exc_safe_divide(r: random.Random, i: int) -> Spec:
    a = r.randint(-20, 20)
    b = r.choice([0, 1, 2, -3])
    expected = None
    try:
        expected = a / b
    except Exception:
        expected = None
    base = "exceptions/easy/safe_divide"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Safe divide",
        topic="exceptions",
        difficulty="easy",
        prompt="Write `safe_divide(a, b)` that returns `a/b` or `None` if division fails.",
        starter="""\
def safe_divide(a, b):
    # TODO
    pass
""",
        tests=f"""\
assert safe_divide({a}, {b}) == {expected!r}
assert safe_divide(10, 2) == 5
assert safe_divide(10, 0) is None
""",
    )

@template("exceptions", "easy")
def t_exc_safe_index(r: random.Random, i: int) -> Spec:
    xs = [r.randint(0, 9) for _ in range(5)]
    idx = r.choice([-1, 0, 2, 10])
    expected = None
    try:
        expected = xs[idx]
    except Exception:
        expected = None
    base = "exceptions/easy/safe_index"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Safe index",
        topic="exceptions",
        difficulty="easy",
        prompt="Write `safe_index(xs, i)` that returns `xs[i]` or `None` if it's out of range.",
        starter="""\
def safe_index(xs, i):
    # TODO
    pass
""",
        tests=f"""\
assert safe_index({xs!r}, {idx}) == {expected!r}
""",
    )

@template("exceptions", "medium")
def t_exc_parse_int_list(r: random.Random, i: int) -> Spec:
    s = r.choice(["1,2,3", "10, -5, 7", "", "a,2,3"])
    base = "exceptions/medium/parse_int_list"
    slug = f"{base}/{slugname('problem', i)}"
    # expected: return list of ints if all parse, else None
    expected = None
    try:
        parts = [p.strip() for p in s.split(",")] if s != "" else []
        xs = [int(p) for p in parts if p != ""]
        expected = xs
    except Exception:
        expected = None
    return Spec(
        slug=slug,
        title="Parse int list",
        topic="exceptions",
        difficulty="medium",
        prompt="Write `parse_int_list(s)` where `s` looks like `'1,2,3'`. Return a list of ints.\nIf any item fails to parse, return `None`.",
        starter="""\
def parse_int_list(s):
    # TODO
    pass
""",
        tests=f"""\
assert parse_int_list({s!r}) == {expected!r}
assert parse_int_list("1,2,3") == [1,2,3]
assert parse_int_list("a,2") is None
""",
    )

@template("exceptions", "medium")
def t_exc_safe_key(r: random.Random, i: int) -> Spec:
    d = {"a": 1}
    key = r.choice(["a", "b"])
    expected = d[key] if key in d else None
    base = "exceptions/medium/safe_key"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Safe dict access",
        topic="exceptions",
        difficulty="medium",
        prompt="Write `safe_get(d, key)` that returns `d[key]` or `None` if the key is missing (use try/except).",
        starter="""\
def safe_get(d, key):
    # TODO
    pass
""",
        tests=f"""\
assert safe_get({d!r}, {key!r}) == {expected!r}
""",
    )

@template("exceptions", "hard")
def t_exc_validate_int_range(r: random.Random, i: int) -> Spec:
    base = "exceptions/hard/validate_range"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Validate integer in range",
        topic="exceptions",
        difficulty="hard",
        prompt="Write `validate_int_in_range(s, lo, hi)`:\n- Convert `s` to int\n- If conversion fails, raise `ValueError`\n- If not in [lo, hi], raise `ValueError`\n- Otherwise return the int",
        starter="""\
def validate_int_in_range(s, lo, hi):
    # TODO
    pass
""",
        tests="""\
assert validate_int_in_range("5", 0, 10) == 5
try:
    validate_int_in_range("nope", 0, 10)
    assert False
except ValueError:
    pass

try:
    validate_int_in_range("99", 0, 10)
    assert False
except ValueError:
    pass
""",
    )


# ------------------------- CLI (SIMULATED argv; Pyodide-friendly) -------------------------

@template("cli", "easy")
def t_cli_has_flag(r: random.Random, i: int) -> Spec:
    argv = ["prog.py", "--verbose", "--n", "3"]
    flag = r.choice(["--verbose", "--missing"])
    expected = flag in argv
    base = "cli/easy/has_flag"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Does argv contain a flag?",
        topic="cli",
        difficulty="easy",
        prompt="Write `has_flag(argv, flag)` that returns True if `flag` is present in the argv list.",
        starter="""\
def has_flag(argv, flag):
    # TODO
    pass
""",
        tests=f"""\
assert has_flag({argv!r}, {flag!r}) == {expected}
assert has_flag({argv!r}, "--verbose") is True
""",
    )

@template("cli", "medium")
def t_cli_parse_flags_sim(r: random.Random, i: int) -> Spec:
    n = r.randint(1, 9)
    verbose = r.choice([True, False])
    argv = ["prog.py", "--n", str(n)]
    if verbose:
        argv.append("--verbose")
    expected = {"n": n, "verbose": verbose}
    base = "cli/medium/parse_flags"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Parse argv flags (simulated)",
        topic="cli",
        difficulty="medium",
        prompt="""Write `parse_flags(argv)` that parses:

- `--n <int>` (required)
- `--verbose` (optional)

Return a dict like `{"n": 5, "verbose": True}`.

`argv` will look like `["prog.py", "--n", "5", "--verbose"]`.
""",
        starter="""\
def parse_flags(argv):
    # TODO
    pass
""",
        tests=f"""\
argv = {argv!r}
assert parse_flags(argv) == {expected!r}
""",
    )

@template("cli", "medium")
def t_cli_parse_kv(r: random.Random, i: int) -> Spec:
    argv = ["prog.py", "a=1", "b=two", "c=3"]
    expected = {"a": "1", "b": "two", "c": "3"}
    base = "cli/medium/parse_kv"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Parse key=value args",
        topic="cli",
        difficulty="medium",
        prompt="Write `parse_kv(argv)` where argv looks like `['prog.py', 'a=1', 'b=two']`.\nReturn a dict mapping keys to values as strings.",
        starter="""\
def parse_kv(argv):
    # TODO
    pass
""",
        tests=f"""\
assert parse_kv({argv!r}) == {expected!r}
""",
    )

@template("cli", "hard")
def t_cli_dispatch(r: random.Random, i: int) -> Spec:
    base = "cli/hard/dispatch"
    slug = f"{base}/{slugname('problem', i)}"
    return Spec(
        slug=slug,
        title="Dispatch a subcommand",
        topic="cli",
        difficulty="hard",
        prompt="Write `dispatch(argv)`:\n- If argv[1] is 'add', return int(argv[2]) + int(argv[3])\n- If argv[1] is 'mul', return int(argv[2]) * int(argv[3])\nAssume argv is valid.",
        starter="""\
def dispatch(argv):
    # TODO
    pass
""",
        tests="""\
assert dispatch(["prog.py","add","2","3"]) == 5
assert dispatch(["prog.py","mul","4","5"]) == 20
""",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--each", type=int, default=1,
                    help="variants per selected exercise (default 1). Use >1 only if you WANT variations.")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--out", type=str, default=str(OUT_DEFAULT))
    ap.add_argument("--topics", type=str, default="all",
                    help="comma list of topics (numbers,strings,lists,...) or 'all'")
    ap.add_argument("--allow-reuse", action="store_true",
                    help="if a topic/difficulty has too few distinct templates, reuse templates to fill targets")
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()
    rng = random.Random(args.seed)

    if args.clear and out_dir.exists():
        for p in out_dir.rglob("*.toml"):
            p.unlink()

    want_topics = None
    if args.topics.strip().lower() != "all":
        want_topics = {t.strip() for t in args.topics.split(",") if t.strip()}

    buckets: dict[tuple[str, str], list[Template]] = defaultdict(list)
    for t in REGISTRY:
        if want_topics and t.topic not in want_topics:
            continue
        buckets[(t.topic, t.difficulty)].append(t)

        import sys

    topics = sorted(
        {topic for (topic, _diff) in buckets.keys()},
        key=lambda t: TOPIC_ORDER.index(t) if t in TOPIC_ORDER else 999,
    )

    out_dir.mkdir(parents=True, exist_ok=True)

    def pick_templates(tpls: list[Template], k: int, topic: str, diff: str) -> list[Template]:
        if k <= 0 or not tpls:
            return []
        if len(tpls) >= k:
            # no reuse needed
            return rng.sample(tpls, k)

        if args.allow_reuse:
            # reuse, but balance: always pick among least-used templates
            used = defaultdict(int)
            picks: list[Template] = []
            for _ in range(k):
                m = min(used[t] for t in tpls)
                candidates = [t for t in tpls if used[t] == m]
                choice = rng.choice(candidates)
                used[choice] += 1
                picks.append(choice)
            return picks

        # default: don't fail, just warn and generate what we can
        print(
            f"WARNING: {topic}/{diff} has only {len(tpls)} templates; wanted {k}. "
            f"Generating {len(tpls)}. (Use --allow-reuse to fill targets.)",
            file=sys.stderr,
        )
        return list(tpls)

    written = 0
    per_bucket_written: dict[tuple[str, str], int] = defaultdict(int)
    per_template_calls: dict[Template, int] = defaultdict(int)

    for topic in topics:
        for diff in DIFF_ORDER:
            target = TARGET_PER_TOPIC[diff]
            tpls = buckets.get((topic, diff), [])
            chosen = pick_templates(tpls, target, topic, diff)

            for tpl in chosen:
                for _ in range(args.each):
                    per_template_calls[tpl] += 1
                    spec = tpl.fn(rng, per_template_calls[tpl])
                    write_toml(out_dir, spec)
                    written += 1
                    per_bucket_written[(topic, diff)] += 1

    # Summary
    print(f"Wrote {written} file(s) to: {out_dir}")
    for topic in topics:
        parts = []
        for diff in DIFF_ORDER:
            n = per_bucket_written.get((topic, diff), 0)
            if n:
                parts.append(f"{diff}:{n}")
        if parts:
            print(f"  {topic}: " + ", ".join(parts))


if __name__ == "__main__":
    main()

