"""Verify local MCP connectivity and the OpenCode agent permission matrix.

This script does not call any language model. Zotero data stays on the machine.
"""

from __future__ import annotations

import argparse
import asyncio
import gc
import json
import os
from pathlib import Path
from typing import Any

import yaml
from mcp import Client, StdioServerParameters


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "opencode.json"
AGENTS = ROOT / ".opencode" / "agents"
EXPECTED_AGENTS = {
    "research-orchestrator": "primary",
    "math-deriver": "all",
    "symbolic-checker": "all",
    "literature-reader": "all",
    "scholarly-searcher": "all",
    "paper-reader": "all",
    "literature-synthesizer": "all",
    "citation-auditor": "all",
    "manuscript-reviewer": "all",
    "research-writer": "all",
    "lean-verifier": "all",
    "proof-reviewer": "all",
}


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise RuntimeError(f"{path.name}: missing YAML frontmatter")
    _, header, _ = text.split("---", 2)
    return yaml.safe_load(header)


def check_agents() -> None:
    for name, mode in EXPECTED_AGENTS.items():
        data = _frontmatter(AGENTS / f"{name}.md")
        if data.get("mode") != mode:
            raise RuntimeError(f"{name}: expected mode {mode}")
        if not str(data.get("model", "")).startswith("ai4math-gateway/"):
            raise RuntimeError(f"{name}: model bypasses the budget gateway")
        if name != "research-orchestrator" and data.get("permission", {}).get("edit") != "deny":
            raise RuntimeError(f"{name}: professional agent must not edit files")

    literature = _frontmatter(AGENTS / "literature-reader.md")["permission"]
    lean = _frontmatter(AGENTS / "lean-verifier.md")["permission"]
    if (
        literature.get("zotero_local_*") != "ask"
        or literature.get("zotero_local_zotero_get_citation_metadata") != "allow"
        or literature.get("lean_lsp_*") != "deny"
    ):
        raise RuntimeError("literature-reader MCP permissions are incorrect")
    if lean.get("lean_lsp_*") != "allow" or lean.get("zotero_local_*") != "deny":
        raise RuntimeError("lean-verifier MCP permissions are incorrect")
    expected_skills = {
        "sympy",
        "lean4",
        "literature-review",
        "citation-management",
        "peer-review",
        "scientific-critical-thinking",
        "scientific-writing",
        "academic-paper-review",
        "liteparse",
        "markitdown",
        "paper-search",
        "opencode-ensemble",
    }
    missing_skills = {
        name for name in expected_skills if not (ROOT / ".opencode" / "skills" / name / "SKILL.md").is_file()
    }
    if missing_skills:
        raise RuntimeError(f"missing project skills: {sorted(missing_skills)}")
    print(f"Agent 权限：{len(EXPECTED_AGENTS)} 个角色配置通过")
    print(f"项目 Skills：{len(expected_skills)} 个入口文件通过")

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if config.get("plugin") != ["@hueyexe/opencode-ensemble@0.16.0"]:
        raise RuntimeError("OpenCode Ensemble 未固定到已审查版本")
    ensemble = json.loads((ROOT / ".opencode" / "ensemble.json").read_text(encoding="utf-8"))
    if ensemble.get("dashboardPort") != 4747 or ensemble.get("mergeOnCleanup") is not False:
        raise RuntimeError("Ensemble 面板或安全合并策略配置错误")
    print("并行编排：Ensemble 0.16.0，自动合并已关闭")


def _server_parameters(name: str) -> StdioServerParameters:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))["mcp"][name]
    command = data["command"]
    env = dict(os.environ)
    env.update(data.get("environment", {}))
    return StdioServerParameters(
        command=command[0],
        args=command[1:],
        cwd=data.get("cwd"),
        env=env,
    )


async def check_zotero() -> None:
    async with Client(_server_parameters("zotero_local"), read_timeout_seconds=30) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        expected = {
            "zotero_status",
            "zotero_search",
            "zotero_get_item",
            "zotero_get_citation_metadata",
            "zotero_list_children",
            "zotero_get_indexed_fulltext",
            "zotero_list_collections",
        }
        if tools != expected:
            raise RuntimeError(f"unexpected Zotero tool set: {sorted(tools)}")
        result = await client.call_tool("zotero_status", {})
        if result.is_error or not result.structured_content.get("available"):
            raise RuntimeError("Zotero status check failed")
        print("Zotero MCP：已连接，7 个只读工具")


async def check_lean(run_build: bool) -> None:
    async with Client(_server_parameters("lean_lsp"), read_timeout_seconds=150) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        disabled = {
            "lean_leansearch",
            "lean_loogle",
            "lean_leanfinder",
            "lean_state_search",
            "lean_hammer_premise",
            "lean_run_code",
            "lean_profile_proof",
            "lean_get_widgets",
            "lean_get_widget_source",
        }
        if tools & disabled:
            raise RuntimeError(f"disabled Lean tools are still visible: {sorted(tools & disabled)}")
        required = {"lean_build", "lean_goal", "lean_diagnostic_messages", "lean_verify"}
        if not required <= tools:
            raise RuntimeError(f"required Lean tools are missing: {sorted(required - tools)}")
        print(f"Lean MCP：已连接，{len(tools)} 个受限工具；9 个高权限或联网工具已关闭")
        if run_build:
            result = await client.call_tool(
                "lean_build",
                {
                    "lean_project_path": str(ROOT / "formal"),
                    "clean": False,
                    "fetch_cache": False,
                    "output_lines": 5,
                },
            )
            if result.is_error or not result.structured_content.get("success"):
                raise RuntimeError("Lean MCP build failed")
            print("Lean MCP 构建：通过")


async def check_literature_search() -> None:
    async with Client(_server_parameters("literature_search"), read_timeout_seconds=30) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        expected = {
            "search_academic",
            "search_openalex",
            "search_semantic_scholar",
            "search_arxiv",
            "lookup_crossref",
        }
        if tools != expected:
            raise RuntimeError(f"unexpected literature search tool set: {sorted(tools)}")
        print("库外文献 MCP：已连接，5 个只读检索工具")


async def check_research_workspace() -> None:
    async with Client(_server_parameters("research_workspace"), read_timeout_seconds=30) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        expected = {
            "pdf_inspect",
            "pdf_extract",
            "pdf_screenshot",
            "paper_project_create",
            "paper_write_text",
            "paper_project_status",
            "paper_build_bundle",
        }
        if tools != expected:
            raise RuntimeError(f"unexpected research workspace tool set: {sorted(tools)}")
        print("PDF/论文 MCP：已连接，7 个本地受限工具")


async def main(run_build: bool) -> None:
    check_agents()
    await check_literature_search()
    await check_research_workspace()
    await check_zotero()
    await check_lean(run_build)
    gc.collect()
    await asyncio.sleep(0.2)
    print("检查完成：未调用语言模型，未产生 token 消耗")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-lean-build", action="store_true", help="only check Lean tool discovery"
    )
    args = parser.parse_args()
    asyncio.run(main(run_build=not args.skip_lean_build))
