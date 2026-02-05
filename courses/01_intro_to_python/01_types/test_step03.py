import math
import student

def test_total():
    assert isinstance(student.total, float)
    assert math.isclose(student.total, student.items * student.price_each)

def test_line():
    assert isinstance(student.line, str)
    assert student.line == student.msg + str(student.total)
