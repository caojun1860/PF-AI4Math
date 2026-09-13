from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
from typing import Any

import yaml


NANOCNY_PER_CNY = 1_000_000_000
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "gateway.yaml"


def _positive_int(value: Any, field: str) -> int:
    result = int(value)
    if result <= 0:
        raise ValueError(f"{field} 必须为正整数")
    return result


def _positive_float(value: Any, field: str) -> float:
    result = float(value)
    if result <= 0:
        raise ValueError(f"{field} 必须为正数")
    return result


def cny_to_nano(value: Any) -> int:
    amount = Decimal(str(value)) * NANOCNY_PER_CNY
    result = int(amount.to_integral_value(rounding=ROUND_CEILING))
    if result <= 0:
        raise ValueError("金额预算必须大于 0")
    return result


def per_million_to_nano_per_token(value: Any) -> int:
    amount = Decimal(str(value)) * NANOCNY_PER_CNY / 1_000_000
    result = int(amount.to_integral_value(rounding=ROUND_CEILING))
    if result < 0:
        raise ValueError("模型单价不能为负数")
    return result


@dataclass(frozen=True)
class BudgetConfig:
    budget_id: str
    total_tokens: int
    total_cny_nano: int
    total_requests: int
    allowed_provider_prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelRoute:
    alias: str
    provider_model: str
    api_base: str
    api_key_env: str
    keychain_service: str | None
    max_context_tokens: int
    max_output_tokens: int
    default_output_tokens: int
    input_nano_per_token: int
    output_nano_per_token: int
    timeout_seconds: int


@dataclass(frozen=True)
class GatewayConfig:
    source_path: Path
    host: str
    port: int
    auth_token: str
    database_path: Path
    max_concurrent_requests: int
    min_start_interval_seconds: float
    retry_attempts: int
    retry_base_seconds: float
    sse_keepalive_seconds: float
    budget: BudgetConfig
    models: dict[str, ModelRoute]


def load_config(path: str | Path | None = None) -> GatewayConfig:
    source = Path(path or os.environ.get("AI4MATH_GATEWAY_CONFIG", DEFAULT_CONFIG_PATH)).expanduser().resolve()
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("网关配置必须是 YAML 对象")

    server = raw.get("server", {})
    budget_raw = raw.get("budget", {})
    models_raw = raw.get("models", {})
    if not isinstance(models_raw, dict) or not models_raw:
        raise ValueError("至少需要配置一个模型别名")

    database_value = str(server.get("database", ".runtime/gateway/budget.sqlite3"))
    database_path = Path(database_value).expanduser()
    if not database_path.is_absolute():
        database_path = (source.parents[1] / database_path).resolve()

    allowed_prefixes_raw = budget_raw.get("allowed_provider_prefixes", [])
    if not isinstance(allowed_prefixes_raw, list):
        raise ValueError("budget.allowed_provider_prefixes 必须是列表")
    allowed_prefixes = tuple(str(value) for value in allowed_prefixes_raw if str(value))

    budget = BudgetConfig(
        budget_id=str(budget_raw.get("id", "default")),
        total_tokens=_positive_int(budget_raw.get("total_tokens", 50_000), "budget.total_tokens"),
        total_cny_nano=cny_to_nano(budget_raw.get("total_cny", "1.00")),
        total_requests=_positive_int(budget_raw.get("total_requests", 50), "budget.total_requests"),
        allowed_provider_prefixes=allowed_prefixes,
    )

    models: dict[str, ModelRoute] = {}
    for alias, item in models_raw.items():
        if not isinstance(item, dict):
            raise ValueError(f"models.{alias} 必须是对象")
        max_output = _positive_int(item.get("max_output_tokens", 2048), f"models.{alias}.max_output_tokens")
        default_output = _positive_int(
            item.get("default_output_tokens", min(1024, max_output)),
            f"models.{alias}.default_output_tokens",
        )
        if default_output > max_output:
            raise ValueError(f"models.{alias}.default_output_tokens 不能超过 max_output_tokens")
        context = _positive_int(item.get("max_context_tokens", 16_384), f"models.{alias}.max_context_tokens")
        if max_output >= context:
            raise ValueError(f"models.{alias}.max_output_tokens 必须小于上下文上限")
        models[str(alias)] = ModelRoute(
            alias=str(alias),
            provider_model=str(item["provider_model"]),
            api_base=str(item["api_base"]).rstrip("/"),
            api_key_env=str(item.get("api_key_env", "ARK_API_KEY")),
            keychain_service=(str(item["keychain_service"]) if item.get("keychain_service") else None),
            max_context_tokens=context,
            max_output_tokens=max_output,
            default_output_tokens=default_output,
            input_nano_per_token=per_million_to_nano_per_token(item.get("input_cny_per_million", "0")),
            output_nano_per_token=per_million_to_nano_per_token(item.get("output_cny_per_million", "0")),
            timeout_seconds=_positive_int(item.get("timeout_seconds", 120), f"models.{alias}.timeout_seconds"),
        )

    if budget.allowed_provider_prefixes:
        disallowed = [
            route.alias
            for route in models.values()
            if not route.provider_model.startswith(budget.allowed_provider_prefixes)
        ]
        if disallowed:
            names = ", ".join(sorted(disallowed))
            raise ValueError(f"高额度预算不允许这些模型路由：{names}")

    auth_token = str(server.get("auth_token", ""))
    if not auth_token:
        raise ValueError("server.auth_token 不能为空")

    return GatewayConfig(
        source_path=source,
        host=str(server.get("host", "127.0.0.1")),
        port=int(server.get("port", 4001)),
        auth_token=auth_token,
        database_path=database_path,
        max_concurrent_requests=_positive_int(
            server.get("max_concurrent_requests", 2), "server.max_concurrent_requests"
        ),
        min_start_interval_seconds=_positive_float(
            server.get("min_start_interval_seconds", 4), "server.min_start_interval_seconds"
        ),
        retry_attempts=_positive_int(server.get("retry_attempts", 4), "server.retry_attempts"),
        retry_base_seconds=_positive_float(
            server.get("retry_base_seconds", 5), "server.retry_base_seconds"
        ),
        sse_keepalive_seconds=_positive_float(
            server.get("sse_keepalive_seconds", 15), "server.sse_keepalive_seconds"
        ),
        budget=budget,
        models=models,
    )
