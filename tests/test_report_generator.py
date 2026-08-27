from tactical_lens.report_generator import _get_styles


def test_get_styles_returns_styles():
    styles = _get_styles()
    assert isinstance(styles, dict)
    assert 'title_main' in styles
    assert 'body' in styles
