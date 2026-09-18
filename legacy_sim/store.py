"""In-memory store over the seed dataset, with the query semantics that
``legacy/openapi.yaml`` promises. Kept free of any web framework so the
contract tests and the MCP server tests can use it directly."""

import base64
import copy
from datetime import UTC, datetime, timedelta

from legacy_sim.seed import NOW, build_dataset

MAX_LIMIT = 50
DEFAULT_LIMIT = 20
WINDOWS = {"24h": timedelta(hours=24), "7d": timedelta(days=7),
           "30d": timedelta(days=30)}


class NotFound(Exception):
    pass


class BadRequest(Exception):
    pass


def _parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def encode_cursor(offset):
    return base64.urlsafe_b64encode(f"offset:{offset}".encode()).decode()


def decode_cursor(cursor):
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        assert raw.startswith("offset:")
        return int(raw.split(":", 1)[1])
    except Exception as exc:  # noqa: BLE001 - any malformed cursor
        raise BadRequest("invalid cursor") from exc


def paginate(rows, cursor, limit):
    limit = DEFAULT_LIMIT if limit is None else int(limit)
    if limit < 1 or limit > MAX_LIMIT:
        raise BadRequest(f"limit must be between 1 and {MAX_LIMIT}")
    offset = decode_cursor(cursor)
    page = rows[offset:offset + limit]
    next_cursor = (encode_cursor(offset + limit)
                   if offset + limit < len(rows) else None)
    return {"items": page, "next_cursor": next_cursor, "total": len(rows)}


