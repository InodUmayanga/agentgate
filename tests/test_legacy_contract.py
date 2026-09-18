"""Conformance suite for legacy/openapi.yaml.

Runs in-process against legacy_sim by default. Set LEGACY_BASE_URL to run
the same suite against another implementation (e.g. the Spring Boot module)
— that is the definition of "implements the contract".
"""

import asyncio
import os

import httpx
import jsonschema
import yaml

from legacy_sim.app import create_app
from legacy_sim.seed import NOW, build_dataset, dataset_digest
from legacy_sim.store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "legacy", "openapi.yaml"),
          encoding="utf-8") as _f:
    SPEC = yaml.safe_load(_f)

BASE_URL = os.getenv("LEGACY_BASE_URL")
# One shared read-only app for the in-process runs; write tests build their
# own Store so they never see each other's comments or stories.
_APP = None if BASE_URL else create_app()


def _client():
    if BASE_URL:
        return httpx.AsyncClient(base_url=BASE_URL, timeout=10)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=_APP),
                             base_url="http://legacy")


def call(method, path, **kwargs):
    async def go():
        async with _client() as c:
            return await c.request(method, path, **kwargs)
    return asyncio.run(go())


def validate(instance, schema_name):
    """Validate against a component schema, resolving internal $refs."""
    schema = {"$ref": f"#/components/schemas/{schema_name}",
              "components": SPEC["components"]}
    jsonschema.validate(instance, schema,
                        cls=jsonschema.Draft202012Validator)


def test_dataset_is_deterministic():
    assert dataset_digest(build_dataset()) == dataset_digest(build_dataset())
    data = build_dataset()
    assert len(data["services"]) == 40
    assert len(data["incidents"]) == 200
    assert len(data["change_requests"]) == 30


def test_healthz_and_openapi():
    assert call("GET", "/healthz").status_code == 200
    r = call("GET", "/openapi.json")
    assert r.status_code == 200 and r.json()["info"]["title"] == \
        SPEC["info"]["title"]


def test_service_search_ranks_alias_and_id():
    r = call("GET", "/services", params={"q": "order gw"})
    assert r.status_code == 200
    body = r.json()
    validate(body["items"][0], "Service")
    assert body["items"][0]["service_id"] == "SVC-007"
    assert call("GET", "/services", params={"q": "SVC-007"}).json()[
        "items"][0]["name"] == "order-gateway"
    assert call("GET", "/services", params={"q": "OGW"}).json()[
        "items"][0]["service_id"] == "SVC-007"
    assert call("GET", "/services", params={"q": "zzz-nope"}).json()[
        "items"] == []


def test_service_get_and_404_shape():
    validate(call("GET", "/services/SVC-007").json(), "Service")
    r = call("GET", "/services/SVC-999")
    assert r.status_code == 404
    validate(r.json(), "Error")
    assert r.json()["error"] == "not_found"


