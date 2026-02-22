"""
Cross-Statement Consistency Checks
Validates linkages and consistency between Income Statement, Balance Sheet, and Cash Flow.
"""

from typing import List
from .base import BaseCheck
from ..models import FinancialModel, CheckResult, CheckCategory, Severity


class NetIncomeLinkage(BaseCheck):
    """Verify Net Income on IS matches NI on Cash Flow Statement."""

    check_id = "XST-001"
    check_name = "Net Income Linkage (IS → CF)"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            cf = model.cash_flows.get(period)
            if not ist or not cf:
                continue
            passed = self._is_close(ist.net_income, cf.net_income)
            msg = (f"IS NI={ist.net_income:.2f} vs CF NI={cf.net_income:.2f}"
                   if not passed else "Net income linkage IS→CF OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=ist.net_income, actual=cf.net_income,
                severity_on_fail=Severity.CRITICAL,
            ))
        return results


class RetainedEarningsRollforward(BaseCheck):
    """Verify RE(t) = RE(t-1) + NI - Dividends (±other comprehensive items)."""

    check_id = "XST-002"
    check_name = "Retained Earnings Rollforward"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        periods = model.get_ordered_periods()
        for i in range(1, len(periods)):
            prev_period = periods[i - 1]
            curr_period = periods[i]
            bs_prev = model.balance_sheets.get(prev_period)
            bs_curr = model.balance_sheets.get(curr_period)
            ist = model.income_statements.get(curr_period)
            cf = model.cash_flows.get(curr_period)
            if not all([bs_prev, bs_curr, ist]):
                continue

            dividends = cf.dividends_paid if cf else 0.0
            # Dividends paid on CF is typically negative (outflow)
            # RE(t) = RE(t-1) + NI + dividends_paid (where div_paid is negative)
            computed = bs_prev.retained_earnings + ist.net_income + dividends
            actual = bs_curr.retained_earnings
            # Use wider tolerance for RE rollforward since buybacks/other items may flow through
            passed = self._is_close(computed, actual, abs_tol=max(self.tolerance_abs, abs(actual) * 0.02))
            msg = (f"RE(t-1)={bs_prev.retained_earnings:.2f} + NI={ist.net_income:.2f}"
                   f" + Div={dividends:.2f} = {computed:.2f}"
                   f" vs stated RE(t)={actual:.2f}"
                   if not passed else "Retained earnings rollforward OK.")
            results.append(self._make_result(
                period=curr_period, passed=passed, msg=msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
                details={
                    "re_prior": bs_prev.retained_earnings,
                    "net_income": ist.net_income,
                    "dividends_paid": dividends,
                    "note": "Δ may include share buybacks, AOCI reclasses, or other equity items"
                }
            ))
        return results


class CashEndingToBS(BaseCheck):
    """Verify Ending Cash on CF matches Cash on Balance Sheet."""

    check_id = "XST-003"
    check_name = "Ending Cash Linkage (CF → BS)"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            cf = model.cash_flows.get(period)
            bs = model.balance_sheets.get(period)
            if not cf or not bs:
                continue
            passed = self._is_close(cf.ending_cash, bs.cash)
            msg = (f"CF ending cash={cf.ending_cash:.2f} vs BS cash={bs.cash:.2f}"
                   if not passed else "Ending cash linkage CF→BS OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=cf.ending_cash, actual=bs.cash,
                severity_on_fail=Severity.CRITICAL,
            ))
        return results


class CashBeginningContinuity(BaseCheck):
    """Verify Beginning Cash(t) = Ending Cash(t-1) on CF, and Ending Cash(t-1) = BS Cash(t-1)."""

    check_id = "XST-004"
    check_name = "Cash Continuity Between Periods"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        periods = model.get_ordered_periods()
        for i in range(1, len(periods)):
            prev_period = periods[i - 1]
            curr_period = periods[i]
            cf_prev = model.cash_flows.get(prev_period)
            cf_curr = model.cash_flows.get(curr_period)
            if not cf_prev or not cf_curr:
                continue
            passed = self._is_close(cf_prev.ending_cash, cf_curr.beginning_cash)
            msg = (f"Ending cash ({prev_period})={cf_prev.ending_cash:.2f}"
                   f" vs Beginning cash ({curr_period})={cf_curr.beginning_cash:.2f}"
                   if not passed else f"Cash continuity {prev_period}→{curr_period} OK.")
            results.append(self._make_result(
                period=curr_period, passed=passed, msg=msg,
                expected=cf_prev.ending_cash, actual=cf_curr.beginning_cash,
                severity_on_fail=Severity.CRITICAL,
            ))
        return results


