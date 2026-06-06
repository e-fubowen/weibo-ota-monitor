from weibo_fetcher import parse_date, filter_by_date


def test_parse_date_valid():
    date_str = "Sat May 15 12:00:00 +0800 2026"
    result = parse_date(date_str)
    assert result.startswith("2026-05-15")


def test_parse_date_invalid():
    result = parse_date("bad-date")
    assert result == "0000-00-00 00:00:00"


def test_filter_by_date_no_filter():
    weibos = [{"created_at": "foo"}, {"created_at": "bar"}]
    result = filter_by_date(weibos, None, None)
    assert len(result) == 2


def test_filter_by_date_start_only(monkeypatch):
    weibos = [
        {"created_at": "Thu May 14 10:00:00 +0800 2026"},
        {"created_at": "Sat May 16 10:00:00 +0800 2026"},
    ]
    result = filter_by_date(weibos, "2026-05-15", None)
    assert len(result) == 1
