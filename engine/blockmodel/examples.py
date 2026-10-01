"""Examples built in code, written to models/examples/ and checked for freshness by the tests.

uv run python -m blockmodel.examples
"""

from datetime import date
from pathlib import Path

from .builder import ModelBuilder
from .model import Model, Timeline

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "models" / "examples"


def cash_interest_model() -> Model:
    """Interest on the cash balance: a loop through a Feedback block.

    cash[t] = cash[t-1] + operating cash flow[t] + rate * cash[t-1], with cash[0] = opening cash.
    """
    b = ModelBuilder(
        "Example: interest on the cash balance (feedback loop)",
        Timeline(start=date(2027, 1, 1), frequency="quarter", periods=12),
        namespace="cash_interest",
    )
    opening = b.constant(1_000_000, kind="currency", unit="USD", label="Opening cash", key="opening")
    rate = b.constant(0.02, kind="percent", label="Interest rate per quarter", key="rate")
    flows = b.series(
        [
            -150_000,
            -120_000,
            -80_000,
            -40_000,
            0,
            40_000,
            80_000,
            120_000,
            160_000,
            200_000,
            240_000,
            280_000,
        ],
        kind="currency",
        unit="USD",
        label="Operating cash flow",
        key="flows",
    )
    previous = b.add("series.feedback", initial=opening, label="Cash at start of quarter", key="previous")
    interest = b.add("math.multiply", a=previous, b=rate, label="Interest earned", key="interest")
    net = b.add("math.add", a=flows, b=interest, label="Net cash flow", key="net")
    cash = b.add("math.add", a=previous, b=net, label="Cash at end of quarter", key="cash")
    b.connect(cash, previous, "x")
    b.report(interest, "Interest earned", "$#,##0")
    b.report(cash, "Cash at end of quarter", "$#,##0")
    b.scenario("high-rate", "Interest at 3% per quarter", {rate: {"value": 0.03}})
    return b.build()


EXAMPLES = {"cash_interest": cash_interest_model}


def main() -> None:
    for name, make in EXAMPLES.items():
        path = EXAMPLES_DIR / f"{name}.json"
        path.write_text(make().model_dump_json(by_alias=True, indent=1) + "\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
