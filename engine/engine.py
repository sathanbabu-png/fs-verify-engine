"""
Financial Statement Verification Engine
Main orchestrator that runs all checks and aggregates results.
"""

import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from .models import FinancialModel, CheckResult, Severity, CheckCategory
from .checks.base import BaseCheck, CheckRegistry
from .checks import ALL_CHECKS


class VerificationEngine:
    """
    Core verification engine.
    Instantiates all checks, runs them against a FinancialModel,
    and produces a structured verification report.
    """

    def __init__(
        self,
        tolerance_abs: float = 0.01,
        tolerance_pct: float = 0.001,
        enabled_categories: Optional[List[CheckCategory]] = None,
        disabled_check_ids: Optional[List[str]] = None,
    ):
        self.tolerance_abs = tolerance_abs
        self.tolerance_pct = tolerance_pct
        self.enabled_categories = enabled_categories
        self.disabled_check_ids = set(disabled_check_ids or [])

        self.registry = CheckRegistry()
        self._register_all_checks()

    def _register_all_checks(self):
        """Instantiate and register all check classes."""
        for check_cls in ALL_CHECKS:
            check = check_cls(
                tolerance_abs=self.tolerance_abs,
                tolerance_pct=self.tolerance_pct,
            )
            if check.check_id not in self.disabled_check_ids:
                if self.enabled_categories is None or check.category in self.enabled_categories:
                    self.registry.register(check)

    def run(self, model: FinancialModel) -> "VerificationReport":
        """Run all registered checks against the model."""
        all_results: List[CheckResult] = []
        check_metadata: List[Dict[str, str]] = []

        for check in self.registry.get_all():
            try:
                results = check.run(model)
                all_results.extend(results)
                check_metadata.append({
                    "check_id": check.check_id,
                    "check_name": check.check_name,
                    "category": check.category.value,
                    "status": "completed",
                    "result_count": len(results),
                })
            except Exception as e:
                check_metadata.append({
                    "check_id": check.check_id,
                    "check_name": check.check_name,
                    "category": check.category.value,
                    "status": "error",
                    "error": str(e),
                })

        return VerificationReport(
            model=model,
            results=all_results,
            check_metadata=check_metadata,
        )


class VerificationReport:
    """Aggregated verification report with summary statistics."""

    def __init__(
        self,
        model: FinancialModel,
        results: List[CheckResult],
        check_metadata: List[Dict[str, str]],
    ):
        self.model = model
        self.results = results
        self.check_metadata = check_metadata
        self.timestamp = datetime.now().isoformat()

    @property
    def total_checks(self) -> int:
        return len(self.results)

    @property
    def pass_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.PASS)

    @property
    def fail_count(self) -> int:
        return self.total_checks - self.pass_count

    @property
    def critical_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.CRITICAL)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for r in self.results if r.severity == Severity.WARNING)

    @property
    def pass_rate(self) -> float:
        return self.pass_count / self.total_checks if self.total_checks > 0 else 0.0

    @property
    def overall_health(self) -> str:
        """Overall model health assessment."""
        if self.critical_count > 0:
            return "CRITICAL"
        if self.error_count > 0:
            return "ERRORS_FOUND"
        if self.warning_count > 0:
            return "WARNINGS"
        return "CLEAN"

    def get_failures(self, min_severity: Severity = Severity.WARNING) -> List[CheckResult]:
        """Get all failures at or above a given severity."""
        severity_order = {
            Severity.INFO: 0, Severity.WARNING: 1,
            Severity.ERROR: 2, Severity.CRITICAL: 3,
        }
        min_level = severity_order.get(min_severity, 0)
        return [
            r for r in self.results
            if r.severity != Severity.PASS and severity_order.get(r.severity, 0) >= min_level
        ]

    def by_category(self) -> Dict[str, List[CheckResult]]:
        """Group results by check category."""
        grouped = {}
        for r in self.results:
            cat = r.category.value
            if cat not in grouped:
                grouped[cat] = []
            grouped[cat].append(r)
        return grouped

    def by_period(self) -> Dict[str, List[CheckResult]]:
        """Group results by period."""
        grouped = {}
        for r in self.results:
            p = r.period or "global"
            if p not in grouped:
                grouped[p] = []
            grouped[p].append(r)
        return grouped

    def summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        cat_summary = {}
        for cat, results in self.by_category().items():
            passes = sum(1 for r in results if r.severity == Severity.PASS)
            cat_summary[cat] = {
                "total": len(results),
                "passed": passes,
                "failed": len(results) - passes,
                "pass_rate": passes / len(results) if results else 0,
            }

        return {
            "company_name": self.model.company_name,
            "timestamp": self.timestamp,
            "overall_health": self.overall_health,
            "total_checks": self.total_checks,
            "passed": self.pass_count,
            "failed": self.fail_count,
            "pass_rate": round(self.pass_rate, 4),
            "by_severity": {
                "critical": self.critical_count,
                "error": self.error_count,
                "warning": self.warning_count,
                "info": sum(1 for r in self.results if r.severity == Severity.INFO),
                "pass": self.pass_count,
            },
            "by_category": cat_summary,
            "periods_analyzed": list(set(r.period for r in self.results if r.period)),
        }

    def to_json(self, indent: int = 2) -> str:
        """Full report as JSON."""
        return json.dumps({
            "summary": self.summary(),
            "check_metadata": self.check_metadata,
            "results": [r.to_dict() for r in self.results],
        }, indent=indent, default=str)

    def print_summary(self):
        """Print a formatted summary to console."""
        s = self.summary()
        print(f"\n{'='*70}")
        print(f"  FINANCIAL MODEL VERIFICATION REPORT")
        print(f"  Company: {s['company_name']}")
        print(f"  Timestamp: {s['timestamp']}")
        print(f"{'='*70}")
        print(f"\n  Overall Health: {s['overall_health']}")
        print(f"  Total Checks: {s['total_checks']}  |  "
              f"Passed: {s['passed']}  |  Failed: {s['failed']}  |  "
              f"Pass Rate: {s['pass_rate']:.1%}")
        print(f"\n  By Severity:")
        for sev, count in s['by_severity'].items():
            if count > 0:
                icon = {"critical": "🔴", "error": "🟠", "warning": "🟡", "info": "🔵", "pass": "🟢"}.get(sev, "")
                print(f"    {icon} {sev.upper()}: {count}")
        print(f"\n  By Category:")
        for cat, stats in s['by_category'].items():
            print(f"    {cat}: {stats['passed']}/{stats['total']} passed ({stats['pass_rate']:.0%})")

        failures = self.get_failures()
        if failures:
            print(f"\n  {'─'*66}")
            print(f"  FAILURES & WARNINGS ({len(failures)}):")
            for r in sorted(failures, key=lambda x: x.severity.value, reverse=True):
                icon = {"critical": "🔴", "error": "🟠", "warning": "🟡"}.get(r.severity.value, "⚪")
                print(f"    {icon} [{r.check_id}] {r.period}: {r.message}")
                if r.delta is not None:
                    print(f"       Δ={r.delta:.4f}" +
                          (f" ({r.delta_pct:.2%})" if r.delta_pct is not None else ""))
        print(f"\n{'='*70}\n")
