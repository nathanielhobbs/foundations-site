import math
import student

def test_mean_basic():
    assert math.isclose(student.mean([1, 2, 3]), 2.0)
    assert math.isclose(student.mean([10]), 10.0)

def test_mean_empty_raises():
    try:
        student.mean([])
        assert False, "expected ValueError"
    except ValueError:
        pass
