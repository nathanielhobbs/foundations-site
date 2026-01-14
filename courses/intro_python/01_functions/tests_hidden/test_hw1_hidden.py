import pytest
import student

def test_divide_by_zero_raises():
    with pytest.raises(ZeroDivisionError):
        student.divide(1, 0)

def test_mean_no_args_raises():
    with pytest.raises(ValueError):
        student.mean()

def test_more_mean_cases():
    assert student.mean(7) == 7
    assert student.mean(-1, -3) == -2

def test_float_ops():
    assert student.add(0.1, 0.2) == pytest.approx(0.3)
    assert student.multiply(0.5, 0.2) == pytest.approx(0.1)
