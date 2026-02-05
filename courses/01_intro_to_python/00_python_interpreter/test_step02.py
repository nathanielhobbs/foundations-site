import math
import student

def test_total():
    assert math.isclose(student.total, student.price * student.qty)
