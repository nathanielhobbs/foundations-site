import math
import student

def test_safe_div():
    assert student.safe_div(10, 0) is None
    assert student.safe_div(10, 0.0) is None
    assert math.isclose(student.safe_div(10, 2), 5.0)
    assert math.isclose(student.safe_div(-9, 3), -3.0)
