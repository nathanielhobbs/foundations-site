import student

def test_first_last():
    assert student.first_last("hi") == ("h", "i")
    assert student.first_last("a") == ("a", "a")
    assert student.first_last("") == ("", "")
