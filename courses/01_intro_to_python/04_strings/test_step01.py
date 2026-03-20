import student

def test_make_greeting():
    assert student.make_greeting("Ada") == "Hello, Ada!"
    assert student.make_greeting("  Ada  ") == "Hello, Ada!"
    assert student.make_greeting("") == "Hello there!"
    assert student.make_greeting("   ") == "Hello there!"
