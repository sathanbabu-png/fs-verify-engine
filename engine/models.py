"""
Financial Statement Data Models
Standardized internal representation for 3-statement models.
All monetary values assumed in consistent units (e.g., $M).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import json


class Severity(Enum):
    """Check result severity levels."""
    PASS = "pass"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CheckCategory(Enum):
    """Categories of verification checks."""
    STRUCTURAL = "structural"
    CROSS_STATEMENT = "cross_statement"
    REASONABLENESS = "reasonableness"
    CIRCULAR = "circular"


@dataclass
class CheckResult:
    """Result of a single verification check."""
    check_id: str
    check_name: str
    category: CheckCategory
    severity: Severity
    period: Optional[str]  # e.g., "FY2024", "Q1-2025"
    message: str
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    delta: Optional[float] = None
    delta_pct: Optional[float] = None
    tolerance: Optional[float] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "check_name": self.check_name,
            "category": self.category.value,
            "severity": self.severity.value,
            "period": self.period,
            "message": self.message,
            "expected_value": self.expected_value,
            "actual_value": self.actual_value,
            "delta": self.delta,
            "delta_pct": self.delta_pct,
            "tolerance": self.tolerance,
            "details": self.details,
        }


@dataclass
class IncomeStatement:
    """Single-period Income Statement line items."""
    period: str
    revenue: float = 0.0
    cogs: float = 0.0
    gross_profit: float = 0.0
    sga: float = 0.0
    rd: float = 0.0
    other_opex: float = 0.0
    depreciation: float = 0.0
    amortization: float = 0.0
    total_opex: float = 0.0
    ebit: float = 0.0
    interest_expense: float = 0.0
    interest_income: float = 0.0
    other_income_expense: float = 0.0
    ebt: float = 0.0
    tax_expense: float = 0.0
    net_income: float = 0.0
    # Optional granularity
    ebitda: Optional[float] = None
    effective_tax_rate: Optional[float] = None
    shares_outstanding_basic: Optional[float] = None
    shares_outstanding_diluted: Optional[float] = None
    eps_basic: Optional[float] = None
    eps_diluted: Optional[float] = None


@dataclass
class BalanceSheet:
    """Single-period Balance Sheet line items."""
    period: str
    # Current Assets
    cash: float = 0.0
    short_term_investments: float = 0.0
    accounts_receivable: float = 0.0
    inventory: float = 0.0
    prepaid_expenses: float = 0.0
    other_current_assets: float = 0.0
    total_current_assets: float = 0.0
    # Non-Current Assets
    ppe_gross: float = 0.0
    accumulated_depreciation: float = 0.0
    ppe_net: float = 0.0
    goodwill: float = 0.0
    intangible_assets: float = 0.0
    other_non_current_assets: float = 0.0
    total_non_current_assets: float = 0.0
    total_assets: float = 0.0
    # Current Liabilities
    accounts_payable: float = 0.0
    accrued_liabilities: float = 0.0
    short_term_debt: float = 0.0
    current_portion_ltd: float = 0.0
    other_current_liabilities: float = 0.0
    total_current_liabilities: float = 0.0
    # Non-Current Liabilities
    long_term_debt: float = 0.0
    deferred_tax_liability: float = 0.0
    other_non_current_liabilities: float = 0.0
    total_non_current_liabilities: float = 0.0
    total_liabilities: float = 0.0
    # Equity
    common_stock: float = 0.0
    additional_paid_in_capital: float = 0.0
    retained_earnings: float = 0.0
    treasury_stock: float = 0.0
    accumulated_other_comprehensive_income: float = 0.0
    total_equity: float = 0.0
    total_liabilities_and_equity: float = 0.0


@dataclass
class CashFlowStatement:
    """Single-period Cash Flow Statement line items."""
    period: str
    # Operating
    net_income: float = 0.0
    depreciation_amortization: float = 0.0
    stock_based_compensation: float = 0.0
    deferred_taxes: float = 0.0
    change_in_receivables: float = 0.0
    change_in_inventory: float = 0.0
    change_in_payables: float = 0.0
    change_in_other_working_capital: float = 0.0
    other_operating: float = 0.0
    cash_from_operations: float = 0.0
    # Investing
    capex: float = 0.0
    acquisitions: float = 0.0
    purchase_of_investments: float = 0.0
    sale_of_investments: float = 0.0
    other_investing: float = 0.0
    cash_from_investing: float = 0.0
    # Financing
    debt_issuance: float = 0.0
    debt_repayment: float = 0.0
    equity_issuance: float = 0.0
    share_repurchases: float = 0.0
    dividends_paid: float = 0.0
    other_financing: float = 0.0
    cash_from_financing: float = 0.0
    # Summary
    net_change_in_cash: float = 0.0
    beginning_cash: float = 0.0
    ending_cash: float = 0.0
    # Optional
    free_cash_flow: Optional[float] = None


@dataclass
class FinancialModel:
    """Complete 3-statement financial model across multiple periods."""
    company_name: str = "Unknown"
    currency: str = "USD"
    unit: str = "millions"
    periods: List[str] = field(default_factory=list)
    historical_periods: List[str] = field(default_factory=list)
    projected_periods: List[str] = field(default_factory=list)
    income_statements: Dict[str, IncomeStatement] = field(default_factory=dict)
    balance_sheets: Dict[str, BalanceSheet] = field(default_factory=dict)
    cash_flows: Dict[str, CashFlowStatement] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_ordered_periods(self) -> List[str]:
        """Return periods in chronological order."""
        return self.periods if self.periods else sorted(
            set(list(self.income_statements.keys()) +
                list(self.balance_sheets.keys()) +
                list(self.cash_flows.keys()))
        )

    def has_complete_period(self, period: str) -> bool:
        """Check if all 3 statements exist for a period."""
        return (period in self.income_statements and
                period in self.balance_sheets and
                period in self.cash_flows)

    def to_dict(self) -> dict:
        """Serialize the full model to a dictionary."""
        return {
            "company_name": self.company_name,
            "currency": self.currency,
            "unit": self.unit,
            "periods": self.periods,
            "historical_periods": self.historical_periods,
            "projected_periods": self.projected_periods,
            "income_statements": {k: vars(v) for k, v in self.income_statements.items()},
            "balance_sheets": {k: vars(v) for k, v in self.balance_sheets.items()},
            "cash_flows": {k: vars(v) for k, v in self.cash_flows.items()},
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)
