"""mcp-fetch - web and REST API connector.

See docs/05-mcp-connectors.md #5.4. The host allow-list is the mandatory
safety control here (#5.7): this connector must never fetch an arbitrary
LLM- or user-supplied URL, only hosts in ALLOWED_HOSTS (comma-separated env
var), which prevents SSRF and keeps data sourcing to "approved KESO data"
(the architecture's key principle).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ALLOWED_HOSTS = {h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()}

app = FastAPI(title="mcp-fetch")


class ToolCallRequest(BaseModel):
    args: dict
    context: dict


def _check_allowed(url: str) -> None:
    host = urlparse(url).hostname
    if host not in ALLOWED_HOSTS:
        raise HTTPException(status_code=403, detail=f"Host '{host}' is not in the approved allow-list")


def _provenance(uri: str) -> dict:
    return {"source_system": "gis", "source_uri": uri, "retrieved_at": datetime.now(timezone.utc).isoformat()}


@app.get("/health")
async def health():
    return {"status": "ok", "allowed_hosts": sorted(ALLOWED_HOSTS)}


@app.get("/tools")
async def list_tools():
    return {"tools": ["fetch_json", "fetch_geojson"]}


@app.post("/tools/fetch_json/call")
async def fetch_json(req: ToolCallRequest):
    url = req.args["url"]
    method = req.args.get("method", "GET").upper()
    params = req.args.get("params")
    _check_allowed(url)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, url, params=params)
        resp.raise_for_status()
        data = resp.json()

    return {"result": data, "provenance": _provenance(url)}


@app.post("/tools/fetch_geojson/call")
async def fetch_geojson(req: ToolCallRequest):
    url = req.args.get("url")
    layer_id = req.args.get("layer_id")
    if not url and layer_id:
        gis_base = next(iter(ALLOWED_HOSTS), None)
        if gis_base is None:
            raise HTTPException(status_code=500, detail="No GIS host configured")
        url = f"https://{gis_base}/layers/{layer_id}/geojson"
    if not url:
        raise HTTPException(status_code=400, detail="url or layer_id is required")

    _check_allowed(url)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    return {"result": data, "provenance": _provenance(url)}
