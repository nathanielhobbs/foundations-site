import student

def test_slugify():
    assert student.slugify("  Intro to Python!!!  ") == "intro-to-python"
    assert student.slugify("Data   Science 101") == "data-science-101"
    assert student.slugify("Hello---World") == "hello-world"
    assert student.slugify("   ") == ""