class Store:
    def __init__(self, data=None):
        self.data = copy.deepcopy(data) if data else build_dataset()
        self.services = {s["service_id"]: s for s in self.data["services"]}
        self.incidents = {i["incident_id"]: i for i in self.data["incidents"]}
        self.change_requests = {c["cr_id"]: c
                                for c in self.data["change_requests"]}
        self.stories = list(self.data["stories"])
        self.deployments = list(self.data["deployments"])
        self.metrics = {}
        for m in self.data["metrics"]:
            self.metrics.setdefault(m["service_id"], []).append(m)
        self._idempotency = {}
        self._comment_seq = 1
        self._story_seq = len(self.stories) + 1

    # ---- services --------------------------------------------------------
    def search_services(self, q=None, cursor=None, limit=None):
        rows = list(self.services.values())
        if q:
            needle = q.strip().lower()
            if needle.upper() in self.services:
                rows = [self.services[needle.upper()]]
            else:
                needle_n = needle.replace(" ", "").replace("-", "")

                def score(s):
                    names = [s["name"]] + s["aliases"]
                    normal = [n.lower().replace(" ", "").replace("-", "")
                              for n in names]
                    if needle in (n.lower() for n in names):
                        return 3
                    if needle_n in normal:
                        return 2
                    if any(needle_n in n or n in needle_n for n in normal):
                        return 1
                    return 0
                rows = sorted((s for s in rows if score(s) > 0),
                              key=lambda s: (-score(s), s["name"]))
        return paginate(rows, cursor, limit)

    def get_service(self, service_id):
        try:
            return self.services[service_id]
        except KeyError:
            raise NotFound(f"service {service_id} not found") from None

    # ---- incidents -------------------------------------------------------
    def search_incidents(self, service_id=None, severity=None, status=None,
                         category=None, since=None, q=None, cursor=None,
                         limit=None):
        rows = list(self.incidents.values())
        if service_id:
            rows = [r for r in rows if r["service_id"] == service_id]
        if severity:
            rows = [r for r in rows if r["severity"] == severity]
        if status:
            rows = [r for r in rows if r["status"] == status]
        if category:
            rows = [r for r in rows if r["category"] == category]
        if since:
            try:
                since_ts = _parse_ts(since)
            except ValueError as exc:
                raise BadRequest("since must be an ISO-8601 timestamp") \
                    from exc
            rows = [r for r in rows if _parse_ts(r["opened_at"]) >= since_ts]
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in r["title"].lower()
                    or needle in r["description"].lower()]
        rows.sort(key=lambda r: r["opened_at"], reverse=True)
        summaries = [self._incident_summary(r) for r in rows]
        return paginate(summaries, cursor, limit)

    @staticmethod
    def _incident_summary(r):
        return {k: r[k] for k in ("incident_id", "service_id", "severity",
                                  "status", "category", "title", "opened_at",
                                  "resolved_at", "source_ref")}

    def get_incident(self, incident_id):
        try:
            return self.incidents[incident_id]
        except KeyError:
            raise NotFound(f"incident {incident_id} not found") from None

    def add_comment(self, incident_id, author, text, idempotency_key):
        inc = self.get_incident(incident_id)
        if not text or not text.strip():
            raise BadRequest("text is required")
        if not idempotency_key:
            raise BadRequest("idempotency_key is required")
        key = ("comment", incident_id, idempotency_key)
        if key in self._idempotency:
            return self._idempotency[key], False
        cid = f"CMT-{self._comment_seq:04d}"
        self._comment_seq += 1
        comment = {
            "comment_id": cid,
            "author": author or "agent",
            "text": text,
            "created_at": NOW.isoformat().replace("+00:00", "Z"),
            "source_ref": f"comment:{cid}",
        }
        inc["comments"].append(comment)
        self._idempotency[key] = comment
        return comment, True

    # ---- change requests -------------------------------------------------
    def search_change_requests(self, status=None, service_id=None, q=None,
                               cursor=None, limit=None):
        rows = list(self.change_requests.values())
        if status:
            rows = [r for r in rows if r["status"] == status]
        if service_id:
            rows = [r for r in rows if service_id in r["target_services"]]
        if q:
            needle = q.lower()
            rows = [r for r in rows if needle in r["title"].lower()
                    or needle in r["brd_text"].lower()]
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        summaries = [{k: r[k] for k in ("cr_id", "title", "status",
                                       "requested_by_team",
                                       "target_services", "created_at",
                                       "source_ref")} for r in rows]
        return paginate(summaries, cursor, limit)

    def get_change_request(self, cr_id):
        try:
            return self.change_requests[cr_id]
        except KeyError:
            raise NotFound(f"change request {cr_id} not found") from None

    def stories_for(self, cr_id):
        self.get_change_request(cr_id)
        return [s for s in self.stories if s["cr_id"] == cr_id]

    def add_stories(self, cr_id, stories, idempotency_key):
        self.get_change_request(cr_id)
        if not idempotency_key:
            raise BadRequest("idempotency_key is required")
        if not isinstance(stories, list) or not stories:
            raise BadRequest("stories must be a non-empty list")
        for s in stories:
            if s.get("type") not in ("user", "technical"):
                raise BadRequest("story.type must be user or technical")
            if not s.get("title"):
                raise BadRequest("story.title is required")
            if not isinstance(s.get("acceptance_criteria", []), list):
                raise BadRequest("acceptance_criteria must be a list")
        key = ("stories", cr_id, idempotency_key)
        if key in self._idempotency:
            return self._idempotency[key], False
        created = []
        for s in stories:
            sid = f"ST-{self._story_seq:04d}"
            self._story_seq += 1
            story = {
                "story_id": sid,
                "cr_id": cr_id,
                "type": s["type"],
                "title": s["title"],
                "acceptance_criteria": list(s.get("acceptance_criteria", [])),
                "depends_on": list(s.get("depends_on", [])),
                "draft": True,
                "created_at": NOW.isoformat().replace("+00:00", "Z"),
                "source_ref": f"story:{sid}",
            }
            self.stories.append(story)
            created.append(story)
        self._idempotency[key] = created
        return created, True

    # ---- deployments and metrics ----------------------------------------
    def search_deployments(self, service_id=None, since=None, cursor=None,
                           limit=None):
        rows = list(self.deployments)
        if service_id:
            rows = [r for r in rows if r["service_id"] == service_id]
        if since:
            since_ts = _parse_ts(since)
            rows = [r for r in rows
                    if _parse_ts(r["deployed_at"]) >= since_ts]
        rows.sort(key=lambda r: r["deployed_at"], reverse=True)
        return paginate(rows, cursor, limit)

    def service_metrics(self, service_id, window="24h"):
        self.get_service(service_id)
        if window not in WINDOWS:
            raise BadRequest("window must be one of 24h, 7d, 30d")
        start = NOW - WINDOWS[window]
        rows = [m for m in self.metrics.get(service_id, [])
                if _parse_ts(m["ts"]) >= start]
        if not rows:
            raise NotFound(f"no metrics for {service_id}")

        def agg(field):
            values = [r[field] for r in rows]
            peak = max(rows, key=lambda r: r[field])
            return {"avg": round(sum(values) / len(values), 3),
                    "max": peak[field], "max_at": peak["ts"]}
        return {
            "service_id": service_id,
            "window": window,
            "from": start.isoformat().replace("+00:00", "Z"),
            "to": NOW.isoformat().replace("+00:00", "Z"),
            "samples": len(rows),
            "p95_ms": agg("p95_ms"),
            "error_rate": agg("error_rate"),
            "db_round_trips": agg("db_round_trips"),
            "kafka_lag": agg("kafka_lag"),
            "source_ref": f"metric:{service_id}:{window}",
        }

    def now(self):
        return NOW.astimezone(UTC)