class DALinkage(BaseCheck):
    """Verify D&A on CF approximates D&A on IS (if split out)."""

    check_id = "XST-005"
    check_name = "D&A Linkage (IS ↔ CF)"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            cf = model.cash_flows.get(period)
            if not ist or not cf:
                continue
            is_da = ist.depreciation + ist.amortization
            cf_da = cf.depreciation_amortization
            if is_da == 0 and cf_da == 0:
                continue
            passed = self._is_close(is_da, cf_da)
            msg = (f"IS D&A={is_da:.2f} vs CF D&A={cf_da:.2f}"
                   if not passed else "D&A linkage IS↔CF OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=is_da, actual=cf_da,
                severity_on_fail=Severity.WARNING,
                details={"note": "May differ due to amortization of financing costs or other non-IS D&A"}
            ))
        return results


class PPERollforward(BaseCheck):
    """Verify PPE(t) ≈ PPE(t-1) + CapEx - Depreciation (net)."""

    check_id = "XST-006"
    check_name = "PP&E Rollforward"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        periods = model.get_ordered_periods()
        for i in range(1, len(periods)):
            prev_period = periods[i - 1]
            curr_period = periods[i]
            bs_prev = model.balance_sheets.get(prev_period)
            bs_curr = model.balance_sheets.get(curr_period)
            cf = model.cash_flows.get(curr_period)
            ist = model.income_statements.get(curr_period)
            if not all([bs_prev, bs_curr, cf]):
                continue
            # CapEx is typically negative on CF (outflow), depreciation reduces net PPE
            depreciation = ist.depreciation if ist else (cf.depreciation_amortization if cf else 0)
            # Net PPE(t) ≈ Net PPE(t-1) + CapEx(negative, so subtract) - Depreciation
            # CapEx on CF is negative, so: PPE(t) ≈ PPE(t-1) - CapEx(CF) - Depr
            # Actually: PPE(t) = PPE(t-1) + CapEx(as positive) - Depr
            # CF capex is negative outflow, so additions = -capex
            computed = bs_prev.ppe_net + (-cf.capex) - depreciation
            actual = bs_curr.ppe_net
            if bs_prev.ppe_net == 0 and actual == 0:
                continue
            # Wider tolerance — disposals, impairments, reclasses not modeled
            tol = max(self.tolerance_abs, abs(actual) * 0.05)
            passed = self._is_close(computed, actual, abs_tol=tol)
            msg = (f"PPE(t-1)={bs_prev.ppe_net:.2f} + CapEx={-cf.capex:.2f}"
                   f" - Depr={depreciation:.2f} = {computed:.2f}"
                   f" vs stated PPE(t)={actual:.2f}"
                   if not passed else "PP&E rollforward OK.")
            results.append(self._make_result(
                period=curr_period, passed=passed, msg=msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.WARNING,
                details={"note": "Δ may include disposals, impairments, FX, or acquisitions"}
            ))
        return results


class DebtRollforward(BaseCheck):
    """Verify Total Debt(t) ≈ Debt(t-1) + Issuance - Repayment."""

    check_id = "XST-007"
    check_name = "Total Debt Rollforward"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        periods = model.get_ordered_periods()
        for i in range(1, len(periods)):
            prev_period = periods[i - 1]
            curr_period = periods[i]
            bs_prev = model.balance_sheets.get(prev_period)
            bs_curr = model.balance_sheets.get(curr_period)
            cf = model.cash_flows.get(curr_period)
            if not all([bs_prev, bs_curr, cf]):
                continue

            def total_debt(bs):
                return bs.short_term_debt + bs.current_portion_ltd + bs.long_term_debt

            debt_prev = total_debt(bs_prev)
            debt_curr = total_debt(bs_curr)
            # debt_repayment is typically negative on CF
            computed = debt_prev + cf.debt_issuance + cf.debt_repayment
            if debt_prev == 0 and debt_curr == 0:
                continue
            tol = max(self.tolerance_abs, abs(debt_curr) * 0.03)
            passed = self._is_close(computed, debt_curr, abs_tol=tol)
            msg = (f"Debt(t-1)={debt_prev:.2f} + Issue={cf.debt_issuance:.2f}"
                   f" + Repay={cf.debt_repayment:.2f} = {computed:.2f}"
                   f" vs Debt(t)={debt_curr:.2f}"
                   if not passed else "Debt rollforward OK.")
            results.append(self._make_result(
                period=curr_period, passed=passed, msg=msg,
                expected=computed, actual=debt_curr,
                severity_on_fail=Severity.WARNING,
                details={"note": "Δ may include FX translation, amortization of discount/premium, reclasses"}
            ))
        return results


