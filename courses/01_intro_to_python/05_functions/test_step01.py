import student

def test_square():
    assert student.square(0) == 0
    assert student.square(2) == 4
    assert student.square(-3) == 9
