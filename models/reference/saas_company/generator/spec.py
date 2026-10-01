"""SaaS company reference model: single source of truth.

A generic subscription software company, quarterly for eight years. Every figure is illustrative.
Every calculation row is written once in the formula DSL. build.py translates the DSL into live
Excel formulas, and check.py evaluates the same DSL independently in numpy; the two must agree.
"""

ILL = "illustrative"

PERIODS = 32

TIMELINE = {
    "start_date": "2027-01-01",
    "frequency": "quarter",
    "periods": PERIODS,
    "months_per_period": 3,
    "fiscal_year_end": "12-31",
}

# id, label, group, type, unit, value, low, high, source, notes
DRIVERS = [
    # Customers
    ("opening_customers", "Customers at start of period 1", "Customers", "quantity", "customers", 400, None, None, ILL, ""),
    ("marketing_spend", "Marketing spend", "Customers", "series<currency>", "USD", "series", None, None, ILL,
     "Paid acquisition, events and content, per quarter."),
    ("marketing_cost_per_customer", "Marketing cost per new customer", "Customers", "currency", "USD/customer", 15000, 10000, 22000, ILL,
     "Marketing spend needed to win one customer; sales team cost is separate."),
    ("sales_reps", "Quota-carrying sales reps", "Customers", "series<count>", "FTE", "series", None, None, ILL, ""),
    ("deals_per_rep_q", "Deals each rep can close per quarter", "Customers", "float", "customers/FTE", 10, 7, 14, ILL,
     "Caps new customers when the sales team, not marketing, is the constraint."),
    ("churn_rate_q", "Quarterly customer churn", "Customers", "percent", "fraction", 0.04, 0.02, 0.07, ILL,
     "Share of customers at the start of a quarter who cancel during it."),
    # Pricing
    ("arpa_monthly", "Average revenue per account (monthly)", "Pricing", "currency", "USD/customer", 2000, 1500, 2600, ILL,
     "List price net of discounts, per customer per month, in period 1."),
    ("price_growth_annual", "Annual price increase", "Pricing", "percent", "fraction", 0.03, 0.0, 0.06, ILL, ""),
    ("months_per_quarter", "Months per quarter", "Pricing", "float", "months", 3, None, None, ILL, "Convention."),
    ("months_per_year", "Months per year", "Pricing", "float", "months", 12, None, None, ILL, "Convention."),
    # Cost of revenue
    ("hosting_cost_monthly", "Hosting cost per customer (monthly)", "Cost of revenue", "currency", "USD/customer", 140, 100, 200, ILL,
     "Cloud infrastructure and third-party services per customer per month."),
    ("support_cost_pct", "Customer support cost", "Cost of revenue", "percent", "fraction of revenue", 0.06, None, None, ILL, ""),
    ("payment_fees_pct", "Payment processing fees", "Cost of revenue", "percent", "fraction of revenue", 0.025, None, None, ILL, ""),
    # Operating expenses
    ("sales_rep_cost_q", "Loaded cost per sales rep", "Operating expenses", "currency", "USD/FTE", 45000, None, None, ILL,
     "Salary, commission and benefits per quarter."),
    ("engineers", "Engineering headcount", "Operating expenses", "series<count>", "FTE", "series", None, None, ILL, ""),
    ("engineer_cost_q", "Loaded cost per engineer", "Operating expenses", "currency", "USD/FTE", 55000, None, None, ILL, "Per quarter."),
    ("ga_headcount", "G&A headcount", "Operating expenses", "series<count>", "FTE", "series", None, None, ILL,
     "Finance, people, legal and operations."),
    ("ga_cost_per_fte_q", "Loaded cost per G&A employee", "Operating expenses", "currency", "USD/FTE", 40000, None, None, ILL, "Per quarter."),
    ("other_opex_initial_q", "Other operating costs, period 1", "Operating expenses", "currency", "USD", 600000, None, None, ILL,
     "Rent, software and professional fees."),
    ("other_opex_growth_q", "Other operating cost growth per quarter", "Operating expenses", "percent", "fraction", 0.025, None, None, ILL, ""),
    ("platform_rebuild_cost", "Platform rebuild (one-time)", "Operating expenses", "currency", "USD", 6000000, None, None, ILL,
     "A one-time re-architecture project, expensed as incurred."),
    ("platform_rebuild_start", "Platform rebuild start period", "Operating expenses", "int", "period", 9, None, None, ILL, ""),
    ("platform_rebuild_periods", "Platform rebuild duration", "Operating expenses", "int", "quarters", 4, None, None, ILL, ""),
    # Capex
    ("growth_capex", "Growth capex", "Capex", "series<currency>", "USD", "series", None, None, ILL,
     "Office fit-outs and equipment for new hires."),
    ("maintenance_capex_pct", "Maintenance capex", "Capex", "percent", "fraction of revenue", 0.015, None, None, ILL, ""),
    ("asset_life_q", "Depreciable life", "Capex", "int", "quarters", 12, None, None, ILL, "Straight line, no salvage."),
    # Working capital and tax
    ("ar_days", "Receivable days", "Financing", "float", "days", 45, None, None, ILL, ""),
    ("ap_days", "Payable days", "Financing", "float", "days", 30, None, None, ILL, ""),
    ("days_per_quarter", "Days per quarter", "Financing", "float", "days", 91.25, None, None, ILL, "Convention."),
    ("annual_prepay_share", "Revenue billed annually in advance", "Financing", "percent", "fraction of revenue", 0.4, None, None, ILL,
     "Annual contracts billed up front create deferred revenue."),
    ("prepaid_quarters", "Average quarters of service prepaid", "Financing", "float", "quarters", 1.5, None, None, ILL,
     "Half of a year's billing, on average, is still unearned at quarter end."),
    ("tax_rate", "Blended income tax rate", "Financing", "percent", "fraction", 0.25, None, None, ILL,
     "Losses carried forward without limit or expiry."),
    # Financing
    ("opening_cash", "Opening cash, start of period 1", "Financing", "currency", "USD", 25000000, None, None, ILL, ""),
    ("equity_raises", "Equity raised", "Financing", "series<currency>", "USD", "series", None, None, ILL,
     "Scheduled raises; no cash-triggered financing (that would be circular)."),
    ("min_cash_balance", "Minimum cash balance", "Financing", "currency", "USD", 8000000, None, None, ILL, "Used only for the cash check flag."),
    # Valuation
    ("discount_rate_annual", "Discount rate (annual)", "Valuation", "percent", "fraction", 0.18, 0.12, 0.25, ILL, "Growth-stage rate on unlevered FCF."),
    ("terminal_growth_annual", "Terminal growth (annual)", "Valuation", "percent", "fraction", 0.03, 0.0, 0.05, ILL, ""),
    ("irr_guess_q", "IRR solver starting guess (quarterly)", "Valuation", "percent", "fraction", 0.05, None, None, ILL,
     "Only chooses between roots; does not change a unique answer."),
    ("terminal_period", "Terminal period", "Valuation", "int", "period", 32, None, None, ILL, "Equals the number of periods."),
]


