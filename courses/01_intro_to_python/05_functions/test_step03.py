import student

def test_append_new():
    a = [1, 2]
    b = student.append_new(a, 3)
    assert a == [1, 2]
    assert b == [1, 2, 3]
    assert b is not a
