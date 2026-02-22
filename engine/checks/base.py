"""
Base Check Class and Check Registry
All verification checks inherit from BaseCheck.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from ..models import FinancialModel, CheckResult, Severity, CheckCategory
import math


class BaseCheck(ABC):
    """Abstract base class for all verification checks."""

    def __init__(self, tolerance_abs: float = 0.01, tolerance_pct: float = 0.001):
        """
        Args:
            tolerance_abs: Absolute tolerance for equality checks (e.g., 0.01 = $10K if unit is $M)
            tolerance_pct: Percentage tolerance for ratio checks (0.001 = 0.1%)
        """
        self.tolerance_abs = tolerance_abs
        self.tolerance_pct = tolerance_pct

    @property
    @abstractmethod
    def check_id(self) -> str:
        """Unique identifier for this check (e.g., 'STR-001')."""
        ...

    @property
    @abstractmethod
    def check_name(self) -> str:
        """Human-readable check name."""
        ...

    @property
    @abstractmethod
    def category(self) -> CheckCategory:
        """Check category."""
        ...

    @abstractmethod
    def run(self, model: FinancialModel) -> List[CheckResult]:
        """Execute the check and return results."""
        ...

    def _is_close(self, a: float, b: float, abs_tol: Optional[float] = None) -> bool:
        """Check if two values are approximately equal within tolerance."""
        tol = abs_tol if abs_tol is not None else self.tolerance_abs
        return math.isclose(a, b, abs_tol=tol, rel_tol=self.tolerance_pct)

    def _delta(self, expected: float, actual: float) -> float:
        return actual - expected

    def _delta_pct(self, expected: float, actual: float) -> Optional[float]:
        if expected == 0:
            return None if actual == 0 else float('inf')
        return (actual - expected) / abs(expected)

    def _make_result(
        self,
        period: str,
        passed: bool,
        message: str,
        expected: Optional[float] = None,
        actual: Optional[float] = None,
        severity_on_fail: Severity = Severity.ERROR,
        details: Optional[Dict[str, Any]] = None,
    ) -> CheckResult:
        """Helper to construct a CheckResult."""
        delta = None
        delta_pct = None
        if expected is not None and actual is not None:
            delta = self._delta(expected, actual)
            delta_pct = self._delta_pct(expected, actual)

        return CheckResult(
            check_id=self.check_id,
            check_name=self.check_name,
            category=self.category,
            severity=Severity.PASS if passed else severity_on_fail,
            period=period,
            message=message,
            expected_value=expected,
            actual_value=actual,
            delta=delta,
            delta_pct=delta_pct,
            tolerance=self.tolerance_abs,
            details=details,
        )

    def _safe_div(self, numerator: float, denominator: float) -> Optional[float]:
        """Safe division returning None on zero denominator."""
        if denominator == 0:
            return None
        return numerator / denominator


class CheckRegistry:
    """Registry of all available checks."""

    def __init__(self):
        self._checks: Dict[str, BaseCheck] = {}

    def register(self, check: BaseCheck):
        self._checks[check.check_id] = check

    def get_all(self) -> List[BaseCheck]:
        return list(self._checks.values())

    def get_by_category(self, category: CheckCategory) -> List[BaseCheck]:
        return [c for c in self._checks.values() if c.category == category]

    def get_by_id(self, check_id: str) -> Optional[BaseCheck]:
        return self._checks.get(check_id)
