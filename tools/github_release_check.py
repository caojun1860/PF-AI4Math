"""Check the committed repository for common privacy and portability problems."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BANNED_ENDINGS = (".pdf", ".sqlite3", ".db", ".log", ".aux", ".synctex.gz")
SECRET_PATTERNS = {
    "private key": re.compile(r"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    "API key": re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{16,}\b"),
    "bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
}
ABSOLUTE_PATH = re.compile(r"/(?:Users|home)/[^/\s]+/")


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


def main() -> int:
    tracked_raw = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, stdout=subprocess.PIPE, check=True
    ).stdout
    tracked = [Path(value.decode()) for value in tracked_raw.split(b"\0") if value]
    errors: list[str] = []
    warnings: list[str] = []

    for relative in tracked:
        name = str(relative)
        if relative.name == ".env" or name.endswith(BANNED_ENDINGS):
            errors.append(f"不应提交的文件类型：{name}")
            continue
        path = ROOT / relative
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # 上游 skill 文档含沙箱用户路径一类教学示例；个人路径检查聚焦项目原创文件。
        checks_personal_paths = (
            not name.startswith(".opencode/skills/")
            and name != "tools/github_release_check.py"
        )
        if checks_personal_paths and ABSOLUTE_PATH.search(content):
            errors.append(f"包含个人绝对路径：{name}")
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                errors.append(f"疑似 {label}：{name}")

    remote = git("remote", "get-url", "origin")
    if remote.returncode:
        warnings.append("尚未配置 GitHub origin")
    authors = git("log", "--format=%ae", "--all")
    local_authors = sorted({email for email in authors.stdout.splitlines() if email.endswith(".local")})
    if local_authors:
        warnings.append(
            "Git 历史含本机生成的作者邮箱；公开前建议改成 GitHub noreply 邮箱："
            + ", ".join(local_authors)
        )
    status = git("status", "--short").stdout.splitlines()
    if status:
        warnings.append(f"工作区有 {len(status)} 项未提交变化；git push 只会上传已提交版本")

    print("GitHub 发布检查")
    print(f"- 已跟踪文件：{len(tracked)}")
    for warning in warnings:
        print(f"- 提醒：{warning}")
    for error in errors:
        print(f"- 阻止发布：{error}")
    if errors:
        print("结果：未通过")
        return 1
    print("结果：已提交内容通过凭据、文件类型和绝对路径检查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
