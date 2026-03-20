import student

def test_clamp():
    assert student.clamp(-1) == 0
    assert student.clamp(0.5) == 0.5
    assert student.clamp(2) == 1
    assert student.clamp(10, lo=0, hi=100) == 10
    assert student.clamp(-5, lo=-3, hi=3) == -3
