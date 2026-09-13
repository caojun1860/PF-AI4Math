"""Create, build, and package one self-contained paper folder per research question."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
PAPERS = ROOT / "papers"
ACTIVE = ROOT / ".runtime" / "active-paper.json"
TEXT_TARGETS = (
    re.compile(r"^main\.tex$"),
    re.compile(r"^references\.bib$"),
    re.compile(r"^README\.md$"),
    re.compile(r"^sections/[A-Za-z0-9_.\-]+\.tex$"),
    re.compile(r"^evidence/[A-Za-z0-9_.\-]+\.(?:jsonl|json|md|yaml)$"),
)


def safe_slug(value: str) -> str:
    value = value.strip().replace(" ", "-")
    value = re.sub(r"[^\w\-.\u3400-\u9fff]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-+", "-", value).strip("-._")
    if not value or value in {".", ".."}:
        raise ValueError("论文文件夹短名不能为空")
    return value[:80]


def paper_dir(slug: str, *, root: Path = ROOT) -> Path:
    return root / "papers" / safe_slug(slug)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _template(title: str) -> str:
    escaped = title.replace("\\", r"\textbackslash{}").replace("{", r"\{").replace("}", r"\}")
    return rf"""\documentclass[11pt]{{ctexart}}
\usepackage[a4paper,margin=2.5cm]{{geometry}}
\usepackage{{amsmath,amssymb,amsthm,mathtools}}
\usepackage{{graphicx,booktabs,hyperref}}
\usepackage[backend=biber,style=alphabetic]{{biblatex}}
\addbibresource{{references.bib}}

\newtheorem{{theorem}}{{定理}}[section]
\newtheorem{{lemma}}[theorem]{{引理}}
\newtheorem{{proposition}}[theorem]{{命题}}
\theoremstyle{{definition}}
\newtheorem{{definition}}[theorem]{{定义}}

\title{{{escaped}}}
\author{{}}
\date{{\today}}

\begin{{document}}
\maketitle
\begin{{abstract}}
在此写入摘要。
\end{{abstract}}

\input{{sections/01-introduction}}
\input{{sections/02-results}}
\input{{sections/03-proof}}
\input{{sections/04-discussion}}

