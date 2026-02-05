
import math
import student

def test_total():
    expected_tax = student.bill * student.tax_rate
    expected_tip = student.bill * student.tip_rate
    expected_total = student.bill + expected_tax + expected_tip
    assert math.isclose(student.tax, expected_tax)
    assert math.isclose(student.tip, expected_tip)
    assert math.isclose(student.total, expected_total)
