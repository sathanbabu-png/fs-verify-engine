"""
Reasonableness & Sanity Checks
Validates economic plausibility, margin trends, leverage, and efficiency ratios.
"""

from typing import List, Optional, Tuple
from .base import BaseCheck
from ..models import FinancialModel, CheckResult, CheckCategory, Severity
import statistics


class MarginDriftCheck(BaseCheck):
    """Flag projected margins that deviate significantly from historical range."""

    check_id = "RSN-001"
    check_name = "Margin Drift vs. Historical"
    category = CheckCategory.REASONABLENESS

    def _compute_margin(self, numerator: float, denominator: float) -> Optional[float]:
        return self._safe_div(numerator, denominator)

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        margin_defs = [
            ("Gross Margin", lambda ist: self._compute_margin(ist.gross_profit, ist.revenue)),
            ("EBIT Margin", lambda ist: self._compute_margin(ist.ebit, ist.revenue)),
            ("Net Margin", lambda ist: self._compute_margin(ist.net_income, ist.revenue)),
        ]

        hist_periods = model.historical_periods or []
        proj_periods = model.projected_periods or []

        for margin_name, margin_fn in margin_defs:
            # Compute historical margins
            hist_margins = []
            for p in hist_periods:
                ist = model.income_statements.get(p)
                if ist and ist.revenue != 0:
                    m = margin_fn(ist)
                    if m is not None:
                        hist_margins.append(m)

            if len(hist_margins) < 2:
                continue  # Need at least 2 historical periods

            hist_mean = statistics.mean(hist_margins)
            hist_std = statistics.stdev(hist_margins) if len(hist_margins) > 1 else 0
            hist_min = min(hist_margins)
            hist_max = max(hist_margins)

            for p in proj_periods:
                ist = model.income_statements.get(p)
                if not ist or ist.revenue == 0:
                    continue
                m = margin_fn(ist)
                if m is None:
                    continue
                # Flag if > 2 std devs from mean or outside historical range by > 500bps
                outside_range = m < hist_min - 0.05 or m > hist_max + 0.05
                if hist_std > 0:
                    z_score = (m - hist_mean) / hist_std
                    extreme = abs(z_score) > 2.5
                else:
                    z_score = 0
                    extreme = outside_range

                passed = not (extreme or outside_range)
                msg = (f"{margin_name}={m:.2%} (hist range: {hist_min:.2%}-{hist_max:.2%},"
                       f" mean={hist_mean:.2%}, z={z_score:.1f})")
                results.append(self._make_result(
                    period=p, passed=passed, msg=msg,
                    expected=hist_mean, actual=m,
                    severity_on_fail=Severity.WARNING,
                    details={
                        "margin_name": margin_name,
                        "historical_mean": hist_mean,
                        "historical_std": hist_std,
                        "historical_min": hist_min,
                        "historical_max": hist_max,
                        "z_score": z_score,
                    }
                ))
        return results


class RevenueGrowthReasonability(BaseCheck):
    """Flag extreme revenue growth rates in projections."""

    check_id = "RSN-002"
    check_name = "Revenue Growth Reasonability"
    category = CheckCategory.REASONABLENESS

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        periods = model.get_ordered_periods()
        for i in range(1, len(periods)):
            prev_period = periods[i - 1]
            curr_period = periods[i]
            ist_prev = model.income_statements.get(prev_period)
            ist_curr = model.income_statements.get(curr_period)
            if not ist_prev or not ist_curr or ist_prev.revenue == 0:
                continue
            growth = (ist_curr.revenue - ist_prev.revenue) / abs(ist_prev.revenue)
            # Flag if growth > 50% or < -30% (aggressive thresholds)
            reasonable = -0.30 <= growth <= 0.50
            msg = (f"Revenue growth={growth:.2%}"
                   f" ({prev_period}: {ist_prev.revenue:.2f} → {curr_period}: {ist_curr.revenue:.2f})"
                   + ("" if reasonable else " — outside -30% to +50% range"))
            results.append(self._make_result(
                period=curr_period, passed=reasonable, msg=msg,
                expected=None, actual=growth,
                severity_on_fail=Severity.WARNING if abs(growth) < 1.0 else Severity.ERROR,
                details={"growth_rate": growth, "revenue_prior": ist_prev.revenue, "revenue_curr": ist_curr.revenue}
            ))
        return results


class LeverageRatioCheck(BaseCheck):
    """Check Debt/EBITDA and Interest Coverage ratios."""

    check_id = "RSN-003"
    check_name = "Leverage & Coverage Ratios"
    category = CheckCategory.REASONABLENESS

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            bs = model.balance_sheets.get(period)
            if not ist or not bs:
                continue

            total_debt = bs.short_term_debt + bs.current_portion_ltd + bs.long_term_debt
            ebitda = ist.ebit + ist.depreciation + ist.amortization
            if ist.ebitda:
                ebitda = ist.ebitda

            # Debt/EBITDA
            if ebitda > 0:
                debt_ebitda = total_debt / ebitda
                reasonable = debt_ebitda <= 8.0
                msg = f"Debt/EBITDA={debt_ebitda:.2f}x (Debt={total_debt:.2f}, EBITDA={ebitda:.2f})"
                if not reasonable:
                    msg += " — exceeds 8.0x"
                results.append(self._make_result(
                    period, reasonable, msg,
                    expected=None, actual=debt_ebitda,
                    severity_on_fail=Severity.WARNING,
                    details={"ratio": "Debt/EBITDA", "value": debt_ebitda}
                ))

            # Interest Coverage (EBIT / Interest Expense)
            if ist.interest_expense > 0:
                coverage = ist.ebit / ist.interest_expense
                reasonable = coverage >= 1.0
                msg = f"Interest Coverage={coverage:.2f}x (EBIT={ist.ebit:.2f}, IntExp={ist.interest_expense:.2f})"
                if not reasonable:
                    msg += " — below 1.0x, cannot cover interest"
                results.append(self._make_result(
                    period, reasonable, msg,
                    expected=None, actual=coverage,
                    severity_on_fail=Severity.ERROR if coverage < 1.0 else Severity.WARNING,
                    details={"ratio": "Interest Coverage", "value": coverage}
                ))
        return results


