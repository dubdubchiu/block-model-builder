"""Period arithmetic for a model timeline: dates, labels, and fiscal years."""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from .model import Timeline

MONTHS_PER_PERIOD = {"month": 1, "quarter": 3, "year": 12}


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


@dataclass(frozen=True)
class TimelineCalc:
    periods: int
    t: np.ndarray  # 1..N as float, for arithmetic with rates
    starts: tuple[date, ...]
    ends: tuple[date, ...]
    labels: tuple[str, ...]
    calendar_year: np.ndarray  # year of each period's end
    fiscal_year: np.ndarray  # fiscal year of each period (the year it ends in)
    years: tuple[int, ...]  # distinct fiscal years, in order: the columns of annual values
    year_index: np.ndarray  # position of each period's fiscal year in `years`

    def length(self, shape: str) -> int:
        return len(self.years) if shape == "annual" else self.periods

    def label(self, shape: str, i: int) -> str:
        return f"FY{self.years[i]}" if shape == "annual" else self.labels[i]


def _label(start: date, frequency: str) -> str:
    if frequency == "month":
        return f"{start.year}-{start.month:02d}"
    if frequency == "quarter":
        return f"{start.year}Q{(start.month - 1) // 3 + 1}"
    return str(start.year)


def build_timeline(tl: Timeline) -> TimelineCalc:
    step = MONTHS_PER_PERIOD[tl.frequency]
    fy_month, fy_day = (int(x) for x in tl.fiscal_year_end.split("-"))
    starts = tuple(_add_months(tl.start, i * step) for i in range(tl.periods))
    ends = tuple(_add_months(s, step) - timedelta(days=1) for s in starts)
    fiscal = [e.year if (e.month, e.day) <= (fy_month, fy_day) else e.year + 1 for e in ends]
    years = tuple(dict.fromkeys(fiscal))
    index = {y: i for i, y in enumerate(years)}
    return TimelineCalc(
        periods=tl.periods,
        t=np.arange(1, tl.periods + 1, dtype=float),
        starts=starts,
        ends=ends,
        labels=tuple(_label(s, tl.frequency) for s in starts),
        calendar_year=np.array([e.year for e in ends]),
        fiscal_year=np.array(fiscal),
        years=years,
        year_index=np.array([index[y] for y in fiscal]),
    )
