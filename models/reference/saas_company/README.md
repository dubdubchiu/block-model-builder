# SaaS company reference model

The acceptance model: a generic subscription software company, quarterly for eight years. Every figure is illustrative; it describes no real company.

## Files

| File | What it is |
|---|---|
| `saas_company_reference_model.xlsx` | The workbook, with live formulas and cached values (recalculated in LibreOffice). |
| `generator/spec.py` | The model's single source of truth: drivers, series, and each calculation row written once in the formula DSL. |
| `generator/dsl.py` | The DSL parser, plus translators to Excel formulas and to numpy. The numpy side is a reference implementation of the block semantics, and the oracle for `engine/tests/test_blocks.py`. |
| `generator/build.py` | Writes the workbook from `spec.py`. |
| `generator/model_np.py`, `generator/check.py` | Evaluate `spec.py` in numpy, and compare the result with the recalculated workbook row by row. |
| `snapshot_expected.py` | Reads the workbook's cached values into `expected.json`. |
| `expected.json` | The test fixture: timeline, period labels, years, all 80 calculation rows and 4 annual rows, the 32 expected ids with role and tolerance, and the report lines. |

The generator needs numpy, scipy and openpyxl, which are not engine dependencies, and LibreOffice Calc to recalculate the workbook.

## The model

- **Customers:** new customers are the tighter of what marketing spend buys and what the sales team can close. Churn applies to customers at the start of each quarter; customers who join aren't churned in the quarter they join. The count uses a closed form, `retention * cumulative(new / retention, opening)` with `retention = (1 - churn)^t`, because spec rows can't refer to themselves.
- **Revenue:** average customers times a monthly ARPA that rises 3% a year, three months a quarter. ARR is end-of-quarter MRR times 12.
- **Costs:** hosting per customer, support and payment fees as a share of revenue; sales and marketing, R&D and G&A from headcount; a one-time platform rebuild spread over four quarters.
- **Cash:** capex and straight-line depreciation, tax with losses carried forward, receivables, deferred revenue and payables, two equity raises.
- **Unit economics:** fully loaded CAC, LTV to CAC, CAC payback, burn multiple, rule of 40, runway.
- **Valuation:** Gordon-growth terminal value, NPV (checked against discount factors) and IRR.
- **Scenario drivers:** quarterly churn and monthly ARPA carry low and high values, which the importer turns into four scenarios.

## Acceptance rule

Tests read `expected.json`, never the workbook. A value passes when `|got - want| <= max(1e-6, rel * |want|)`, with `rel = 1e-6`. Rows marked `exact` (the bool flags) must match exactly. `required` rows gate the test. `checkpoint` rows are reported row by row, to locate the first divergence.

## Verification record (2026-10-01)

- `generator/check.py` on the LibreOffice-recalculated workbook: 0 failures; the worst relative difference is 2.8e-14 (`change_in_nwc`, period 26).
- The engine, importing `spec.py`, matches all 84 rows of `expected.json`; the worst relative difference is 2.8e-14.
- Headline values: NPV 51,239,655 at an 18% annual discount rate; IRR 11.28% per quarter (53.37% annual); ARR from 10.2M to 86.6M.

## Regenerating

Only when the reference model changes on purpose. Commit the workbook, `expected.json` and the example together.

```
cd generator
uv run --no-project --python 3.12 --with numpy --with scipy --with openpyxl python build.py /tmp/built.xlsx
soffice --headless --convert-to xlsx --outdir /tmp/recalc /tmp/built.xlsx
uv run --no-project --python 3.12 --with numpy --with scipy --with openpyxl python check.py /tmp/recalc/built.xlsx
cp /tmp/recalc/built.xlsx ../saas_company_reference_model.xlsx
cd .. && uv run --no-project --python 3.12 --with openpyxl python snapshot_expected.py
cd ../../.. && uv run python -m blockmodel.importers.rows models/reference/saas_company/generator/spec.py \
  models/examples/saas_company.json --scenarios churn_rate_q,arpa_monthly
```
