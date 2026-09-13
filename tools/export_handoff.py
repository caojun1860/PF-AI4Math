"""Export a secret-free, model-agnostic snapshot of the current AI4Math project."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / ".handoff"
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".runtime",
    ".handoff",
    ".lake",
    "__pycache__",
    "node_modules",
    "sources",
    "parsed",
    "build",
    "deliverables",
}
EXCLUDED_NAMES = {".env", ".DS_Store", "mcp-auth.json"}
EXCLUDED_ENDINGS = (
    ".pdf",
    ".zip",
    ".sqlite3",
    ".sqlite3-wal",
    ".sqlite3-shm",
    ".db",
    ".log",
    ".aux",
    ".synctex.gz",
)
TEXT_ENDINGS = {
    ".md",
    ".txt",
    ".tex",
    ".bib",
    ".yaml",
    ".yml",
    ".json",
    ".jsonl",
    ".py",
    ".lean",
    ".toml",
    ".command",
}
SECRET_PATTERNS = {
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    "API key": re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{16,}\b"),
    "bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def included_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.name.endswith(EXCLUDED_ENDINGS):
            continue
        if path.suffix.lower() not in TEXT_ENDINGS and path.name not in {"LICENSE"}:
            continue
        result.append(path)
    return sorted(result, key=lambda item: str(item.relative_to(ROOT)))


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = OUTPUT_ROOT / f"ai4math-handoff-{timestamp}"
    project = target / "project"
    project.mkdir(parents=True, exist_ok=False)

    sources = included_files()
    unsafe: list[str] = []
    for source in sources:
        try:
            content = source.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                unsafe.append(f"{source.relative_to(ROOT)}: {label}")
    if unsafe:
        raise RuntimeError("交接包包含疑似凭据，已停止导出：\n" + "\n".join(unsafe))

    entries = []
    for source in sources:
        relative = source.relative_to(ROOT)
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        entries.append(
            {
                "path": str(relative),
                "bytes": source.stat().st_size,
                "sha256": sha256(source),
            }
        )

    active = ""
    active_file = ROOT / ".runtime" / "active-paper.json"
    if active_file.exists():
        try:
            active = str(json.loads(active_file.read_text(encoding="utf-8")).get("slug", ""))
        except (OSError, ValueError, TypeError):
            active = ""

    manifest = {
        "format": "ai4math-model-handoff-v1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": git_value("rev-parse", "HEAD"),
        "git_branch": git_value("branch", "--show-current"),
        "active_paper": active,
        "file_count": len(entries),
        "files": entries,
        "excluded": [
            "credentials and .env",
            "OAuth state and local runtime databases",
            "original PDFs and source attachments",
            "parsed/build/deliverable caches",
        ],
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (target / "START-HERE.md").write_text(
        "# AI4Math 接管包\n\n"
        "将 `project/` 作为新模型的工作目录。依次读取 "
        "`AGENTS.md`、`MODEL-HANDOFF.md`、`state/current.md`、`tasks/`、"
        "`papers/` 和 `reports/`。先核对现状，再继续未完成节点。\n\n"
        f"Git commit: `{manifest['git_head']}`  \n"
        f"Active paper: `{active or '未记录'}`  \n"
        f"Files: {len(entries)}\n",
        encoding="utf-8",
    )

    archive_path = target.with_suffix(".zip")
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(target.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(target.parent))

    print(json.dumps({
        "folder": str(target),
        "zip": str(archive_path),
        "files": len(entries),
        "sha256": sha256(archive_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
