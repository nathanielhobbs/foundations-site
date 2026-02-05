import math
import student

def test_results():
    assert student.result_add == student.x + student.y
    assert student.result_mul == student.x * student.y
    assert math.isclose(student.result_div, student.x / student.y)

def test_types():
    assert isinstance(student.x, int)
    assert isinstance(student.y, int)
    assert isinstance(student.result_add, int)
    assert isinstance(student.result_mul, int)
    assert isinstance(student.result_div, float)