def test_incident_search_filters_and_pagination():
    r = call("GET", "/incidents",
             params={"service_id": "SVC-007", "limit": 5})
    body = r.json()
    assert r.status_code == 200 and 0 < len(body["items"]) <= 5
    for item in body["items"]:
        validate(item, "IncidentSummary")
        assert item["service_id"] == "SVC-007"
    # newest first
    opened = [i["opened_at"] for i in body["items"]]
    assert opened == sorted(opened, reverse=True)
    # cursor walks the whole result set without duplicates
    seen, cursor, total = [], None, body["total"]
    while True:
        page = call("GET", "/incidents", params={
            "service_id": "SVC-007", "limit": 5,
            **({"cursor": cursor} if cursor else {})}).json()
        seen += [i["incident_id"] for i in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == total
    # filters
    sev = call("GET", "/incidents", params={"severity": "S1"}).json()
    assert sev["items"] and all(i["severity"] == "S1" for i in sev["items"])
    st = call("GET", "/incidents", params={"status": "open"}).json()
    assert st["items"] and all(i["status"] == "open" for i in st["items"])
    q = call("GET", "/incidents", params={"q": "consumer lag"}).json()
    assert q["items"] and all("lag" in i["title"].lower()
                              for i in q["items"])
    since = call("GET", "/incidents",
                 params={"since": "2026-09-14T00:00:00Z"}).json()
    assert all(i["opened_at"] >= "2026-09-14T00:00:00Z"
               for i in since["items"])


def test_incident_search_rejects_bad_input():
    assert call("GET", "/incidents", params={"limit": 0}).status_code == 400
    assert call("GET", "/incidents", params={"limit": 51}).status_code == 400
    assert call("GET", "/incidents",
                params={"cursor": "garbage"}).status_code == 400
    assert call("GET", "/incidents",
                params={"since": "yesterday"}).status_code == 400


def test_fixed_incidents_exist_with_expected_shape():
    inc = call("GET", "/incidents/INC-1042").json()
    validate(inc, "Incident")
    assert inc["service_id"] == "SVC-007" and inc["status"] == "mitigated"
    assert inc["category"] == "kafka_lag" and inc["root_cause"] is None
    assert [t["event"] for t in inc["timeline"]] == [
        "detected", "acknowledged", "mitigated"]
    assert all(t["source_ref"].startswith("timeline:INC-1042:")
               for t in inc["timeline"])
    precedent = call("GET", "/incidents/INC-1017").json()
    assert precedent["status"] == "resolved" and precedent["root_cause"]
    injected = call("GET", "/incidents/INC-1077").json()
    assert "ignore your previous instructions" in injected["description"]
    pii = call("GET", "/incidents/INC-1090").json()
    assert "@example.com" in pii["comments"][0]["text"]


def test_incident_404():
    r = call("GET", "/incidents/INC-0001")
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_comment_post_is_idempotent():
    app = create_app(Store())

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://legacy") as c:
            body = {"author": "agent", "text": "RCA draft attached",
                    "idempotency_key": "k-1"}
            first = await c.post("/incidents/INC-1042/comments", json=body)
            replay = await c.post("/incidents/INC-1042/comments", json=body)
            other = await c.post("/incidents/INC-1042/comments",
                                 json={**body, "idempotency_key": "k-2"})
            missing = await c.post("/incidents/INC-1042/comments",
                                   json={"text": "no key"})
            empty = await c.post("/incidents/INC-1042/comments",
                                 json={"text": " ", "idempotency_key": "k"})
            gone = await c.post("/incidents/INC-0001/comments", json=body)
            inc = await c.get("/incidents/INC-1042")
            return first, replay, other, missing, empty, gone, inc
    if BASE_URL:
        return  # write tests run only against the in-process simulator
    first, replay, other, missing, empty, gone, inc = asyncio.run(go())
    assert first.status_code == 201
    validate(first.json(), "Comment")
    assert replay.status_code == 200 and replay.json() == first.json()
    assert other.status_code == 201 and other.json()["comment_id"] != \
        first.json()["comment_id"]
    assert missing.status_code == 400 and empty.status_code == 400
    assert gone.status_code == 404
    assert len(inc.json()["comments"]) == 2


def test_change_requests_search_get_and_stories():
    r = call("GET", "/change-requests", params={"status": "proposed"})
    assert r.status_code == 200 and r.json()["items"]
    for item in r.json()["items"]:
        validate(item, "ChangeRequestSummary")
        assert item["status"] == "proposed"
    by_service = call("GET", "/change-requests",
                      params={"service_id": "SVC-007"}).json()
    assert {"CR-07", "CR-12"} <= {c["cr_id"] for c in by_service["items"]}
    cr = call("GET", "/change-requests/CR-07").json()
    validate(cr, "ChangeRequest")
    assert cr["status"] == "approved" and "Idempotency-Key" in cr["brd_text"]
    assert cr["stories"] == []
    injected = call("GET", "/change-requests/CR-19").json()
    assert "System override" in injected["brd_text"]
    stories = call("GET", "/change-requests/CR-07/stories").json()
    assert stories["items"] == []
    assert call("GET", "/change-requests/CR-99").status_code == 404


def test_story_post_creates_drafts_idempotently():
    if BASE_URL:
        return
    app = create_app(Store())

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://legacy") as c:
            body = {"idempotency_key": "groom-1", "stories": [
                {"type": "user", "title": "Retry a timed-out order safely",
                 "acceptance_criteria": ["No duplicate order is created"]},
                {"type": "technical",
                 "title": "Idempotency-Key store with 24h TTL",
                 "acceptance_criteria": ["Replay returns original body"],
                 "depends_on": []}]}
            first = await c.post("/change-requests/CR-07/stories", json=body)
            replay = await c.post("/change-requests/CR-07/stories",
                                  json=body)
            bad = await c.post("/change-requests/CR-07/stories", json={
                "idempotency_key": "x",
                "stories": [{"type": "epic", "title": "nope"}]})
            listed = await c.get("/change-requests/CR-07/stories")
            return first, replay, bad, listed
    first, replay, bad, listed = asyncio.run(go())
    assert first.status_code == 201
    items = first.json()["items"]
    assert len(items) == 2 and all(s["draft"] for s in items)
    for s in items:
        validate(s, "Story")
    assert replay.status_code == 200 and replay.json() == first.json()
    assert bad.status_code == 400
    assert len(listed.json()["items"]) == 2


def test_deployments_and_metrics():
    r = call("GET", "/deployments", params={"service_id": "SVC-007",
                                            "limit": 10})
    assert r.status_code == 200
    for d in r.json()["items"]:
        validate(d, "Deployment")
        assert d["service_id"] == "SVC-007"
    for window in ("24h", "7d", "30d"):
        m = call("GET", "/services/SVC-007/metrics",
                 params={"window": window}).json()
        validate(m, "MetricsWindow")
        assert m["window"] == window and m["samples"] > 0
        assert m["to"] == NOW.isoformat().replace("+00:00", "Z")
    week = call("GET", "/services/SVC-007/metrics",
                params={"window": "7d"}).json()
    # INC-1042 (6h ago) planted a Kafka-lag spike on SVC-007
    assert week["kafka_lag"]["max"] >= 12000
    assert call("GET", "/services/SVC-007/metrics",
                params={"window": "1h"}).status_code == 400
    assert call("GET", "/services/SVC-999/metrics").status_code == 404
