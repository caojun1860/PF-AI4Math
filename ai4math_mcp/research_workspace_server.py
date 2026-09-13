"""Scoped local MCP tools for PDFs and per-question paper deliverables."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mcp.server import MCPServer

from tools.paper_manager import build_and_bundle, create_project, status, write_text


ROOT = Path(__file__).resolve().parents[1]
PDF_PYTHON = ROOT / ".runtime" / "pdf-tools" / "bin" / "python"
MARKITDOWN = ROOT / ".runtime" / "pdf-tools" / "bin" / "markitdown"
LIT = ROOT / ".runtime" / "pdf-tools" / "bin" / "lit"
mcp = MCPServer(
    "AI4Math Research Workspace",
    instructions="Local-only PDF parsing and scoped paper-folder writing/building.",
    log_level="ERROR",
)


def _allowed_roots() -> list[Path]:
    home = Path.home()
    values = [
        ROOT,
        home / "Documents",
        home / "Downloads",
        home / "Desktop",
        home / "Zotero" / "storage",
        Path(tempfile.gettempdir()),
        Path("/private/tmp"),
    ]
    return [path.resolve() for path in values if path.exists()]


def _pdf_path(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if path.suffix.lower() != ".pdf" or not path.is_file():
        raise ValueError("只接受现有 PDF 文件")
    if path.stat().st_size > 500 * 1024 * 1024:
        raise ValueError("PDF 不能超过 500 MB")
    if not any(path.is_relative_to(root) for root in _allowed_roots()):
        raise ValueError("PDF 必须位于项目、Documents、Downloads、Desktop、Zotero 或临时附件目录")
    return path


def _image_path(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=True)
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"} or not path.is_file():
        raise ValueError("只接受现有 PNG/JPG/WebP/GIF 图片")
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("图片不能超过 10 MB")
    if not any(path.is_relative_to(root) for root in _allowed_roots()):
        raise ValueError("图片必须位于项目、Documents、Downloads、Desktop、Zotero 或临时附件目录")
    return path


def _slug(value: str) -> str:
    from tools.paper_manager import safe_slug

    return safe_slug(value)


def _pages(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    if len(value) > 100 or not re.fullmatch(r"[0-9,\- ]+", value):
        raise ValueError("pages 仅支持页码和范围，例如 1,3-5")
    return value.replace(" ", "")


def _run(command: list[str], *, timeout: int = 300) -> str:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-4000:])
    return result.stdout


@mcp.tool()
def pdf_inspect(path: str) -> dict[str, Any]:
    """Inspect a local PDF without sending it to a cloud service."""
    source = _pdf_path(path)
    code = (
        "import json,pdfplumber,sys; "
        "p=pdfplumber.open(sys.argv[1]); "
        "print(json.dumps({'pages':len(p.pages),'metadata':p.metadata or {}},ensure_ascii=False)); p.close()"
    )
    data = json.loads(_run([str(PDF_PYTHON), "-c", code, str(source)], timeout=60))
    return {"path": str(source), "bytes": source.stat().st_size, **data}


@mcp.tool()
def pdf_extract(
    path: str,
    problem_slug: str,
    engine: str = "auto",
    pages: str | None = None,
    max_characters: int = 120000,
) -> dict[str, Any]:
    """Extract PDF text locally; use LiteParse OCR when needed and save the result in the paper folder."""
    source = _pdf_path(path)
    slug = _slug(problem_slug)
    page_spec = _pages(pages)
    maximum = int(max_characters)
    if not 1000 <= maximum <= 180000:
        raise ValueError("max_characters 必须在 1,000 到 180,000 之间")
    if engine not in {"auto", "markitdown", "liteparse"}:
        raise ValueError("engine 必须是 auto、markitdown 或 liteparse")
    output_dir = ROOT / "papers" / slug / "parsed"
    output_dir.mkdir(parents=True, exist_ok=True)

    used = engine
    output = output_dir / f"{source.stem}.{engine}.md"
    if engine in {"auto", "markitdown"} and page_spec is None:
        output = output_dir / f"{source.stem}.markitdown.md"
        _run([str(MARKITDOWN), str(source), "-o", str(output)])
        text = output.read_text(encoding="utf-8", errors="replace")
        used = "markitdown"
        if engine == "auto" and len(text.strip()) < 500:
            used = "liteparse"
    else:
        text = ""
        used = "liteparse" if engine == "auto" else engine

    if used == "liteparse":
        output = output_dir / f"{source.stem}.liteparse.md"
        command = [str(LIT), "parse", str(source), "--format", "text", "--max-pages", "300", "-o", str(output)]
        if page_spec:
            command.extend(["--target-pages", page_spec])
        _run(command)
        text = output.read_text(encoding="utf-8", errors="replace")

    return {
        "source": str(source),
        "engine": used,
        "pages": page_spec or "all",
        "saved_to": str(output),
        "total_characters": len(text),
        "content": text[:maximum],
        "truncated": len(text) > maximum,
        "privacy": "local-only",
    }


@mcp.tool()
def pdf_screenshot(path: str, problem_slug: str, pages: str, dpi: int = 160) -> dict[str, Any]:
    """Render selected PDF pages locally for checking equations, figures, and page layout."""
    source = _pdf_path(path)
    slug, page_spec = _slug(problem_slug), _pages(pages)
    value = int(dpi)
    if not 100 <= value <= 240:
        raise ValueError("dpi 必须在 100 到 240 之间")
    output = ROOT / "papers" / slug / "figures" / "pdf-pages" / source.stem
    output.mkdir(parents=True, exist_ok=True)
    _run([str(LIT), "screenshot", str(source), "-o", str(output), "--target-pages", page_spec or "1", "--dpi", str(value)])
    files = sorted(str(path) for path in output.iterdir() if path.is_file())
    return {"source": str(source), "pages": page_spec, "files": files, "privacy": "local-only"}


@mcp.tool()
def paper_project_create(question: str, title: str, problem_slug: str) -> dict[str, Any]:
    """Create or resume the default paper folder for one research question."""
    return create_project(question, title, problem_slug)


@mcp.tool()
def paper_write_text(problem_slug: str, relative_path: str, content: str) -> dict[str, Any]:
    """Write a scoped LaTeX, BibTeX, README, or evidence text file inside one paper folder."""
    return write_text(problem_slug, relative_path, content)


@mcp.tool()
def paper_project_status(problem_slug: str) -> dict[str, Any]:
    """Show source sections and downloadable outputs for one paper folder."""
    return status(problem_slug)


@mcp.tool()
def paper_build_bundle(problem_slug: str) -> dict[str, Any]:
    """Compile XeLaTeX/Biber and create PDF, TeX, source ZIP, and checksum manifest."""
    env = os.environ.copy()
    env["PATH"] = "/Library/TeX/texbin:/usr/bin:/bin:/usr/sbin:/sbin:" + env.get("PATH", "")
    return build_and_bundle(problem_slug)


@mcp.tool()
def url_fetch(url: str, problem_slug: str, max_characters: int = 120000) -> dict[str, Any]:
    """Fetch a public web page and convert it to Markdown locally; result saved in the paper folder."""
    import httpx
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("只接受 http/https URL")
    slug = _slug(problem_slug)
    maximum = int(max_characters)
    if not 1000 <= maximum <= 180000:
        raise ValueError("max_characters 必须在 1,000 到 180,000 之间")
    output_dir = ROOT / "papers" / slug / "parsed"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", parsed.netloc + parsed.path)[:120].strip("_") or "page"
    html_path = output_dir / f"{safe_name}.html"
    md_path = output_dir / f"{safe_name}.md"
    headers = {"User-Agent": "AI4Math-Workflow/1.0 (+local research tool)"}
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        if len(resp.content) > 20 * 1024 * 1024:
            raise ValueError("页面超过 20 MB，拒绝抓取")
        html_path.write_bytes(resp.content)
    _run([str(MARKITDOWN), str(html_path), "-o", str(md_path)], timeout=120)
    text = md_path.read_text(encoding="utf-8", errors="replace")
    html_path.unlink(missing_ok=True)
    return {
        "url": url,
        "saved_to": str(md_path),
        "total_characters": len(text),
        "content": text[:maximum],
        "truncated": len(text) > maximum,
        "privacy": "fetched from public web, stored locally",
    }


@mcp.tool()
def image_describe(path: str, problem_slug: str, prompt: str | None = None) -> dict[str, Any]:
    """Send a local image to the vision-capable model via the budget gateway and return a structured description."""
    import base64
    import httpx

    source = _image_path(path)
    slug = _slug(problem_slug)
    encoded = base64.b64encode(source.read_bytes()).decode("ascii")
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }[source.suffix.lower()]
    user_prompt = (
        prompt
        or "请详细描述这张图片的内容：如果是数学公式，用 LaTeX 转写；如果是图表，说明数据和趋势；如果是截图，提取关键文字。"
    )
    payload = {
        "model": "vision",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                ],
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.1,
    }
    with httpx.Client(timeout=180) as client:
        resp = client.post("http://127.0.0.1:4001/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
    description = data["choices"][0]["message"]["content"]
    output_dir = ROOT / "papers" / slug / "evidence" / "image-descriptions"
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{source.stem}.md"
    out.write_text(
        f"# 图片描述：{source.name}\n\n来源：{source}\n\n{description}\n",
        encoding="utf-8",
    )
    return {
        "source": str(source),
        "saved_to": str(out),
        "description": description,
        "model": "vision (via budget gateway)",
        "privacy": "image sent to configured vision model via local gateway",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
