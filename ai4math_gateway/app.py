from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import secrets
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from .budget import BudgetExceeded, BudgetLedger
from .config import GatewayConfig, ModelRoute, NANOCNY_PER_CNY, load_config


CompletionFunction = Callable[..., Awaitable[Any]]


def estimate_input_tokens(body: dict[str, Any]) -> int:
    """按 UTF-8 负载作保守近似，同时避免把每个字节误算成一个 token。"""
    relevant = {
        key: value
        for key, value in body.items()
        if key not in {"model", "stream", "stream_options", "max_tokens", "max_completion_tokens"}
    }
    encoded = json.dumps(relevant, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    messages = body.get("messages")
    message_count = len(messages) if isinstance(messages, list) else 1
    # 中文通常约为每字一个 token、每字三个 UTF-8 字节；英文和 JSON
    # 通常每 token 包含多个字节。按每两个字节一个 token 估算，仍留有
    # 较大余量，但不会让 OpenCode 的工具调用记录被人为放大数倍。
    return max(1, math.ceil(len(encoded) / 2) + 512 + 64 * message_count)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if hasattr(value, "dict"):
        return value.dict(exclude_none=True)
    raise TypeError(f"无法序列化上游响应类型：{type(value).__name__}")


def _usage_from(data: dict[str, Any]) -> tuple[int, int] | None:
    usage = data.get("usage")
    if usage is None:
        return None
    if not isinstance(usage, dict):
        usage = _as_dict(usage)
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    if input_tokens is None or output_tokens is None:
        return None
    return max(0, int(input_tokens)), max(0, int(output_tokens))


def _read_keychain(service: str) -> str | None:
    if sys.platform != "darwin":
        return None
    account = os.environ.get("USER") or os.environ.get("LOGNAME")
    if not account:
        return None
    result = subprocess.run(
        ["security", "find-generic-password", "-a", account, "-s", service, "-w"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def resolve_credentials(config: GatewayConfig) -> dict[str, str]:
    credentials: dict[str, str] = {}
    source_cache: dict[tuple[str, str | None], str | None] = {}
    for alias, route in config.models.items():
        source = (route.api_key_env, route.keychain_service)
        if source not in source_cache:
            key = os.environ.get(route.api_key_env)
            if not key and route.keychain_service:
                key = _read_keychain(route.keychain_service)
            source_cache[source] = key
        key = source_cache[source]
        if key:
            credentials[alias] = key
    return credentials


def _select_route(config: GatewayConfig, requested_model: Any) -> ModelRoute:
    model_id = str(requested_model or "")
    alias = model_id if model_id in config.models else model_id.rsplit("/", 1)[-1]
    route = config.models.get(alias)
    if route is None:
        raise HTTPException(status_code=404, detail={"error": "未知模型别名", "model": model_id})
    return route


def _requested_output(body: dict[str, Any], route: ModelRoute) -> int:
    raw = body.get("max_completion_tokens", body.get("max_tokens", route.default_output_tokens))
    if isinstance(raw, bool):
        raise HTTPException(status_code=400, detail="max_tokens 必须是正整数")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="max_tokens 必须是正整数") from exc
    if value <= 0:
        raise HTTPException(status_code=400, detail="max_tokens 必须是正整数")
    if value > route.max_output_tokens:
        raise HTTPException(
            status_code=400,
            detail={"error": "输出上限超出角色配置", "requested": value, "limit": route.max_output_tokens},
        )
    return value


def _budget_error(exc: BudgetExceeded) -> dict[str, Any]:
    if exc.dimension == "cny_nano":
        return {
            "error": "金额预算不足",
            "used_cny": exc.used / NANOCNY_PER_CNY,
            "reserved_cny": exc.reserved / NANOCNY_PER_CNY,
            "requested_cny": exc.requested / NANOCNY_PER_CNY,
            "limit_cny": exc.limit / NANOCNY_PER_CNY,
        }
    return {
        "error": f"{exc.dimension} 预算不足",
        "used": exc.used,
        "reserved": exc.reserved,
        "requested": exc.requested,
        "limit": exc.limit,
    }


def _is_retryable_upstream_error(exc: BaseException) -> bool:
    """仅重试限流、连接和超时类瞬时故障。"""
    message = f"{type(exc).__name__}: {exc}".lower()
    markers = (
        "request burst",
        "rate limit",
        "ratelimit",
        "too many requests",
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "service unavailable",
        "midstreamfallbackerror",
    )
    return any(marker in message for marker in markers)


def create_app(
    config_path: str | Path | None = None,
    *,
    completion_fn: CompletionFunction | None = None,
    credentials: dict[str, str] | None = None,
) -> FastAPI:
    config = load_config(config_path)
    ledger = BudgetLedger(config.database_path)
    ledger.configure_budget(config.budget)
    recovered_at_startup = ledger.recover_reservations(error_type="GatewayRestart")
    credential_map = credentials if credentials is not None else resolve_credentials(config)
    if completion_fn is None:
        import litellm

        litellm.suppress_debug_info = True
        completion_fn = litellm.acompletion

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        ledger.recover_reservations(error_type="GatewayShutdown")

    app = FastAPI(title="AI4Math Local Gateway", version="0.1.0", lifespan=lifespan)
    app.state.config = config
    app.state.ledger = ledger
    upstream_semaphore = asyncio.Semaphore(config.max_concurrent_requests)
    start_lock = asyncio.Lock()
    last_start_at = 0.0

    async def acquire_upstream_slot() -> None:
        """限制活跃请求数，并让新请求平滑进入豆包而非瞬时齐发。"""
        nonlocal last_start_at
        await upstream_semaphore.acquire()
        try:
            async with start_lock:
                delay = config.min_start_interval_seconds - (time.monotonic() - last_start_at)
                if delay > 0:
                    await asyncio.sleep(delay)
                last_start_at = time.monotonic()
        except BaseException:
            upstream_semaphore.release()
            raise

    @app.exception_handler(HTTPException)
    async def openai_style_http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict):
            details = dict(exc.detail)
            message = str(details.pop("error", "请求失败"))
            error_type = str(details.pop("type", "gateway_error"))
        else:
            message = str(exc.detail)
            error_type = "gateway_error"
            details = {}
        payload: dict[str, Any] = {"message": message, "type": error_type}
        if details:
            payload["details"] = details
        return JSONResponse(status_code=exc.status_code, content={"error": payload})

    def require_auth(authorization: str | None) -> None:
        expected = f"Bearer {config.auth_token}"
        if authorization is None or not secrets.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="本地网关认证失败")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "credential_configured": all(alias in credential_map for alias in config.models),
            "models": list(config.models),
            "budget_id": config.budget.budget_id,
            "traffic": {
                "max_concurrent_requests": config.max_concurrent_requests,
                "min_start_interval_seconds": config.min_start_interval_seconds,
                "retry_attempts": config.retry_attempts,
                "sse_keepalive_seconds": config.sse_keepalive_seconds,
            },
            "recovered_requests_at_startup": recovered_at_startup,
        }

    @app.get("/v1/models")
    async def models(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        require_auth(authorization)
        created = int(time.time())
        return {
            "object": "list",
            "data": [
                {"id": alias, "object": "model", "created": created, "owned_by": "ai4math"}
                for alias in config.models
            ],
        }

    @app.get("/budget/status")
    async def budget_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        require_auth(authorization)
        return {
            "budget": ledger.status(config.budget.budget_id),
            "recent": ledger.recent(config.budget.budget_id, 20),
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(
        request: Request,
        authorization: str | None = Header(default=None),
        x_ai4math_budget: str | None = Header(default=None),
    ):
        require_auth(authorization)
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="请求体必须是 JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
            raise HTTPException(status_code=400, detail="messages 必须是数组")

        route = _select_route(config, body.get("model"))
        api_key = credential_map.get(route.alias)
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="尚未配置豆包网关密钥，请先运行“配置豆包网关密钥.command”",
            )
        max_output = _requested_output(body, route)
        input_estimate = estimate_input_tokens(body)
        if input_estimate + max_output > route.max_context_tokens:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "上下文预算超出角色配置",
                    "estimated_input": input_estimate,
                    "max_output": max_output,
                    "limit": route.max_context_tokens,
                },
            )

        budget_id = x_ai4math_budget or config.budget.budget_id
        request_id = f"req_{uuid.uuid4().hex}"
        try:
            reservation = ledger.reserve(
                request_id=request_id,
                budget_id=budget_id,
                alias=route.alias,
                input_estimate=input_estimate,
                max_output=max_output,
                input_nano_per_token=route.input_nano_per_token,
                output_nano_per_token=route.output_nano_per_token,
            )
        except BudgetExceeded as exc:
            raise HTTPException(status_code=429, detail=_budget_error(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        upstream = dict(body)
        upstream["model"] = route.provider_model
        upstream["max_tokens"] = max_output
        upstream.pop("max_completion_tokens", None)
        upstream["api_base"] = route.api_base
        upstream["api_key"] = api_key
        upstream["timeout"] = route.timeout_seconds

        if bool(body.get("stream", False)):
            upstream["stream"] = True
            upstream["stream_options"] = {"include_usage": True}

            async def event_stream() -> AsyncIterator[str]:
                last_usage: tuple[int, int] | None = None
                emitted_model_data = False
                slot_acquired = False
                try:
                    # 先返回 SSE 响应，再在后台等待配额；心跳避免客户端把排队误判为断线。
                    slot_task = asyncio.create_task(acquire_upstream_slot())
                    while not slot_task.done():
                        await asyncio.wait({slot_task}, timeout=config.sse_keepalive_seconds)
                        if not slot_task.done():
                            yield ": ai4math-queue-keepalive\n\n"
                    await slot_task
                    slot_acquired = True

                    completed = False
                    final_error: BaseException | None = None
                    for attempt in range(config.retry_attempts):
                        if attempt:
                            retry_delay = config.retry_base_seconds * (2 ** (attempt - 1))
                            deadline = time.monotonic() + retry_delay
                            while time.monotonic() < deadline:
                                await asyncio.sleep(
                                    min(config.sse_keepalive_seconds, deadline - time.monotonic())
                                )
                                yield ": ai4math-retry-keepalive\n\n"

                        try:
                            open_task = asyncio.create_task(completion_fn(**upstream))
                            while not open_task.done():
                                await asyncio.wait({open_task}, timeout=config.sse_keepalive_seconds)
                                if not open_task.done():
                                    yield ": ai4math-upstream-keepalive\n\n"
                            stream = await open_task
                            iterator = stream.__aiter__()

                            while True:
                                next_task = asyncio.create_task(iterator.__anext__())
                                while not next_task.done():
                                    await asyncio.wait(
                                        {next_task}, timeout=config.sse_keepalive_seconds
                                    )
                                    if not next_task.done():
                                        yield ": ai4math-model-keepalive\n\n"
                                try:
                                    chunk = await next_task
                                except StopAsyncIteration:
                                    completed = True
                                    break
                                data = _as_dict(chunk)
                                data["model"] = route.alias
                                usage = _usage_from(data)
                                if usage is not None:
                                    last_usage = usage
                                emitted_model_data = True
                                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                            if completed:
                                break
                        except Exception as exc:
                            final_error = exc
                            if emitted_model_data or not _is_retryable_upstream_error(exc):
                                raise
                            if attempt + 1 >= config.retry_attempts:
                                raise

                    if not completed:
                        if final_error is not None:
                            raise final_error
                        raise RuntimeError("上游流未正常结束")

                    if last_usage is None:
                        ledger.settle_reserved(reservation, status="estimated")
                    else:
                        ledger.settle(
                            reservation,
                            actual_input=last_usage[0],
                            actual_output=last_usage[1],
                            input_nano_per_token=route.input_nano_per_token,
                            output_nano_per_token=route.output_nano_per_token,
                        )
                    yield "data: [DONE]\n\n"
                except BaseException as exc:
                    try:
                        ledger.settle_reserved(
                            reservation,
                            status="uncertain",
                            error_type=type(exc).__name__,
                        )
                    except RuntimeError:
                        pass
                    raise
                finally:
                    if slot_acquired:
                        upstream_semaphore.release()

            return StreamingResponse(
                event_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        upstream["stream"] = False
        slot_acquired = False
        try:
            await acquire_upstream_slot()
            slot_acquired = True
            response = None
            final_error: BaseException | None = None
            for attempt in range(config.retry_attempts):
                if attempt:
                    await asyncio.sleep(config.retry_base_seconds * (2 ** (attempt - 1)))
                try:
                    response = await completion_fn(**upstream)
                    break
                except Exception as exc:
                    final_error = exc
                    if not _is_retryable_upstream_error(exc) or attempt + 1 >= config.retry_attempts:
                        raise
            if response is None:
                if final_error is not None:
                    raise final_error
                raise RuntimeError("上游模型没有返回响应")
            data = _as_dict(response)
            usage = _usage_from(data)
            if usage is None:
                ledger.settle_reserved(reservation, status="estimated")
            else:
                ledger.settle(
                    reservation,
                    actual_input=usage[0],
                    actual_output=usage[1],
                    input_nano_per_token=route.input_nano_per_token,
                    output_nano_per_token=route.output_nano_per_token,
                )
            data["model"] = route.alias
            return JSONResponse(data)
        except HTTPException:
            raise
        except Exception as exc:
            try:
                ledger.settle_reserved(reservation, status="uncertain", error_type=type(exc).__name__)
            except RuntimeError:
                pass
            raise HTTPException(
                status_code=502,
                detail={"error": "上游模型调用失败", "type": type(exc).__name__},
            ) from exc
        finally:
            if slot_acquired:
                upstream_semaphore.release()

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 AI4Math 本地预算网关")
    parser.add_argument("--config", default=None, help="gateway.yaml 路径")
    args = parser.parse_args()
    config = load_config(args.config)

    import uvicorn

    uvicorn.run(
        create_app(config.source_path),
        host=config.host,
        port=config.port,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