def rep(values_by_block):
    out = []
    for n, v in values_by_block:
        out += [v] * n
    return out


SERIES = {
    "marketing_spend": [600_000 + 100_000 * i for i in range(16)] + [2_200_000 + 60_000 * i for i in range(16)],
    "sales_reps": [6, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20,
                   21, 21, 22, 22, 23, 23, 24, 24, 25, 25, 26, 26, 27, 27, 28, 28],
    "engineers": [20, 21, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 41, 42, 43, 44,
                  45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60],
    "ga_headcount": rep([(4, 6), (4, 8), (4, 10), (4, 12), (4, 14), (4, 15), (4, 16), (4, 17)]),
    "growth_capex": rep([(4, 400_000), (4, 250_000), (4, 900_000), (20, 300_000)]),
    "equity_raises": None,  # set below
}
SERIES["equity_raises"] = [0.0] * PERIODS
SERIES["equity_raises"][5] = 30e6  # period 6
SERIES["equity_raises"][13] = 40e6  # period 14

# Calculations: id, label, group, type, unit, formula, notes
# Types prefixed series<> are per period; others are scalars.
CALCS = [
    # Customers
    ("new_customers_from_marketing", "New customers marketing can win", "Customers", "series<count>", "customers",
     "round(marketing_spend / marketing_cost_per_customer, 0)", "Round half away from zero (Excel convention)."),
    ("sales_capacity", "New customers the sales team can close", "Customers", "series<quantity>", "customers",
     "sales_reps * deals_per_rep_q", ""),
    ("new_customers", "New customers", "Customers", "series<quantity>", "customers",
     "min(new_customers_from_marketing, sales_capacity)", "The tighter of marketing and sales capacity."),
    ("retention_factor", "Share of a period-1 customer still active", "Customers", "series<float>", "fraction",
     "growth(1 - churn_rate_q, 0 - churn_rate_q)", "(1 - churn) to the power t."),
    ("new_customers_scaled", "New customers scaled by retention", "Customers", "series<quantity>", "customers",
     "new_customers / retention_factor", "Helper for the closed-form customer count below."),
    ("customers_end", "Customers at end of quarter", "Customers", "series<quantity>", "customers",
     "retention_factor * cumulative(new_customers_scaled, opening_customers)",
     "Solves end = start * (1 - churn) + new without a feedback loop: new customers are not churned in the quarter they join."),
    ("customers_start", "Customers at start of quarter", "Customers", "series<quantity>", "customers",
     "if(flag(1, 1), opening_customers, lag(customers_end, 1))", ""),
    ("churned_customers", "Customers lost", "Customers", "series<quantity>", "customers", "customers_start * churn_rate_q", ""),
    ("net_new_customers", "Net new customers", "Customers", "series<quantity>", "customers", "new_customers - churned_customers", ""),
    ("average_customers", "Average customers", "Customers", "series<quantity>", "customers", "(customers_start + customers_end) / 2", ""),
    # Revenue
    ("price_growth_q", "Price increase per quarter", "Pricing", "percent", "fraction", "pow(1 + price_growth_annual, 0.25) - 1", ""),
    ("price_index", "Price index", "Pricing", "series<float>", "index", "growth(1, price_growth_q)", "1.0 in period 1."),
    ("arpa_effective", "Average revenue per account (monthly, current price)", "Pricing", "series<currency>", "USD/customer",
     "arpa_monthly * price_index", ""),
    ("mrr", "Monthly recurring revenue (end of quarter)", "Revenue", "series<currency>", "USD", "customers_end * arpa_effective", ""),
    ("arr", "Annual recurring revenue", "Revenue", "series<currency>", "USD", "mrr * months_per_year", ""),
    ("revenue", "Revenue", "Revenue", "series<currency>", "USD",
     "average_customers * arpa_effective * months_per_quarter", "Average customers over the quarter, three months each."),
    # Cost of revenue
    ("cogs_hosting", "Cost of revenue: hosting", "Cost of revenue", "series<currency>", "USD",
     "average_customers * hosting_cost_monthly * months_per_quarter", ""),
    ("cogs_support", "Cost of revenue: support", "Cost of revenue", "series<currency>", "USD", "revenue * support_cost_pct", ""),
    ("cogs_payments", "Cost of revenue: payment fees", "Cost of revenue", "series<currency>", "USD", "revenue * payment_fees_pct", ""),
    ("cogs_total", "Cost of revenue", "Cost of revenue", "series<currency>", "USD", "sum(cogs_hosting, cogs_support, cogs_payments)", ""),
    ("gross_profit", "Gross profit", "Cost of revenue", "series<currency>", "USD", "revenue - cogs_total", ""),
    ("gross_margin", "Gross margin", "Cost of revenue", "series<percent>", "fraction", "gross_profit / revenue",
     "Revenue is positive in every period, so no zero guard is needed."),
    # Operating expenses
    ("sales_team_cost", "Sales team cost", "Operating expenses", "series<currency>", "USD", "sales_reps * sales_rep_cost_q", ""),
    ("sales_marketing", "Sales and marketing", "Operating expenses", "series<currency>", "USD", "marketing_spend + sales_team_cost", ""),
    ("research_development", "Research and development", "Operating expenses", "series<currency>", "USD", "engineers * engineer_cost_q", ""),
    ("other_opex", "Other operating costs", "Operating expenses", "series<currency>", "USD",
     "growth(other_opex_initial_q, other_opex_growth_q)", ""),
    ("general_admin", "General and administrative", "Operating expenses", "series<currency>", "USD",
     "ga_headcount * ga_cost_per_fte_q + other_opex", ""),
    ("platform_rebuild", "Platform rebuild", "Operating expenses", "series<currency>", "USD",
     "spread(platform_rebuild_cost, platform_rebuild_start, platform_rebuild_periods)", ""),
    ("opex_total", "Operating expenses", "Operating expenses", "series<currency>", "USD",
     "sum(sales_marketing, research_development, general_admin, platform_rebuild)", ""),
    ("ebitda", "EBITDA", "Operating expenses", "series<currency>", "USD", "gross_profit - opex_total", ""),
    ("ebitda_margin", "EBITDA margin", "Operating expenses", "series<percent>", "fraction", "ebitda / revenue", ""),
    # Capex and depreciation
    ("maintenance_capex", "Maintenance capex", "Capex", "series<currency>", "USD", "revenue * maintenance_capex_pct", ""),
    ("capex_total", "Capex", "Capex", "series<currency>", "USD", "growth_capex + maintenance_capex", ""),
    ("depreciation", "Depreciation", "Capex", "series<currency>", "USD", "depreciation_sl(capex_total, asset_life_q)",
     "Each period's capex depreciated straight line from the period it is spent."),
    ("ebit", "EBIT", "Capex", "series<currency>", "USD", "ebitda - depreciation", "No debt, so EBT equals EBIT."),
    # Tax
    ("ebit_cumulative", "Cumulative EBIT", "Financing", "series<currency>", "USD", "cumulative(ebit, 0)", ""),
    ("taxable_income_cumulative", "Cumulative taxable income after losses", "Financing", "series<currency>", "USD",
     "max(0, running_max(ebit_cumulative))", ""),
    ("taxable_income", "Taxable income", "Financing", "series<currency>", "USD",
     "taxable_income_cumulative - lag(taxable_income_cumulative, 1)", ""),
    ("tax", "Income tax", "Financing", "series<currency>", "USD", "taxable_income * tax_rate", "Paid in the period incurred."),
    ("net_income", "Net income", "Financing", "series<currency>", "USD", "ebit - tax", ""),
    # Working capital
    ("accounts_receivable", "Accounts receivable", "Financing", "series<currency>", "USD",
     "revenue * ar_days / days_per_quarter", "End-of-period balance."),
    ("deferred_revenue", "Deferred revenue", "Financing", "series<currency>", "USD",
     "revenue * annual_prepay_share * prepaid_quarters", "Unearned annual prepayments at quarter end."),
    ("accounts_payable", "Accounts payable", "Financing", "series<currency>", "USD",
     "(cogs_total + other_opex) * ap_days / days_per_quarter", "End-of-period balance."),
    ("net_working_capital", "Net working capital", "Financing", "series<currency>", "USD",
     "accounts_receivable - deferred_revenue - accounts_payable", "Negative when prepayments exceed receivables."),
    ("change_in_nwc", "Change in net working capital", "Financing", "series<currency>", "USD",
     "net_working_capital - lag(net_working_capital, 1)", "Opening working capital is zero."),
    # Cash
    ("free_cash_flow", "Free cash flow (unlevered)", "Financing", "series<currency>", "USD",
     "ebitda - tax - capex_total - change_in_nwc", ""),
    ("cumulative_fcf", "Cumulative free cash flow", "Financing", "series<currency>", "USD", "cumulative(free_cash_flow, 0)", ""),
    ("net_cash_flow", "Net cash flow", "Financing", "series<currency>", "USD", "free_cash_flow + equity_raises",
     "No interest on cash (that would be circular)."),
    ("cash_balance", "Cash balance", "Financing", "series<currency>", "USD", "cumulative(net_cash_flow, opening_cash)", "End of period."),
    ("cash_above_minimum", "Cash above minimum", "Financing", "series<bool>", "flag", "cash_balance >= min_cash_balance", "Check."),
    ("cash_burn", "Cash burn", "Financing", "series<currency>", "USD", "max(0, 0 - free_cash_flow)", "Zero once free cash flow is positive."),
    ("runway_quarters", "Runway at current burn", "Financing", "series<float>", "quarters",
     "safe_divide(cash_balance, cash_burn, 0)", "0 when the company isn't burning cash."),
    # Unit economics
    ("cac_fully_loaded", "Customer acquisition cost (fully loaded)", "Unit economics", "series<currency>", "USD/customer",
     "safe_divide(sales_marketing, new_customers, 0)", "Sales and marketing per new customer."),
    ("gross_profit_per_customer_month", "Gross profit per customer per month", "Unit economics", "series<currency>", "USD/customer",
     "arpa_effective * gross_margin", ""),
    ("customer_lifetime_quarters", "Expected customer lifetime", "Unit economics", "float", "quarters", "1 / churn_rate_q", ""),
    ("lifetime_value", "Customer lifetime value", "Unit economics", "series<currency>", "USD/customer",
     "gross_profit_per_customer_month * months_per_quarter * customer_lifetime_quarters", "Gross profit over the expected lifetime."),
    ("ltv_to_cac", "Lifetime value to CAC", "Unit economics", "series<float>", "ratio", "safe_divide(lifetime_value, cac_fully_loaded, 0)", ""),
    ("cac_payback_months", "CAC payback", "Unit economics", "series<float>", "months",
     "safe_divide(cac_fully_loaded, gross_profit_per_customer_month, 0)", "Months of gross profit to recover acquisition cost."),
    ("revenue_growth_yoy", "Revenue growth, year over year", "Unit economics", "series<percent>", "fraction",
     "safe_divide(revenue - lag(revenue, 4), lag(revenue, 4), 0)", "0 in the first year, which has no prior-year quarter."),
    ("rule_of_40", "Rule of 40 score", "Unit economics", "series<percent>", "fraction", "revenue_growth_yoy + ebitda_margin",
     "Growth plus EBITDA margin; 40% or more is the usual bar."),
    ("rule_of_40_met", "Rule of 40 met", "Unit economics", "series<bool>", "flag", "rule_of_40 >= 0.4", "Check."),
    ("net_new_arr", "Net new ARR", "Unit economics", "series<currency>", "USD", "arr - lag(arr, 1)", "Period 1 counts all opening ARR."),
    ("burn_multiple", "Burn multiple", "Unit economics", "series<float>", "ratio", "safe_divide(cash_burn, net_new_arr, 0)",
     "Cash burned per dollar of net new ARR; 0 once burn stops."),
    ("headcount", "Headcount", "Unit economics", "series<count>", "FTE", "sum(sales_reps, engineers, ga_headcount)", ""),
    ("revenue_per_employee", "Annualized revenue per employee", "Unit economics", "series<currency>", "USD/FTE",
     "revenue * 4 / headcount", ""),
    ("customers_won_total", "Customers won, total", "Unit economics", "quantity", "customers", "total(new_customers)", ""),
    # Valuation
    ("discount_rate_q", "Discount rate (quarterly)", "Valuation", "percent", "fraction", "pow(1 + discount_rate_annual, 0.25) - 1", ""),
    ("terminal_growth_q", "Terminal growth (quarterly)", "Valuation", "percent", "fraction", "pow(1 + terminal_growth_annual, 0.25) - 1", ""),
    ("terminal_flag", "Terminal period flag", "Valuation", "series<bool>", "flag", "flag(terminal_period, terminal_period)", ""),
    ("terminal_fcf_series", "FCF in terminal period", "Valuation", "series<currency>", "USD", "if(terminal_flag, free_cash_flow, 0)", ""),
    ("terminal_fcf", "Terminal-period FCF", "Valuation", "currency", "USD", "total(terminal_fcf_series)", ""),
    ("terminal_value", "Terminal value (Gordon growth)", "Valuation", "currency", "USD",
     "terminal_fcf * (1 + terminal_growth_q) / (discount_rate_q - terminal_growth_q)", "Value at end of terminal period."),
    ("terminal_value_flow", "Terminal value in cash flow", "Valuation", "series<currency>", "USD", "if(terminal_flag, terminal_value, 0)", ""),
    ("valuation_cash_flow", "Valuation cash flow (FCF plus TV)", "Valuation", "series<currency>", "USD",
     "free_cash_flow + terminal_value_flow", ""),
    ("npv_value", "NPV", "Valuation", "currency", "USD", "npv(discount_rate_q, valuation_cash_flow)",
     "Convention: period t discounted by (1 + r)^t, t from 1 (Excel NPV). Valued at start of period 1."),
    ("discount_factor_q", "Discount factor", "Valuation", "series<float>", "factor", "discount_factor(discount_rate_q)", "1 / (1 + r)^t."),
    ("pv_valuation_cash_flow", "PV of valuation cash flow", "Valuation", "series<currency>", "USD", "valuation_cash_flow * discount_factor_q", ""),
    ("npv_check", "NPV via discount factors", "Valuation", "currency", "USD", "total(pv_valuation_cash_flow)",
     "Must equal npv_value; pins the NPV timing convention."),
    ("irr_quarterly", "IRR (quarterly)", "Valuation", "percent", "fraction", "irr(valuation_cash_flow, irr_guess_q)", ""),
    ("irr_annual", "IRR (annualized)", "Valuation", "percent", "fraction", "pow(1 + irr_quarterly, 4) - 1", ""),
]

