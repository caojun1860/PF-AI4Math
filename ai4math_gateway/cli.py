from __future__ import annotations

import argparse
import json
from decimal import Decimal

from .budget import BudgetLedger
from .config import cny_to_nano, load_config


def _print_status(ledger: BudgetLedger, budget_id: str) -> None:
    status = ledger.status(budget_id)
    print(f"预算：{budget_id}")
    print(
        f"Token：{status['used_tokens']} 已用 + {status['reserved_tokens']} 进行中 "
        f"/ {status['token_limit']} 上限"
    )
    print(
        f"金额估算：¥{status['used_cny']:.6f} 已用 + ¥{status['reserved_cny']:.6f} 进行中 "
        f"/ ¥{status['cny_limit']:.2f} 上限"
    )
    print(
        f"请求：{status['used_requests']} 已完成 + {status['reserved_requests']} 进行中 "
        f"/ {status['request_limit']} 上限"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="查看或调整 AI4Math 本地预算")
    parser.add_argument("--config", default=None, help="gateway.yaml 路径")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="查看当前预算")
    preflight_parser = subparsers.add_parser("preflight", help="检查启动安全余量")
    preflight_parser.add_argument("--min-tokens", type=int, default=8_000)
    preflight_parser.add_argument("--min-cny", type=Decimal, default=Decimal("0.05"))
    preflight_parser.add_argument("--min-requests", type=int, default=2)
    recent_parser = subparsers.add_parser("recent", help="查看最近请求元数据")
    recent_parser.add_argument("--limit", type=int, default=20)
    set_parser = subparsers.add_parser("set", help="调整预算上限")
    set_parser.add_argument("--tokens", type=int, required=True)
    set_parser.add_argument("--cny", type=Decimal, required=True)
    set_parser.add_argument("--requests", type=int, required=True)
    reset_parser = subparsers.add_parser("reset", help="清零用量与请求记录")
    reset_parser.add_argument("--confirm", required=True, help="必须输入 RESET")
    args = parser.parse_args()

    config = load_config(args.config)
    ledger = BudgetLedger(config.database_path)
    ledger.configure_budget(config.budget)
    budget_id = config.budget.budget_id

    if args.command == "status":
        _print_status(ledger, budget_id)
    elif args.command == "preflight":
        _print_status(ledger, budget_id)
        available = ledger.available(budget_id)
        print(
            f"可用：{available['tokens']} token，¥{available['cny']:.6f}，"
            f"{available['requests']} 次请求"
        )
        enough = (
            available["tokens"] >= args.min_tokens
            and available["cny"] >= float(args.min_cny)
            and available["requests"] >= args.min_requests
        )
        if not enough:
            print("低于启动安全线，研究面板未启动。可先调整预算或继续使用本地检查。")
            raise SystemExit(2)
        print("启动安全线检查通过。")
    elif args.command == "recent":
        print(json.dumps(ledger.recent(budget_id, args.limit), ensure_ascii=False, indent=2))
    elif args.command == "set":
        if args.tokens <= 0 or args.cny <= 0 or args.requests <= 0:
            parser.error("三个上限都必须大于 0")
        ledger.update_limits(
            budget_id,
            total_tokens=args.tokens,
            total_cny_nano=cny_to_nano(args.cny),
            total_requests=args.requests,
        )
        _print_status(ledger, budget_id)
        print("额度已写入本地账本，网关重启后仍然有效。")
    elif args.command == "reset":
        if args.confirm != "RESET":
            parser.error("清零需要 --confirm RESET")
        ledger.reset(budget_id)
        _print_status(ledger, budget_id)


if __name__ == "__main__":
    main()
