from app.tools import calculate_gratuity, calculate_leave_accrued


def test_gratuity_four_years():
    assert calculate_gratuity(15000, 4)["amount_aed"] == 42000.0


def test_gratuity_under_one_year():
    assert calculate_gratuity(15000, 0.8)["eligible"] is False


def test_gratuity_cap_two_years_wage():
    r = calculate_gratuity(10000, 40)
    assert r["cap_applied"] and r["amount_aed"] == 240000.0


def test_leave_seven_months():
    assert calculate_leave_accrued(7)["days"] == 14


def test_leave_under_six_months():
    assert calculate_leave_accrued(3)["days"] == 0