class InterestExpenseReasonability(BaseCheck):
    """Verify interest expense is reasonable vs. average debt balance."""

    check_id = "XST-008"
    check_name = "Interest Expense vs. Avg Debt"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        periods = model.get_ordered_periods()
        for i in range(1, len(periods)):
            prev_period = periods[i - 1]
            curr_period = periods[i]
            bs_prev = model.balance_sheets.get(prev_period)
            bs_curr = model.balance_sheets.get(curr_period)
            ist = model.income_statements.get(curr_period)
            if not all([bs_prev, bs_curr, ist]):
                continue

            def total_debt(bs):
                return bs.short_term_debt + bs.current_portion_ltd + bs.long_term_debt

            avg_debt = (total_debt(bs_prev) + total_debt(bs_curr)) / 2
            if avg_debt <= 0 or ist.interest_expense <= 0:
                continue
            implied_rate = ist.interest_expense / avg_debt
            # Flag if implied rate is outside 0.5%-15% range
            reasonable = 0.005 <= implied_rate <= 0.15
            msg = (f"Implied interest rate={implied_rate:.2%} on avg debt={avg_debt:.2f}"
                   f" (IntExp={ist.interest_expense:.2f})"
                   + ("" if reasonable else " — outside 0.5%-15% range"))
            results.append(self._make_result(
                period=curr_period, passed=reasonable, msg=msg,
                expected=None, actual=implied_rate,
                severity_on_fail=Severity.WARNING,
                details={
                    "avg_debt": avg_debt,
                    "interest_expense": ist.interest_expense,
                    "implied_rate": implied_rate,
                }
            ))
        return results


class WorkingCapitalDeltasCF(BaseCheck):
    """Verify ΔAR, ΔInventory, ΔAP on CF match BS changes (with sign convention)."""

    check_id = "XST-009"
    check_name = "Working Capital Deltas (BS Δ vs. CF)"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        periods = model.get_ordered_periods()
        for i in range(1, len(periods)):
            prev_period = periods[i - 1]
            curr_period = periods[i]
            bs_prev = model.balance_sheets.get(prev_period)
            bs_curr = model.balance_sheets.get(curr_period)
            cf = model.cash_flows.get(curr_period)
            if not all([bs_prev, bs_curr, cf]):
                continue

            wc_items = [
                ("ΔAR", -(bs_curr.accounts_receivable - bs_prev.accounts_receivable), cf.change_in_receivables),
                ("ΔInv", -(bs_curr.inventory - bs_prev.inventory), cf.change_in_inventory),
                ("ΔAP", (bs_curr.accounts_payable - bs_prev.accounts_payable), cf.change_in_payables),
            ]

            for label, bs_delta, cf_value in wc_items:
                if bs_delta == 0 and cf_value == 0:
                    continue
                tol = max(self.tolerance_abs, max(abs(bs_delta), abs(cf_value)) * 0.05)
                passed = self._is_close(bs_delta, cf_value, abs_tol=tol)
                msg = (f"{label}: BS-implied={bs_delta:.2f} vs CF stated={cf_value:.2f}"
                       if not passed else f"{label} consistency OK.")
                results.append(self._make_result(
                    period=curr_period, passed=passed, msg=msg,
                    expected=bs_delta, actual=cf_value,
                    severity_on_fail=Severity.WARNING,
                    details={"item": label, "note": "Sign convention: asset increase = cash use (negative on CF)"}
                ))
        return results


class EffectiveTaxRateCheck(BaseCheck):
    """Verify tax expense / EBT is reasonable and consistent."""

    check_id = "XST-010"
    check_name = "Effective Tax Rate Consistency"
    category = CheckCategory.CROSS_STATEMENT

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            if not ist or ist.ebt == 0:
                continue
            etr = ist.tax_expense / ist.ebt
            # Flag if ETR is negative or above 50%
            reasonable = -0.05 <= etr <= 0.50
            msg = (f"ETR={etr:.2%} (Tax={ist.tax_expense:.2f}, EBT={ist.ebt:.2f})"
                   + ("" if reasonable else " — outside -5% to 50% range"))
            results.append(self._make_result(
                period, reasonable, msg,
                expected=None, actual=etr,
                severity_on_fail=Severity.WARNING,
                details={"effective_tax_rate": etr}
            ))
        return results


CROSS_STATEMENT_CHECKS = [
    NetIncomeLinkage,
    RetainedEarningsRollforward,
    CashEndingToBS,
    CashBeginningContinuity,
    DALinkage,
    PPERollforward,
    DebtRollforward,
    InterestExpenseReasonability,
    WorkingCapitalDeltasCF,
    EffectiveTaxRateCheck,
]
