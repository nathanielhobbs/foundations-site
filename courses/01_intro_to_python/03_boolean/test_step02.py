import student

def test_is_even():
    assert student.is_even(0) is True
    assert student.is_even(2) is True
    assert student.is_even(3) is False
    assert student.is_even(-4) is True
    assert student.is_even(-5) is False
