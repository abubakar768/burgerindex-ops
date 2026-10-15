"""Fixtures mirror real failed runs seen on the dashboard (Oct 5-9, 2026)."""
from datetime import datetime, timezone

from triage.history import triage
from triage.rules import classify

DL = "downloader/response_status_count/"
EX = "downloader/exception_type_count/"


def job(name, stats, status="failed", items=0, start="2026-10-08T03:00:00Z", dur=600, reason="zero_items"):
    return {"name": name, "jobId": name + start, "status": status, "failureReason": reason,
            "itemScraped": items, "startTime": start, "durationSeconds": dur, "rawStats": stats}


def cat(stats, **kw):
    return classify(job("x", stats, **kw)).category


def test_noon_ksa_404_is_endpoint_changed():
    assert cat({"finish_reason": "finished", DL + "404": 1843, "log_count/ERROR": 2}) == "endpoint_changed"


def test_kfc_403_on_first_request_is_blocked():
    assert cat({"finish_reason": "finished", DL + "200": 1, DL + "403": 1}) == "blocked"


def test_407_is_proxy_auth():
    assert cat({"finish_reason": "finished", DL + "407": 33}) == "proxy_auth"


def test_gojek_zyte_request_error():
    assert cat({"finish_reason": "finished", EX + "zyte_api._errors.RequestError": 193}) == "zyte_error"


def test_deliveroo_kwt_network():
    s = {"finish_reason": "finished", DL + "200": 4, DL + "404": 1,
         EX + "twisted.web._newclient.ResponseFailed": 12}
    assert cat(s) == "network"


def test_google_places_timeout():
    assert cat({"finish_reason": "closespider_timeout_no_item"}, items=19135, reason="finish_reason") == "timeout"


def test_amazon_shutdown():
    assert cat({"finish_reason": "shutdown"}) == "shutdown"


def test_200s_with_zero_items_is_parse_broken():
    c = classify(job("x", {"finish_reason": "finished", DL + "200": 500}))
    assert c.category == "parse_broken" and c.fixable


def test_success_is_not_classified():
    assert classify(job("x", {}, status="success", items=100)) is None


def test_silent_drop_and_streak_and_lost():
    now = datetime(2026, 10, 9, 0, 0, tzinfo=timezone.utc)
    hist = [job("ue-ny", {}, status="success", items=n, start=f"2026-10-0{d}T01:00:00Z")
            for d, n in [(3, 3500), (4, 3400), (5, 3600), (6, 3552), (7, 3444)]]
    hist.append(job("ue-ny", {}, status="success", items=76, start="2026-10-08T01:00:00Z"))

    gojek = [job("gojek", {EX + "zyte_api._errors.RequestError": 193}, start=f"2026-10-0{d}T06:00:00Z")
             for d in (5, 6, 7, 8)]

    stuck = [job("grab-idn", {}, status="success", items=10, dur=3600, start="2026-10-01T08:00:00Z"),
             {"name": "grab-idn", "status": "running", "startTime": "2026-10-05T08:00:00Z"}]

    rows = {r["crawler"] + ":" + r["category"]: r for r in triage(hist + gojek + stuck, {"gojek"}, now)}
    assert rows["ue-ny:silent_drop"]["evidence"][0] == "items=76"
    assert rows["gojek:zyte_error"]["streak"] == 4 and rows["gojek:zyte_error"]["p0"]
    assert "grab-idn:lost" in rows
