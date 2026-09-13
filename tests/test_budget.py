from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ai4math_gateway.budget import BudgetExceeded, BudgetLedger
from ai4math_gateway.config import BudgetConfig


class BudgetLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.ledger = BudgetLedger(Path(self.temporary.name) / "budget.sqlite3")
        self.ledger.configure_budget(
            BudgetConfig(
                budget_id="test",
                total_tokens=1_000,
                total_cny_nano=1_000_000_000,
                total_requests=10,
            )
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_reserve_and_settle_use_actual_usage(self) -> None:
        reservation = self.ledger.reserve(
            request_id="one",
            budget_id="test",
            alias="fast",
            input_estimate=100,
            max_output=50,
            input_nano_per_token=3_000,
            output_nano_per_token=15_000,
        )
        during = self.ledger.status("test")
        self.assertEqual(during["reserved_tokens"], 150)
        self.assertEqual(during["used_tokens"], 0)

        self.ledger.settle(
            reservation,
            actual_input=20,
            actual_output=10,
            input_nano_per_token=3_000,
            output_nano_per_token=15_000,
        )
        after = self.ledger.status("test")
        self.assertEqual(after["reserved_tokens"], 0)
        self.assertEqual(after["used_tokens"], 30)
        self.assertEqual(after["used_requests"], 1)

    def test_release_does_not_consume_budget(self) -> None:
        reservation = self.ledger.reserve(
            request_id="release",
            budget_id="test",
            alias="fast",
            input_estimate=100,
            max_output=50,
            input_nano_per_token=3_000,
            output_nano_per_token=15_000,
        )
        self.ledger.release(reservation, error_type="LocalValidation")
        status = self.ledger.status("test")
        self.assertEqual(status["used_tokens"], 0)
        self.assertEqual(status["reserved_tokens"], 0)
        self.assertEqual(status["used_requests"], 0)

    def test_available_balance_counts_in_flight_reservations(self) -> None:
        self.ledger.reserve(
            request_id="available",
            budget_id="test",
            alias="fast",
            input_estimate=100,
            max_output=50,
            input_nano_per_token=3_000,
            output_nano_per_token=15_000,
        )
        available = self.ledger.available("test")
        self.assertEqual(available["tokens"], 850)
        self.assertEqual(available["requests"], 9)

    def test_concurrent_reservations_cannot_overspend(self) -> None:
        self.ledger.update_limits(
            "test",
            total_tokens=150,
            total_cny_nano=1_000_000_000,
            total_requests=10,
        )

        def reserve(number: int) -> str:
            try:
                self.ledger.reserve(
                    request_id=f"parallel-{number}",
                    budget_id="test",
                    alias="fast",
                    input_estimate=60,
                    max_output=40,
                    input_nano_per_token=0,
                    output_nano_per_token=0,
                )
                return "accepted"
            except BudgetExceeded:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(reserve, (1, 2)))
        self.assertCountEqual(outcomes, ["accepted", "rejected"])
        self.assertEqual(self.ledger.status("test")["reserved_tokens"], 100)

    def test_limits_cannot_drop_below_committed_amount(self) -> None:
        self.ledger.reserve(
            request_id="committed",
            budget_id="test",
            alias="fast",
            input_estimate=100,
            max_output=50,
            input_nano_per_token=0,
            output_nano_per_token=0,
        )
        with self.assertRaises(ValueError):
            self.ledger.update_limits(
                "test",
                total_tokens=149,
                total_cny_nano=1_000_000_000,
                total_requests=10,
            )

    def test_restart_recovers_stranded_reservation_conservatively(self) -> None:
        self.ledger.reserve(
            request_id="stranded",
            budget_id="test",
            alias="fast",
            input_estimate=100,
            max_output=50,
            input_nano_per_token=3_000,
            output_nano_per_token=15_000,
        )
        recovered = self.ledger.recover_reservations(error_type="GatewayRestart")
        self.assertEqual(recovered, 1)
        status = self.ledger.status("test")
        self.assertEqual(status["reserved_tokens"], 0)
        self.assertEqual(status["used_tokens"], 150)
        recent = self.ledger.recent("test", 1)[0]
        self.assertEqual(recent["status"], "uncertain")
        self.assertEqual(recent["error_type"], "GatewayRestart")

    def test_default_configuration_does_not_overwrite_manual_limits(self) -> None:
        self.ledger.update_limits(
            "test",
            total_tokens=2_000,
            total_cny_nano=2_000_000_000,
            total_requests=20,
        )
        self.ledger.configure_budget(
            BudgetConfig(
                budget_id="test",
                total_tokens=1_000,
                total_cny_nano=1_000_000_000,
                total_requests=10,
            )
        )
        status = self.ledger.status("test")
        self.assertEqual(status["token_limit"], 2_000)
        self.assertEqual(status["request_limit"], 20)


if __name__ == "__main__":
    unittest.main()
