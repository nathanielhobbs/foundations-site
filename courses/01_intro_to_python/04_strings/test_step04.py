import student

def test_csv_row():
    assert student.csv_row([1, "Ada", 3.5]) == "1,Ada,3.5"
    assert student.csv_row([]) == ""
    assert student.csv_row(["x"]) == "x"
