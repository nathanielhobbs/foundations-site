import student

def test_count_vowels():
    assert student.count_vowels("apple") == 2
    assert student.count_vowels("BANANA") == 3
    assert student.count_vowels("") == 0
    assert student.count_vowels("rhythm") == 0
