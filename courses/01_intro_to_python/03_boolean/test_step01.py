import student

def test_as_bool_matches_python():
    for v in [0, 1, -1, "", " ", [], [0], None, {}, {"x": 1}]:
        out = student.as_bool(v)
        assert type(out) is bool
        assert out == bool(v)
