
import math
import student

def test_division_identities():
    assert student.true_div  == student.i / student.j
    assert student.floor_div == student.i // student.j
    assert student.remainder == student.i % student.j

def test_types():
    assert isinstance(student.i, int)
    assert isinstance(student.j, int)
    assert isinstance(student.true_div, float)
    assert isinstance(student.floor_div, int)
    assert isinstance(student.remainder, int)
    assert isinstance(student.as_float, float)
    assert student.trunc_int == 3
