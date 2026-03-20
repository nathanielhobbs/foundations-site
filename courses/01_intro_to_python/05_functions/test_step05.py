import math
import student

def test_analyze_text():
    chars, words, avg = student.analyze_text("data science")
    assert chars == 12
    assert words == 2
    assert math.isclose(avg, 5.5)

    chars, words, avg = student.analyze_text("   ")
    assert words == 0
    assert math.isclose(avg, 0.0)
