import math
import student

def test_conversions():
    assert student.x_str == "19"
    assert student.y_str == "2.5"
    assert isinstance(student.x, int)
    assert isinstance(student.y, float)
    assert student.x == 19
    assert math.isclose(student.y, 2.5)

def test_sum_and_trunc():
    assert isinstance(student.sum_xy, float)
    assert math.isclose(student.sum_xy, student.x + student.y)
    assert isinstance(student.y_trunc, int)
    assert student.y_trunc == 2