\printbibliography
\end{{document}}
"""


def create_project(question: str, title: str, slug: str, *, root: Path = ROOT) -> dict[str, Any]:
    question = question.strip()
    title = title.strip()
    if not question or not title:
        raise ValueError("question 和 title 均不能为空")
    slug = safe_slug(slug)
    target = paper_dir(slug, root=root)
    metadata_path = target / "question.yaml"
    if metadata_path.exists():
        existing = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
        if existing.get("question") != question:
            raise ValueError(f"论文目录 {slug} 已属于另一个研究问题")
    for name in ("sections", "figures", "sources", "parsed", "evidence", "build", "deliverables"):
        (target / name).mkdir(parents=True, exist_ok=True)

    files = {
        "main.tex": _template(title),
        "references.bib": "% 由 Zotero/BibTeX 或引用审计流程填充。\n",
        "sections/01-introduction.tex": "\\section{引言}\n",
        "sections/02-results.tex": "\\section{主要结果}\n",
        "sections/03-proof.tex": "\\section{证明}\n",
        "sections/04-discussion.tex": "\\section{讨论与开放问题}\n",
        "evidence/claims.jsonl": "",
        "evidence/source-map.json": "{}\n",
        "README.md": "# 论文工作区\n\n`deliverables/` 中保存可下载 PDF、LaTeX 和源文件包。\n",
    }
    for relative, content in files.items():
        path = target / relative
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    metadata = {
        "slug": slug,
        "title": title,
        "question": question,
        "created_at": (yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}).get("created_at", _utc_now())
        if metadata_path.exists()
        else _utc_now(),
        "updated_at": _utc_now(),
        "status": "draft",
    }
    metadata_path.write_text(yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False), encoding="utf-8")
    if root == ROOT:
        ACTIVE.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE.write_text(json.dumps({"slug": slug}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"slug": slug, "path": str(target), "main_tex": str(target / "main.tex")}


def active_slug(*, root: Path = ROOT) -> str:
    path = root / ".runtime" / "active-paper.json"
    if not path.exists():
        raise ValueError("尚未创建当前论文项目")
    return safe_slug(json.loads(path.read_text(encoding="utf-8"))["slug"])


def write_text(slug: str, relative_path: str, content: str, *, root: Path = ROOT) -> dict[str, Any]:
    slug = safe_slug(slug)
    relative = relative_path.strip().replace("\\", "/")
    if not any(pattern.fullmatch(relative) for pattern in TEXT_TARGETS):
        raise ValueError("只允许写入 main.tex、references.bib、sections/、evidence/ 和 README.md")
    encoded = content.encode("utf-8")
    if len(encoded) > 2_000_000:
        raise ValueError("单次写入内容不能超过 2 MB")
    target = paper_dir(slug, root=root) / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    return {"path": str(target), "bytes": len(encoded)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_and_bundle(slug: str, *, root: Path = ROOT, run_latex: bool = True) -> dict[str, Any]:
    slug = safe_slug(slug)
    target = paper_dir(slug, root=root)
    if not (target / "main.tex").is_file():
        raise ValueError(f"找不到论文项目：{slug}")
    build = target / "build"
    deliverables = target / "deliverables"
    build.mkdir(exist_ok=True)
    deliverables.mkdir(exist_ok=True)

    if run_latex:
        latexmk = shutil.which("latexmk") or "/Library/TeX/texbin/latexmk"
        result = subprocess.run(
            [latexmk, "-xelatex", "-interaction=nonstopmode", "-halt-on-error", "-outdir=build", "main.tex"],
            cwd=target,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=300,
        )
        (build / "latexmk-output.txt").write_text(result.stdout[-100_000:], encoding="utf-8")
        if result.returncode:
            raise RuntimeError(f"LaTeX 构建失败；日志见 {build / 'latexmk-output.txt'}")
        shutil.copy2(build / "main.pdf", deliverables / f"{slug}.pdf")

    shutil.copy2(target / "main.tex", deliverables / f"{slug}.tex")
    bundle = deliverables / f"{slug}-source.zip"
    included: list[str] = []
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for pattern in ("main.tex", "references.bib", "question.yaml", "README.md", "sections/**/*", "figures/**/*", "evidence/**/*"):
            for path in sorted(target.glob(pattern)):
                if path.is_file():
                    relative = str(path.relative_to(target))
                    archive.write(path, relative)
                    included.append(relative)

    outputs = [path for path in deliverables.iterdir() if path.is_file() and path.name != "manifest.json"]
    manifest = {
        "slug": slug,
        "built_at": _utc_now(),
        "source_files": sorted(set(included)),
        "deliverables": {path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)} for path in outputs},
    }
    (deliverables / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"folder": str(target), "deliverables": sorted(str(path) for path in deliverables.iterdir() if path.is_file())}


def status(slug: str, *, root: Path = ROOT) -> dict[str, Any]:
    target = paper_dir(slug, root=root)
    if not target.exists():
        raise ValueError(f"找不到论文项目：{slug}")
    return {
        "slug": safe_slug(slug),
        "folder": str(target),
        "sections": sorted(path.name for path in (target / "sections").glob("*.tex")),
        "deliverables": sorted(path.name for path in (target / "deliverables").glob("*")),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--question", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--slug", required=True)
    build = sub.add_parser("build")
    build.add_argument("--slug")
    show = sub.add_parser("status")
    show.add_argument("--slug")
    args = parser.parse_args()
    slug = getattr(args, "slug", None)
    if args.command == "create":
        result = create_project(args.question, args.title, args.slug)
    elif args.command == "build":
        result = build_and_bundle(slug or active_slug())
    else:
        result = status(slug or active_slug())
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
