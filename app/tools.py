"""Deterministic calculators. The model must call these instead of doing arithmetic."""


def calculate_gratuity(basic_monthly_salary: float, years_of_service: float) -> dict:
    """End-of-service gratuity, standard regime, full-time worker.

    21 days of basic wage per year for the first five years, 30 days per year after that
    (FDL 33/2021 Art. 51(2)); daily wage = monthly basic / 30 (Art. 67); the total may not
    exceed two years of wage (Art. 51(6)). Requires at least one year of service.
    Parts of a year are paid pro rata once one year is completed (Art. 51(3)).
    """
    if years_of_service < 1:
        return {"eligible": False, "amount_aed": 0.0,
                "note": "Less than one year of continuous service: no gratuity under the standard rule.",
                "sources": ["FDL 33/2021 Art. 51"]}
    daily = basic_monthly_salary / 30
    first = min(years_of_service, 5)
    extra = max(years_of_service - 5, 0)
    days = 21 * first + 30 * extra
    amount = days * daily
    cap = 24 * basic_monthly_salary
    return {"eligible": True,
            "days_of_basic_wage": round(days, 2),
            "daily_basic_wage": round(daily, 2),
            "amount_aed": round(min(amount, cap), 2),
            "cap_applied": amount > cap,
            "basis": "basic wage only, not allowances",
            "sources": ["FDL 33/2021 Art. 51(2), 51(6), 67"]}


def calculate_leave_accrued(months_of_service: int) -> dict:
    """Statutory minimum annual leave earned in the first year of service.

    FDL 33/2021 Art. 29(1)(b): two days per month if service is more than six months and
    less than a year. Up to six months there is no statutory accrual (a contract may give more).
    """
    if months_of_service <= 6:
        return {"days": 0, "note": "No statutory accrual up to six months of service; check the contract.",
                "sources": ["FDL 33/2021 Art. 29(1)(b)"]}
    if months_of_service < 12:
        return {"days": 2 * months_of_service, "rule": "2 days per month",
                "sources": ["FDL 33/2021 Art. 29(1)(b)"]}
    return {"days": None, "annual_entitlement_days": 30,
            "note": "From one year of service the minimum is 30 days per year (partial years not computed here).",
            "sources": ["FDL 33/2021 Art. 29(1)(a)"]}


TOOL_SCHEMAS = [
    {"name": "calculate_gratuity",
     "description": "Compute end-of-service gratuity in AED from monthly BASIC salary and years of service. Always use this for gratuity amounts.",
     "input_schema": {"type": "object",
                      "properties": {"basic_monthly_salary": {"type": "number", "description": "Monthly basic salary in AED"},
                                     "years_of_service": {"type": "number", "description": "Years of continuous service"}},
                      "required": ["basic_monthly_salary", "years_of_service"]}},
    {"name": "calculate_leave_accrued",
     "description": "Compute statutory annual leave days earned in the first year of service from months of service.",
     "input_schema": {"type": "object",
                      "properties": {"months_of_service": {"type": "integer"}},
                      "required": ["months_of_service"]}},
]

_TOOLS = {"calculate_gratuity": calculate_gratuity, "calculate_leave_accrued": calculate_leave_accrued}


def run_tool(name: str, args: dict) -> dict:
    if name not in _TOOLS:
        return {"error": f"unknown tool {name}"}
    try:
        return _TOOLS[name](**args)
    except TypeError as e:
        return {"error": f"bad arguments: {e}"}