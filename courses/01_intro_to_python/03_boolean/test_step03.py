import student

def test_should_apply_discount():
    assert student.should_apply_discount(100, False) is True
    assert student.should_apply_discount(99.99, False) is False
    assert student.should_apply_discount(20, True) is True
    assert student.should_apply_discount(20, False) is False
