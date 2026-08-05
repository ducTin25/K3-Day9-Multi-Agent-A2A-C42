"""Shared Decimal/rounding finance helpers for money fields (Member 3 / TV3).

Every monetary value in this project must be parsed as Decimal and rounded to
2 decimal places with ROUND_HALF_UP only after totals are summed (README muc 4,
docs/team-plan.md muc 4: "Tien dung Decimal, tong xong moi lam tron 2 chu so").
This module is the single source of truth for that rule for the Payment
domain; other agents' refund/total calculations are welcome to reuse it.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable

MONEY_QUANTUM = Decimal("0.01")
PAYMENT_TOLERANCE = Decimal("0.10")


class MoneyError(ValueError):
    """Raised when a monetary value cannot be parsed or is invalid."""


def to_money(value: Any) -> Decimal:
    """Parse ``value`` into a finite, non-negative Decimal rounded to 2dp."""
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MoneyError(f"{value!r} is not a valid monetary value") from exc
    if not parsed.is_finite() or parsed < 0:
        raise MoneyError(f"{value!r} must be finite and non-negative")
    return parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def sum_money(values: Iterable[Any]) -> Decimal:
    """Sum monetary values. Each value is parsed independently, never multiplied
    by a row count/installment count by this function."""
    total = Decimal("0.00")
    for value in values:
        total += to_money(value)
    return total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def reconciliation_delta(payment_total: Any, reference_total: Any) -> Decimal:
    """Absolute difference between a payment total and a reference (item+freight) total."""
    return abs(to_money(payment_total) - to_money(reference_total)).quantize(
        MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )


def is_within_tolerance(
    payment_total: Any,
    reference_total: Any,
    tolerance: Decimal = PAYMENT_TOLERANCE,
) -> bool:
    """True when the reconciliation delta is within tolerance (inclusive, <=)."""
    return reconciliation_delta(payment_total, reference_total) <= tolerance
