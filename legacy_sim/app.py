"""Starlette implementation of ``legacy/openapi.yaml``.

Deliberately unauthenticated: this is the legacy system the MCP server is
built to secure. Run with ``python -m legacy_sim`` (port 8080) or mount
``create_app()`` in-process for tests.
"""

import json
import os

import yaml
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from legacy_sim.store import BadRequest, NotFound, Store

SPEC_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         "legacy", "openapi.yaml")


def _error(status, code, message):
    return JSONResponse({"error": code, "message": message},
                        status_code=status)


def create_app(store=None):
    store = store or Store()

    def q(request, name, default=None):
        return request.query_params.get(name, default)

    async def healthz(request: Request):
        return JSONResponse({"status": "ok", "now": store.now().isoformat()})

    async def openapi(request: Request):
        with open(SPEC_PATH, encoding="utf-8") as f:
            return JSONResponse(yaml.safe_load(f))

    async def services(request: Request):
        return JSONResponse(store.search_services(
            q(request, "q"), q(request, "cursor"), q(request, "limit")))

    async def service(request: Request):
        return JSONResponse(store.get_service(request.path_params["id"]))

    async def service_metrics(request: Request):
        return JSONResponse(store.service_metrics(
            request.path_params["id"], q(request, "window", "24h")))

    async def incidents(request: Request):
        return JSONResponse(store.search_incidents(
            service_id=q(request, "service_id"),
            severity=q(request, "severity"), status=q(request, "status"),
            category=q(request, "category"), since=q(request, "since"),
            q=q(request, "q"), cursor=q(request, "cursor"),
            limit=q(request, "limit")))

    async def incident(request: Request):
        return JSONResponse(store.get_incident(request.path_params["id"]))

    async def incident_comments(request: Request):
        body = await _json(request)
        comment, created = store.add_comment(
            request.path_params["id"], body.get("author"),
            body.get("text"), body.get("idempotency_key"))
        return JSONResponse(comment, status_code=201 if created else 200)

    async def change_requests(request: Request):
        return JSONResponse(store.search_change_requests(
            status=q(request, "status"), service_id=q(request, "service_id"),
            q=q(request, "q"), cursor=q(request, "cursor"),
            limit=q(request, "limit")))

    async def change_request(request: Request):
        cr = dict(store.get_change_request(request.path_params["id"]))
        cr["stories"] = store.stories_for(cr["cr_id"])
        return JSONResponse(cr)

    async def cr_stories(request: Request):
        cr_id = request.path_params["id"]
        if request.method == "GET":
            return JSONResponse({"items": store.stories_for(cr_id)})
        body = await _json(request)
        stories, created = store.add_stories(
            cr_id, body.get("stories"), body.get("idempotency_key"))
        return JSONResponse({"items": stories},
                            status_code=201 if created else 200)

    async def deployments(request: Request):
        return JSONResponse(store.search_deployments(
            service_id=q(request, "service_id"), since=q(request, "since"),
            cursor=q(request, "cursor"), limit=q(request, "limit")))

    routes = [
        Route("/healthz", healthz),
        Route("/openapi.json", openapi),
        Route("/services", services),
        Route("/services/{id}", service),
        Route("/services/{id}/metrics", service_metrics),
        Route("/incidents", incidents),
        Route("/incidents/{id}", incident),
        Route("/incidents/{id}/comments", incident_comments,
              methods=["POST"]),
        Route("/change-requests", change_requests),
        Route("/change-requests/{id}", change_request),
        Route("/change-requests/{id}/stories", cr_stories,
              methods=["GET", "POST"]),
        Route("/deployments", deployments),
    ]
    app = Starlette(routes=routes, exception_handlers={
        NotFound: lambda r, e: _error(404, "not_found", str(e)),
        BadRequest: lambda r, e: _error(400, "bad_request", str(e)),
    })
    app.state.store = store
    return app


async def _json(request):
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise BadRequest("body must be JSON") from exc
    if not isinstance(body, dict):
        raise BadRequest("body must be a JSON object")
    return body
