from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP, localcontext


CENT = Decimal("0.01")
ZERO = Decimal("0")


def _due_dates(first_due_date, count):
    dates = []
    for index in range(count):
        month_index = first_due_date.month - 1 + index
        year = first_due_date.year + month_index // 12
        month = month_index % 12 + 1
        day = min(first_due_date.day, monthrange(year, month)[1])
        dates.append(first_due_date.replace(year=year, month=month, day=day))
    return dates


def build_emi_schedule(principal, annual_rate_percent, count, first_due_date,
                       calculation_method, disbursement_date=None):
    """Return a fixed-payment reducing-balance schedule with cent-rounded rows."""
    principal = Decimal(principal).quantize(CENT, rounding=ROUND_HALF_UP)
    annual_rate = Decimal(annual_rate_percent or ZERO) / Decimal("100")
    if principal <= ZERO or count < 1:
        raise ValueError("Principal and installment count must be greater than zero.")

    due_dates = _due_dates(first_due_date, count)
    if calculation_method == "flat":
        with localcontext() as context:
            context.prec = 36
            total_interest = (principal * annual_rate * Decimal(count) / Decimal("12")).quantize(
                CENT, rounding=ROUND_HALF_UP,
            )
            regular_principal = (principal / Decimal(count)).quantize(CENT, rounding=ROUND_HALF_UP)
            regular_interest = (total_interest / Decimal(count)).quantize(CENT, rounding=ROUND_HALF_UP)
            regular_payment = regular_principal + regular_interest
            balance = principal
            interest_remaining = total_interest
            previous_date = disbursement_date
            rows = []
            for index, due_date in enumerate(due_dates):
                principal_due = regular_principal if index < count - 1 else balance
                interest_due = regular_interest if index < count - 1 else interest_remaining
                payment = principal_due + interest_due
                closing_balance = max(balance - principal_due, ZERO).quantize(CENT, rounding=ROUND_HALF_UP)
                rows.append({
                    "installment_number": index + 1,
                    "due_date": due_date,
                    "opening_balance": balance,
                    "principal_due": principal_due,
                    "interest_due": interest_due,
                    "interest_days": (due_date - previous_date).days if previous_date else None,
                    "expected_amount": payment,
                    "closing_balance": closing_balance,
                })
                balance = closing_balance
                interest_remaining -= interest_due
                previous_date = due_date
            return rows, regular_payment, total_interest

    if calculation_method == "monthly_reducing":
        monthly_rate = annual_rate / Decimal("12")
        period_rates = [monthly_rate] * count
    elif calculation_method in ("actual_365", "actual_360"):
        if not disbursement_date:
            raise ValueError("A disbursement date is required for daily interest calculation.")
        denominator = Decimal("365") if calculation_method == "actual_365" else Decimal("360")
        period_rates = []
        previous_date = disbursement_date
        for due_date in due_dates:
            days = (due_date - previous_date).days
            if days <= 0:
                raise ValueError("The first due date must be after the disbursement date.")
            period_rates.append(annual_rate * Decimal(days) / denominator)
            previous_date = due_date
    else:
        raise ValueError("Choose a supported interest calculation method.")

    with localcontext() as context:
        context.prec = 36
        future_factor = Decimal("1")
        payment_factor_sum = ZERO
        factors = [Decimal("1") + rate for rate in period_rates]
        for factor in reversed(factors):
            payment_factor_sum += future_factor
            future_factor *= factor
        regular_payment = (principal * future_factor / payment_factor_sum).quantize(
            CENT, rounding=ROUND_HALF_UP,
        )

        rows = []
        balance = principal
        previous_date = disbursement_date
        total_interest = ZERO
        for index, (due_date, period_rate) in enumerate(zip(due_dates, period_rates)):
            interest = (balance * period_rate).quantize(CENT, rounding=ROUND_HALF_UP)
            payment = regular_payment if index < count - 1 else (balance + interest).quantize(
                CENT, rounding=ROUND_HALF_UP,
            )
            principal_due = (payment - interest).quantize(CENT, rounding=ROUND_HALF_UP)
            closing_balance = max(balance - principal_due, ZERO).quantize(CENT, rounding=ROUND_HALF_UP)
            rows.append({
                "installment_number": index + 1,
                "due_date": due_date,
                "opening_balance": balance,
                "principal_due": principal_due,
                "interest_due": interest,
                "interest_days": (due_date - previous_date).days if previous_date else None,
                "expected_amount": payment,
                "closing_balance": closing_balance,
            })
            total_interest += interest
            balance = closing_balance
            previous_date = due_date

    return rows, regular_payment, total_interest
