
import math
import student

#def test_defined():
#    for name in ["a","b","sum_ab","diff_ab","prod_ab","quot_ab","pow_ab"]:
#        assert hasattr(student, name), f"Missing: {name}"

def test_relationships():
    a = student.a
    b = student.b
    assert student.sum_ab  == a + b
    assert student.diff_ab == a - b
    assert student.prod_ab == a * b
    assert student.pow_ab  == a ** b
    assert math.isclose(student.quot_ab, a / b)