# Annual rollups: id, label, type, unit, formula
ANNUAL = [
    ("revenue_annual", "Revenue", "currency", "USD", "annual(revenue)"),
    ("ebitda_annual", "EBITDA", "currency", "USD", "annual(ebitda)"),
    ("free_cash_flow_annual", "Free cash flow", "currency", "USD", "annual(free_cash_flow)"),
    ("new_customers_annual", "New customers", "quantity", "customers", "annual(new_customers)"),
]

# Expected: required outputs first, then intermediate checkpoints.
EXPECTED = [
    "revenue", "arr", "customers_end", "gross_margin", "ebitda", "free_cash_flow", "cash_balance",
    "npv_value", "irr_annual", "ltv_to_cac", "cac_payback_months", "burn_multiple",
    # checkpoints
    "new_customers", "retention_factor", "churned_customers", "average_customers", "price_index", "cogs_total",
    "opex_total", "depreciation", "tax", "change_in_nwc", "npv_check", "irr_quarterly", "terminal_value",
    "cash_above_minimum", "rule_of_40_met", "customers_won_total",
]

# Report: id, display format
REPORT = [
    ("customers_end", "#,##0"), ("new_customers", "#,##0"), ("churned_customers", "#,##0"),
    ("arr", "$#,##0"), ("revenue", "$#,##0"), ("cogs_total", "$#,##0"), ("gross_profit", "$#,##0"), ("gross_margin", "0.0%"),
    ("sales_marketing", "$#,##0"), ("research_development", "$#,##0"), ("general_admin", "$#,##0"), ("opex_total", "$#,##0"),
    ("ebitda", "$#,##0"), ("ebitda_margin", "0.0%"), ("depreciation", "$#,##0"), ("ebit", "$#,##0"), ("tax", "$#,##0"),
    ("net_income", "$#,##0"), ("capex_total", "$#,##0"), ("change_in_nwc", "$#,##0"), ("free_cash_flow", "$#,##0"),
    ("equity_raises", "$#,##0"), ("cash_balance", "$#,##0"), ("runway_quarters", "#,##0.0"),
    ("cac_fully_loaded", "$#,##0"), ("ltv_to_cac", "0.0"), ("cac_payback_months", "#,##0.0"), ("rule_of_40", "0.0%"),
    ("npv_value", "$#,##0"), ("irr_annual", "0.0%"),
]
