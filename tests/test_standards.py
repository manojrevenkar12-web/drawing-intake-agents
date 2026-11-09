import pytest

from dia.standards import iso286, iso2768


@pytest.mark.parametrize(
    ("code", "nominal", "lower", "upper"),
    [
        ("H7", 25, 0.0, 0.021),
        ("g6", 25, -0.020, -0.007),
        ("f7", 40, -0.050, -0.025),
        ("h6", 10, -0.009, 0.0),
        ("H8", 42, 0.0, 0.039),
        ("js6", 10, -0.0045, 0.0045),
        ("H7", 3, 0.0, 0.010),
        ("H7", 3.01, 0.0, 0.012),
    ],
)
def test_iso286_limits(code, nominal, lower, upper):
    lim = iso286.fit_limits(code, nominal)
    assert lim.lower == pytest.approx(lower) and lim.upper == pytest.approx(upper)


def test_unsupported_class_is_refused_not_guessed():
    with pytest.raises(KeyError):
        iso286.fit_limits("k6", 20)
    with pytest.raises(ValueError):
        iso286.fit_limits("H7", 600)


@pytest.mark.parametrize(
    ("cls", "nominal", "dev"),
    [("m", 2, 0.1), ("m", 25, 0.2), ("m", 150, 0.5), ("f", 50, 0.15), ("c", 10, 0.5), ("m", 0.5, 0.1)],
)
def test_iso2768(cls, nominal, dev):
    assert iso2768.deviation(cls, nominal) == dev


@pytest.mark.parametrize(
    ("text", "cls"),
    [("ISO 2768-m", "m"), ("DIN ISO 2768-fK", "f"), ("TOLERANCES TO ISO 2768-c", "c"), ("ISO 286", None)],
)
def test_iso2768_class_from_text(text, cls):
    assert iso2768.parse_class(text) == cls


def test_best_grade():
    assert iso286.best_grade(0.021, 25) == 7
    assert iso286.best_grade(0.005, 25) is None
