"""mcp-sharepoint - DMS documents connector.

See docs/05-mcp-connectors.md #5.3. Uses an app-only Entra ID (Azure AD)
registration (client-credentials flow via MSAL) with read-only Microsoft
Graph permissions scoped to the approved document libraries. If credentials
are not configured (e.g. in a local dev environment without SharePoint
access), tools return an empty result with a `not_configured` flag rather
than failing the whole query -- the Orchestrator's Stage 2 (docs/06 #6.2)
already tolerates individual tool-call failures gracefully.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

import httpx
import msal
from fastapi import FastAPI
from pydantic import BaseModel

TENANT_ID = os.environ.get("SHAREPOINT_TENANT_ID")
CLIENT_ID = os.environ.get("SHAREPOINT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("SHAREPOINT_CLIENT_SECRET")
SITE_ID = os.environ.get("SHAREPOINT_SITE_ID")  # e.g. "keso.sharepoint.com,<site-guid>,<web-guid>"

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_CONFIGURED = bool(TENANT_ID and CLIENT_ID and CLIENT_SECRET and SITE_ID)

app = FastAPI(title="mcp-sharepoint")

_msal_app: msal.ConfidentialClientApplication | None = None
_token_cache: dict = {}


class ToolCallRequest(BaseModel):
    args: dict
    context: dict


def _get_msal_app() -> msal.ConfidentialClientApplication:
    global _msal_app
    if _msal_app is None:
        _msal_app = msal.ConfidentialClientApplication(
            client_id=CLIENT_ID,
            client_credential=CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
        )
    return _msal_app


def _get_token() -> str:
    if _token_cache.get("token") and _token_cache.get("expires_at", 0) > time.time() + 60:
        return _token_cache["token"]
    result = _get_msal_app().acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(f"Failed to acquire Graph token: {result.get('error_description')}")
    _token_cache["token"] = result["access_token"]
    _token_cache["expires_at"] = time.time() + result.get("expires_in", 3600)
    return result["access_token"]


def _provenance(uri: str | None) -> dict:
    return {"source_system": "sharepoint", "source_uri": uri, "retrieved_at": datetime.now(timezone.utc).isoformat()}


@app.get("/health")
async def health():
    return {"status": "ok", "configured": _CONFIGURED}


@app.get("/tools")
async def list_tools():
    return {"tools": ["search_documents", "get_document", "list_library"]}


@app.post("/tools/search_documents/call")
async def search_documents(req: ToolCallRequest):
    if not _CONFIGURED:
        return {"result": [], "not_configured": True, "provenance": _provenance(None)}

    query = req.args["query"]
    library = req.args.get("library")
    token = _get_token()

    search_body = {
        "requests": [
            {
                "entityTypes": ["driveItem"],
                "query": {"queryString": f"{query} {'path:' + library if library else ''}".strip()},
            }
        ]
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{GRAPH_BASE}/search/query",
            headers={"Authorization": f"Bearer {token}"},
            json=search_body,
        )
        resp.raise_for_status()
        hits = resp.json()["value"][0]["hitsContainers"][0].get("hits", [])

    results = [
        {
            "item_id": h["resource"]["id"],
            "title": h["resource"]["name"],
            "snippet": h.get("summary"),
            "web_url": h["resource"].get("webUrl"),
        }
        for h in hits
    ]
    return {"result": results, "provenance": _provenance("search")}


@app.post("/tools/get_document/call")
async def get_document(req: ToolCallRequest):
    if not _CONFIGURED:
        return {"result": None, "not_configured": True, "provenance": _provenance(None)}

    item_id = req.args["item_id"]
    token = _get_token()
    async with httpx.AsyncClient(timeout=15.0) as client:
        meta_resp = await client.get(
            f"{GRAPH_BASE}/sites/{SITE_ID}/drive/items/{item_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        meta_resp.raise_for_status()
        meta = meta_resp.json()

        preview_resp = await client.post(
            f"{GRAPH_BASE}/sites/{SITE_ID}/drive/items/{item_id}/preview",
            headers={"Authorization": f"Bearer {token}"},
        )
        preview_url = preview_resp.json().get("getUrl") if preview_resp.status_code == 200 else None

    return {
        "result": {
            "item_id": item_id,
            "title": meta.get("name"),
            "mime_type": meta.get("file", {}).get("mimeType"),
            "view_url": preview_url or meta.get("webUrl"),
        },
        "provenance": _provenance(meta.get("webUrl")),
    }


@app.post("/tools/list_library/call")
async def list_library(req: ToolCallRequest):
    if not _CONFIGURED:
        return {"result": [], "not_configured": True, "provenance": _provenance(None)}

    library = req.args["library"]
    folder = req.args.get("folder", "")
    token = _get_token()
    path = f"root:/{library}/{folder}:/children".rstrip("/:")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{GRAPH_BASE}/sites/{SITE_ID}/drive/{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        items = resp.json().get("value", [])

    return {
        "result": [{"name": i["name"], "id": i["id"], "is_folder": "folder" in i} for i in items],
        "provenance": _provenance(f"{library}/{folder}"),
    }
