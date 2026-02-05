import math
import student

def test_conversion():
    assert isinstance(student.items, str)
    assert isinstance(student.items_int, int)
    assert student.items_int == 3

def test_total():
    assert isinstance(student.total, float)
    assert math.isclose(student.total, student.items_int * student.price_each)
