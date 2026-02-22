"""
Structural Integrity Checks
Validates intra-statement arithmetic consistency.
"""

from typing import List
from .base import BaseCheck
from ..models import FinancialModel, CheckResult, CheckCategory, Severity


class BalanceSheetBalances(BaseCheck):
    """Verify Assets = Liabilities + Equity for every period."""

    check_id = "STR-001"
    check_name = "Balance Sheet Balances (A = L + E)"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            bs = model.balance_sheets.get(period)
            if not bs:
                continue
            expected = bs.total_assets
            actual = bs.total_liabilities_and_equity
            passed = self._is_close(expected, actual)
            msg = (f"A={expected:.2f}, L+E={actual:.2f}, Δ={actual - expected:.4f}"
                   if not passed else "Balance sheet balances.")
            results.append(self._make_result(
                period, passed, msg,
                expected=expected, actual=actual,
                severity_on_fail=Severity.CRITICAL,
            ))
        return results


class BalanceSheetTotalAssets(BaseCheck):
    """Verify Total Assets = Current Assets + Non-Current Assets."""

    check_id = "STR-002"
    check_name = "Total Assets Summation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            bs = model.balance_sheets.get(period)
            if not bs:
                continue
            computed = bs.total_current_assets + bs.total_non_current_assets
            actual = bs.total_assets
            passed = self._is_close(computed, actual)
            msg = (f"CA({bs.total_current_assets:.2f}) + NCA({bs.total_non_current_assets:.2f})"
                   f" = {computed:.2f} vs stated {actual:.2f}"
                   if not passed else "Total assets summation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class BalanceSheetTotalLiabilities(BaseCheck):
    """Verify Total Liabilities = Current + Non-Current Liabilities."""

    check_id = "STR-003"
    check_name = "Total Liabilities Summation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            bs = model.balance_sheets.get(period)
            if not bs:
                continue
            computed = bs.total_current_liabilities + bs.total_non_current_liabilities
            actual = bs.total_liabilities
            passed = self._is_close(computed, actual)
            msg = (f"CL({bs.total_current_liabilities:.2f}) + NCL({bs.total_non_current_liabilities:.2f})"
                   f" = {computed:.2f} vs stated {actual:.2f}"
                   if not passed else "Total liabilities summation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class BalanceSheetLESum(BaseCheck):
    """Verify L+E = Total Liabilities + Total Equity."""

    check_id = "STR-004"
    check_name = "Liabilities + Equity Summation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            bs = model.balance_sheets.get(period)
            if not bs:
                continue
            computed = bs.total_liabilities + bs.total_equity
            actual = bs.total_liabilities_and_equity
            passed = self._is_close(computed, actual)
            msg = (f"TL({bs.total_liabilities:.2f}) + TE({bs.total_equity:.2f})"
                   f" = {computed:.2f} vs stated L+E={actual:.2f}"
                   if not passed else "L+E summation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class IncomeStatementGrossProfit(BaseCheck):
    """Verify Gross Profit = Revenue - COGS."""

    check_id = "STR-010"
    check_name = "Gross Profit Calculation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            if not ist:
                continue
            computed = ist.revenue - ist.cogs
            actual = ist.gross_profit
            passed = self._is_close(computed, actual)
            msg = (f"Revenue({ist.revenue:.2f}) - COGS({ist.cogs:.2f}) = {computed:.2f}"
                   f" vs stated GP={actual:.2f}"
                   if not passed else "Gross profit calculation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class IncomeStatementEBIT(BaseCheck):
    """Verify EBIT = Gross Profit - Total OpEx (or GP - SGA - R&D - D&A - Other)."""

    check_id = "STR-011"
    check_name = "EBIT Calculation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            if not ist:
                continue
            # Try using total_opex first, else sum components
            if ist.total_opex != 0:
                computed = ist.gross_profit - ist.total_opex
            else:
                opex = ist.sga + ist.rd + ist.depreciation + ist.amortization + ist.other_opex
                computed = ist.gross_profit - opex
            actual = ist.ebit
            passed = self._is_close(computed, actual)
            msg = (f"Computed EBIT={computed:.2f} vs stated EBIT={actual:.2f}"
                   if not passed else "EBIT calculation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class IncomeStatementEBT(BaseCheck):
    """Verify EBT = EBIT - Interest Expense + Interest Income + Other."""

    check_id = "STR-012"
    check_name = "EBT Calculation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            if not ist:
                continue
            computed = ist.ebit - ist.interest_expense + ist.interest_income + ist.other_income_expense
            actual = ist.ebt
            passed = self._is_close(computed, actual)
            msg = (f"EBIT({ist.ebit:.2f}) - IntExp({ist.interest_expense:.2f})"
                   f" + IntInc({ist.interest_income:.2f}) + Other({ist.other_income_expense:.2f})"
                   f" = {computed:.2f} vs stated EBT={actual:.2f}"
                   if not passed else "EBT calculation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class IncomeStatementNetIncome(BaseCheck):
    """Verify Net Income = EBT - Tax Expense."""

    check_id = "STR-013"
    check_name = "Net Income Calculation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            ist = model.income_statements.get(period)
            if not ist:
                continue
            computed = ist.ebt - ist.tax_expense
            actual = ist.net_income
            passed = self._is_close(computed, actual)
            msg = (f"EBT({ist.ebt:.2f}) - Tax({ist.tax_expense:.2f}) = {computed:.2f}"
                   f" vs stated NI={actual:.2f}"
                   if not passed else "Net income calculation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class CashFlowReconciliation(BaseCheck):
    """Verify Beginning Cash + Net Change = Ending Cash."""

    check_id = "STR-020"
    check_name = "Cash Flow Reconciliation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            cf = model.cash_flows.get(period)
            if not cf:
                continue
            computed_ending = cf.beginning_cash + cf.net_change_in_cash
            passed = self._is_close(computed_ending, cf.ending_cash)
            msg = (f"Begin({cf.beginning_cash:.2f}) + ΔCash({cf.net_change_in_cash:.2f})"
                   f" = {computed_ending:.2f} vs stated Ending={cf.ending_cash:.2f}"
                   if not passed else "Cash reconciliation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed_ending, actual=cf.ending_cash,
                severity_on_fail=Severity.CRITICAL,
            ))
        return results


class CashFlowNetChangeCalc(BaseCheck):
    """Verify Net Change = CFO + CFI + CFF."""

    check_id = "STR-021"
    check_name = "Net Change in Cash Calculation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            cf = model.cash_flows.get(period)
            if not cf:
                continue
            computed = cf.cash_from_operations + cf.cash_from_investing + cf.cash_from_financing
            actual = cf.net_change_in_cash
            passed = self._is_close(computed, actual)
            msg = (f"CFO({cf.cash_from_operations:.2f}) + CFI({cf.cash_from_investing:.2f})"
                   f" + CFF({cf.cash_from_financing:.2f}) = {computed:.2f}"
                   f" vs stated ΔCash={actual:.2f}"
                   if not passed else "Net change in cash summation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.CRITICAL,
            ))
        return results


class CashFlowFromOperationsCalc(BaseCheck):
    """Verify CFO = NI + D&A + SBC + ΔWC + Other adjustments."""

    check_id = "STR-022"
    check_name = "Cash From Operations Build-Up"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            cf = model.cash_flows.get(period)
            if not cf:
                continue
            computed = (cf.net_income + cf.depreciation_amortization +
                        cf.stock_based_compensation + cf.deferred_taxes +
                        cf.change_in_receivables + cf.change_in_inventory +
                        cf.change_in_payables + cf.change_in_other_working_capital +
                        cf.other_operating)
            actual = cf.cash_from_operations
            passed = self._is_close(computed, actual)
            msg = (f"Computed CFO={computed:.2f} vs stated CFO={actual:.2f}"
                   if not passed else "CFO build-up OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
                details={
                    "net_income": cf.net_income,
                    "da": cf.depreciation_amortization,
                    "sbc": cf.stock_based_compensation,
                    "deferred_taxes": cf.deferred_taxes,
                    "delta_ar": cf.change_in_receivables,
                    "delta_inv": cf.change_in_inventory,
                    "delta_ap": cf.change_in_payables,
                    "delta_other_wc": cf.change_in_other_working_capital,
                    "other_op": cf.other_operating,
                }
            ))
        return results


class PPENetCalc(BaseCheck):
    """Verify Net PP&E = Gross PP&E - Accumulated Depreciation."""

    check_id = "STR-030"
    check_name = "Net PP&E Calculation"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            bs = model.balance_sheets.get(period)
            if not bs:
                continue
            if bs.ppe_gross == 0 and bs.accumulated_depreciation == 0 and bs.ppe_net == 0:
                continue  # No PPE data
            computed = bs.ppe_gross - bs.accumulated_depreciation
            actual = bs.ppe_net
            passed = self._is_close(computed, actual)
            msg = (f"Gross PPE({bs.ppe_gross:.2f}) - AccDepr({bs.accumulated_depreciation:.2f})"
                   f" = {computed:.2f} vs stated Net PPE={actual:.2f}"
                   if not passed else "Net PP&E calculation OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class CurrentAssetsBreakdown(BaseCheck):
    """Verify Total Current Assets = sum of current asset line items."""

    check_id = "STR-031"
    check_name = "Current Assets Breakdown"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            bs = model.balance_sheets.get(period)
            if not bs:
                continue
            computed = (bs.cash + bs.short_term_investments + bs.accounts_receivable +
                        bs.inventory + bs.prepaid_expenses + bs.other_current_assets)
            actual = bs.total_current_assets
            passed = self._is_close(computed, actual)
            msg = (f"Sum of CA items={computed:.2f} vs stated TCA={actual:.2f}"
                   if not passed else "Current assets breakdown OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class CurrentLiabilitiesBreakdown(BaseCheck):
    """Verify Total Current Liabilities = sum of CL line items."""

    check_id = "STR-032"
    check_name = "Current Liabilities Breakdown"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            bs = model.balance_sheets.get(period)
            if not bs:
                continue
            computed = (bs.accounts_payable + bs.accrued_liabilities + bs.short_term_debt +
                        bs.current_portion_ltd + bs.other_current_liabilities)
            actual = bs.total_current_liabilities
            passed = self._is_close(computed, actual)
            msg = (f"Sum of CL items={computed:.2f} vs stated TCL={actual:.2f}"
                   if not passed else "Current liabilities breakdown OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


class EquityBreakdown(BaseCheck):
    """Verify Total Equity = sum of equity components."""

    check_id = "STR-033"
    check_name = "Total Equity Breakdown"
    category = CheckCategory.STRUCTURAL

    def run(self, model: FinancialModel) -> List[CheckResult]:
        results = []
        for period in model.get_ordered_periods():
            bs = model.balance_sheets.get(period)
            if not bs:
                continue
            computed = (bs.common_stock + bs.additional_paid_in_capital +
                        bs.retained_earnings + bs.treasury_stock +
                        bs.accumulated_other_comprehensive_income)
            actual = bs.total_equity
            passed = self._is_close(computed, actual)
            msg = (f"Sum of equity items={computed:.2f} vs stated TE={actual:.2f}"
                   if not passed else "Equity breakdown OK.")
            results.append(self._make_result(
                period, passed, msg,
                expected=computed, actual=actual,
                severity_on_fail=Severity.ERROR,
            ))
        return results


# Registry of all structural checks
STRUCTURAL_CHECKS = [
    BalanceSheetBalances,
    BalanceSheetTotalAssets,
    BalanceSheetTotalLiabilities,
    BalanceSheetLESum,
    IncomeStatementGrossProfit,
    IncomeStatementEBIT,
    IncomeStatementEBT,
    IncomeStatementNetIncome,
    CashFlowReconciliation,
    CashFlowNetChangeCalc,
    CashFlowFromOperationsCalc,
    PPENetCalc,
    CurrentAssetsBreakdown,
    CurrentLiabilitiesBreakdown,
    EquityBreakdown,
]
