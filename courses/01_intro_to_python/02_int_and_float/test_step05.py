
import student

def test_time_conversion():
    assert isinstance(student.minutes, int)
    assert student.minutes > 0
    assert student.hours * 60 + student.mins == student.minutes
    assert 0 <= student.mins < 60
