"""Bounded, read-only Zotero Desktop MCP server.

The server only talks to Zotero's loopback Web API and intentionally exposes no
create, update, delete, import, or attachment-file operations.
"""

from __future__ import annotations

import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server import MCPServer


DEFAULT_BASE_URL = "http://127.0.0.1:23119/api/users/0"
ITEM_KEY = re.compile(r"[A-Z0-9]{8}")


class ZoteroReadError(RuntimeError):
    """A concise error safe to return through MCP."""


def _bounded_int(value: int, *, minimum: int, maximum: int, name: str) -> int:
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _validate_item_key(item_key: str) -> str:
    key = item_key.strip().upper()
    if not ITEM_KEY.fullmatch(key):
        raise ValueError("item_key must contain exactly eight letters or digits")
    return key


def _base_url() -> str:
    value = os.environ.get("ZOTERO_LOCAL_API", DEFAULT_BASE_URL).rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ZoteroReadError("ZOTERO_LOCAL_API must use the local HTTP interface")
    if parsed.port != 23119:
        raise ZoteroReadError("ZOTERO_LOCAL_API must use Zotero's local port 23119")
    return value


def _creator_name(creator: dict[str, Any]) -> str:
    if creator.get("name"):
        return str(creator["name"])
    return " ".join(
        str(creator.get(part, "")).strip() for part in ("firstName", "lastName")
    ).strip()


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    data = item.get("data", item)
    creators = [name for value in data.get("creators", []) if (name := _creator_name(value))]
    result = {
        "key": data.get("key"),
        "item_type": data.get("itemType"),
        "title": data.get("title"),
        "creators": creators,
        "date": data.get("date"),
        "doi": data.get("DOI"),
        "url": data.get("url"),
        "publication": data.get("publicationTitle"),
        "parent_item": data.get("parentItem"),
        "content_type": data.get("contentType"),
        "tags": [tag.get("tag") for tag in data.get("tags", []) if tag.get("tag")],
    }
    return {key: value for key, value in result.items() if value not in (None, "", [])}


class ZoteroClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or _base_url()).rstrip("/")

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not path.startswith("/") or ".." in path:
            raise ValueError("invalid Zotero API path")
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"Zotero-API-Version": "3", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                import json

                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise ZoteroReadError(f"Zotero local API returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ZoteroReadError(
                "Cannot reach Zotero. Open Zotero and enable its local API."
            ) from exc


def _client() -> ZoteroClient:
    return ZoteroClient()


mcp = MCPServer(
    "AI4Math Zotero Reader",
    instructions=(
        "Read-only access to the local Zotero library. Search before fetching an item. "
        "Keep evidence tied to item keys and DOI/URL. Indexed full text has no reliable "
        "page boundaries, so do not invent page numbers. No tool may modify the library."
    ),
    log_level="ERROR",
)


@mcp.tool()
def zotero_status() -> dict[str, Any]:
    """Check whether the local Zotero read API is available."""
    result = _client().get("/items/top", {"limit": 1, "format": "json"})
    return {"available": True, "sample_items_returned": len(result)}


@mcp.tool()
def zotero_search(query: str, limit: int = 5) -> dict[str, Any]:
    """Search top-level Zotero items by text; returns at most ten compact records."""
    text = query.strip()
    if not text:
        raise ValueError("query is required")
    if len(text) > 500:
        raise ValueError("query must contain at most 500 characters")
    count = _bounded_int(limit, minimum=1, maximum=10, name="limit")
    items = _client().get(
        "/items/top", {"q": text, "limit": count, "format": "json"}
    )
    return {"query": text, "count": len(items), "items": [compact_item(x) for x in items]}


@mcp.tool()
def zotero_get_item(item_key: str) -> dict[str, Any]:
    """Read compact bibliographic metadata for one Zotero item key."""
    key = _validate_item_key(item_key)
    return compact_item(_client().get(f"/items/{key}"))


@mcp.tool()
def zotero_get_citation_metadata(item_key: str) -> dict[str, Any]:
    """Read only citation identity fields: key, title, creators, date, DOI, URL."""
    key = _validate_item_key(item_key)
    item = compact_item(_client().get(f"/items/{key}"))
    allowed = ("key", "title", "creators", "date", "doi", "url")
    return {field: item[field] for field in allowed if field in item}


@mcp.tool()
def zotero_list_children(item_key: str, limit: int = 10) -> dict[str, Any]:
    """List notes and attachments belonging to a Zotero parent item."""
    key = _validate_item_key(item_key)
    count = _bounded_int(limit, minimum=1, maximum=20, name="limit")
    items = _client().get(
        f"/items/{key}/children", {"limit": count, "format": "json"}
    )
    return {"parent_item": key, "count": len(items), "items": [compact_item(x) for x in items]}


@mcp.tool()
def zotero_get_indexed_fulltext(
    attachment_key: str, max_characters: int = 12000
) -> dict[str, Any]:
    """Read bounded indexed text for an attachment; page numbers are unavailable."""
    key = _validate_item_key(attachment_key)
    maximum = _bounded_int(
        max_characters, minimum=1000, maximum=20000, name="max_characters"
    )
    data = _client().get(f"/items/{key}/fulltext")
    content = str(data.get("content", ""))
    return {
        "attachment_key": key,
        "content": content[:maximum],
        "returned_characters": min(len(content), maximum),
        "total_characters": len(content),
        "truncated": len(content) > maximum,
        "page_number_warning": "Indexed text does not preserve reliable PDF page boundaries.",
    }


@mcp.tool()
def zotero_list_collections(limit: int = 20) -> dict[str, Any]:
    """List a bounded set of Zotero collections without item contents."""
    count = _bounded_int(limit, minimum=1, maximum=50, name="limit")
    collections = _client().get("/collections", {"limit": count, "format": "json"})
    compact = []
    for collection in collections:
        data = collection.get("data", collection)
        compact.append(
            {
                "key": data.get("key"),
                "name": data.get("name"),
                "parent_collection": data.get("parentCollection") or None,
            }
        )
    return {"count": len(compact), "collections": compact}


if __name__ == "__main__":
    mcp.run(transport="stdio")