class WorkingCapitalEfficiency(BaseCheck):
    """Check DSO, DIO, DPO trends for reasonableness."""

    check_id = "RSN-004"
    check_name = "Working Capital Efficiency (DSO/DIO/DPO)"
    category = CheckCategory.REASONABLENESS

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            bs = model.balance_sheets.get(period)
            if not ist or not bs:
                continue

            metrics = []
            # DSO = AR / (Revenue / 365)
            if ist.revenue > 0:
                dso = bs.accounts_receivable / (ist.revenue / 365)
                metrics.append(("DSO", dso, 0, 180))
            # DIO = Inventory / (COGS / 365)
            if ist.cogs > 0:
                dio = bs.inventory / (ist.cogs / 365)
                metrics.append(("DIO", dio, 0, 365))
            # DPO = AP / (COGS / 365)
            if ist.cogs > 0:
                dpo = bs.accounts_payable / (ist.cogs / 365)
                metrics.append(("DPO", dpo, 0, 180))

            for name, value, low, high in metrics:
                reasonable = low <= value <= high
                msg = f"{name}={value:.1f} days" + ("" if reasonable else f" — outside {low}-{high} day range")
                results.append(self._make_result(
                    period, reasonable, msg,
                    expected=None, actual=value,
                    severity_on_fail=Severity.WARNING,
                    details={"metric": name, "days": value, "range": [low, high]}
                ))
        return results


class NegativeBalanceCheck(BaseCheck):
    """Flag implausible negative balances (e.g., negative cash, negative revenue)."""

    check_id = "RSN-005"
    check_name = "Negative Balance Detection"
    category = CheckCategory.REASONABLENESS

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            checks = []
            bs = model.balance_sheets.get(period)
            ist = model.income_statements.get(period)
            if bs:
                checks.extend([
                    ("Cash", bs.cash),
                    ("Accounts Receivable", bs.accounts_receivable),
                    ("Inventory", bs.inventory),
                    ("Total Assets", bs.total_assets),
                    ("Accounts Payable", bs.accounts_payable),
                ])
            if ist:
                checks.extend([
                    ("Revenue", ist.revenue),
                    ("COGS", ist.cogs),
                ])

            for label, value in checks:
                if value < -self.tolerance_abs:
                    results.append(self._make_result(
                        period=period, passed=False,
                        msg=f"{label}={value:.2f} is negative",
                        expected=0, actual=value,
                        severity_on_fail=Severity.ERROR,
                    ))
        return results


class CapExToRevenueCheck(BaseCheck):
    """Flag CapEx/Revenue ratios outside reasonable bounds."""

    check_id = "RSN-006"
    check_name = "CapEx Intensity Check"
    category = CheckCategory.REASONABLENESS

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            cf = model.cash_flows.get(period)
            if not ist or not cf or ist.revenue == 0:
                continue
            capex = abs(cf.capex)  # CF capex is typically negative
            ratio = capex / ist.revenue
            # Flag if CapEx > 40% of revenue (extremely capital-intensive)
            reasonable = ratio <= 0.40
            msg = f"CapEx/Revenue={ratio:.2%} (CapEx={capex:.2f}, Rev={ist.revenue:.2f})"
            if not reasonable:
                msg += " — exceeds 40%"
            results.append(self._make_result(
                period, reasonable, msg,
                expected=None, actual=ratio,
                severity_on_fail=Severity.WARNING,
                details={"capex_intensity": ratio}
            ))
        return results


class FCFCheck(BaseCheck):
    """Verify FCF = CFO - CapEx if FCF is provided, and flag persistent negative FCF."""

    check_id = "RSN-007"
    check_name = "Free Cash Flow Verification"
    category = CheckCategory.REASONABLENESS

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        negative_fcf_streak = 0
        for period in model.get_ordered_periods():
            cf = model.cash_flows.get(period)
            if not cf:
                continue
            computed_fcf = cf.cash_from_operations + cf.capex  # capex is negative
            if cf.free_cash_flow is not None:
                passed = self._is_close(computed_fcf, cf.free_cash_flow)
                msg = (f"Computed FCF={computed_fcf:.2f} vs stated FCF={cf.free_cash_flow:.2f}"
                       if not passed else "FCF calculation OK.")
                results.append(self._make_result(
                    period, passed, msg,
                    expected=computed_fcf, actual=cf.free_cash_flow,
                    severity_on_fail=Severity.ERROR,
                ))
            # Track negative FCF
            if computed_fcf < 0:
                negative_fcf_streak += 1
            else:
                negative_fcf_streak = 0

            if negative_fcf_streak >= 3:
                results.append(self._make_result(
                    period, False,
                    f"Negative FCF for {negative_fcf_streak} consecutive periods (FCF={computed_fcf:.2f})",
                    severity_on_fail=Severity.WARNING,
                    details={"consecutive_negative_periods": negative_fcf_streak}
                ))
        return results


REASONABLENESS_CHECKS = [
    MarginDriftCheck,
    RevenueGrowthReasonability,
    LeverageRatioCheck,
    WorkingCapitalEfficiency,
    NegativeBalanceCheck,
    CapExToRevenueCheck,
    FCFCheck,
]
