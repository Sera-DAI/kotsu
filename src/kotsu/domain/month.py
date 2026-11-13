"""Calendar month, no time zone. Each month stands on its own (D9)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True, slots=True, order=True)
class Month:
    year: int
    month: int

    def __post_init__(self) -> None:
        if not 1 <= self.month <= 12:
            raise ValueError(f"invalid month: {self.month}")

    @classmethod
    def of(cls, date: dt.date) -> Month:
        return cls(date.year, date.month)

    def add(self, months: int) -> Month:
        index = self.year * 12 + (self.month - 1) + months
        return Month(index // 12, index % 12 + 1)

    def previous(self) -> Month:
        return self.add(-1)

    def next(self) -> Month:
        return self.add(1)

    @property
    def start(self) -> dt.date:
        return dt.date(self.year, self.month, 1)

    @property
    def end_exclusive(self) -> dt.date:
        return self.next().start

    @property
    def name(self) -> str:
        return f"{NAMES[self.month - 1]} {self.year}"
