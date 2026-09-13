"""Small, read-only MCP façade over the pinned paper-search-mcp package."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from mcp.server import MCPServer
from paper_search_mcp.academic_platforms.arxiv import ArxivSearcher
from paper_search_mcp.academic_platforms.crossref import CrossRefSearcher
from paper_search_mcp.academic_platforms.openalex import OpenAlexSearcher
from paper_search_mcp.academic_platforms.semantic import SemanticSearcher


mcp = MCPServer(
    "AI4Math Literature Search",
    instructions="Read-only academic discovery through OpenAlex, Semantic Scholar, arXiv, and Crossref.",
    log_level="ERROR",
)
_OPENALEX = OpenAlexSearcher()
_SEMANTIC = SemanticSearcher()
_CROSSREF = CrossRefSearcher()
_ARXIV = ArxivSearcher()


def _query(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("query is required")
    if len(value) > 500:
        raise ValueError("query must contain at most 500 characters")
    return value


def _limit(value: int) -> int:
    value = int(value)
    if not 1 <= value <= 20:
        raise ValueError("max_results must be between 1 and 20")
    return value


def _compact(paper: Any, source: str) -> dict[str, Any]:
    raw = paper.to_dict()
    allowed = {
        "paper_id",
        "title",
        "authors",
        "abstract",
        "doi",
        "published_date",
        "pdf_url",
        "url",
        "journal",
        "citation_count",
    }
    result = {key: raw.get(key) for key in allowed if raw.get(key) not in (None, "", [])}
    result["source"] = source
    return result


async def _run(source: str, function: Callable[[], list[Any]]) -> dict[str, Any]:
    try:
        papers = await asyncio.wait_for(asyncio.to_thread(function), timeout=25)
        return {"source": source, "count": len(papers), "papers": [_compact(p, source) for p in papers]}
    except Exception as exc:
        return {"source": source, "count": 0, "papers": [], "error": str(exc)[:500]}


@mcp.tool()
async def search_openalex(query: str, max_results: int = 8) -> dict[str, Any]:
    """Search OpenAlex metadata. Read-only; returns at most 20 compact records."""
    text, count = _query(query), _limit(max_results)
    return await _run("openalex", lambda: _OPENALEX.search(text, max_results=count))


@mcp.tool()
async def search_semantic_scholar(
    query: str, max_results: int = 8, year: str | None = None
) -> dict[str, Any]:
    """Search Semantic Scholar metadata and citation signals."""
    text, count = _query(query), _limit(max_results)
    return await _run(
        "semantic_scholar",
        lambda: _SEMANTIC.search(text, year=year, max_results=count),
    )


@mcp.tool()
async def search_arxiv(query: str, max_results: int = 8) -> dict[str, Any]:
    """Search the official arXiv feed for recent or canonical preprints."""
    text, count = _query(query), _limit(max_results)
    return await _run("arxiv", lambda: _ARXIV.search(text, max_results=count))


@mcp.tool()
async def lookup_crossref(query: str, max_results: int = 8) -> dict[str, Any]:
    """Resolve DOI and canonical bibliographic metadata with Crossref."""
    text, count = _query(query), _limit(max_results)
    return await _run("crossref", lambda: _CROSSREF.search(text, max_results=count))


@mcp.tool()
async def search_academic(
    query: str, max_results_per_source: int = 6, year: str | None = None
) -> dict[str, Any]:
    """Search OpenAlex, Semantic Scholar, arXiv, and Crossref concurrently and deduplicate."""
    text, count = _query(query), _limit(max_results_per_source)
    results = await asyncio.gather(
        _run("openalex", lambda: _OPENALEX.search(text, max_results=count)),
        _run("semantic_scholar", lambda: _SEMANTIC.search(text, year=year, max_results=count)),
        _run("arxiv", lambda: _ARXIV.search(text, max_results=count)),
        _run("crossref", lambda: _CROSSREF.search(text, max_results=count)),
    )
    seen: set[str] = set()
    papers: list[dict[str, Any]] = []
    for result in results:
        for paper in result["papers"]:
            key = (paper.get("doi") or paper.get("paper_id") or paper.get("title") or "").lower()
            if key and key not in seen:
                seen.add(key)
                papers.append(paper)
    return {
        "query": text,
        "sources": {result["source"]: result["count"] for result in results},
        "errors": {result["source"]: result["error"] for result in results if result.get("error")},
        "count": len(papers),
        "papers": papers,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
