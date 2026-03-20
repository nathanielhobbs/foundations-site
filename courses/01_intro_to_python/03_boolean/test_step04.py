import student

def test_nonempty():
    assert student.nonempty("hi") is True
    assert student.nonempty("  hi  ") is True
    assert student.nonempty("   ") is False
    assert student.nonempty("") is False
    assert student.nonempty(None) is False
    assert student.nonempty(123) is False
