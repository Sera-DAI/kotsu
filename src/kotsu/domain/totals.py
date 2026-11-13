"""Month totals. Never stored: the storage layer computes them and hands them over here."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MonthTotals:
    income: int = 0
    expenses: int = 0
    count: int = 0  # entries in the month (or in the filter)

    @property
    def balance(self) -> int:
        """Income minus expenses for the month (D8)."""
        return self.income - self.expenses
