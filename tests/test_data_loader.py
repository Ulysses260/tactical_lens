import pytest

from tactical_lens.data_loader import parse_location, auto_load


def test_parse_location_valid():
    x, y = parse_location("[10, 20]")
    assert x == 10 and y == 20


def test_parse_location_invalid():
    x, y = parse_location("not a json")
    assert x is None and y is None


def test_auto_load_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        auto_load("this_file_should_not_exist_12345.csv")
