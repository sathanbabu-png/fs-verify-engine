"""
Single-Sheet Stacked Parser (v2)
Handles analyst models where IS, BS, CF are stacked vertically on one sheet.

Key design decisions:
  - Label column detected per-section (not globally) via text density analysis
  - Strict period regex: must look like FY2023, Q1-2025, CY2024E, or standalone 2024
  - Stop sections (DCF, Sensitivity, etc.) terminate parsing
  - Indented sub-labels (leading spaces) preserved for mapping
"""

import re
import openpyxl
from typing import Dict, List, Optional, Tuple, Any
from .models import (
    FinancialModel, IncomeStatement, BalanceSheet, CashFlowStatement
)
from .field_mapper import (
    FieldMapper, MappingConfig, MappingDiagnostics,
    load_mapping_config, normalize_signs
)


# ── Section detection ──

SECTION_PATTERNS = {
    'income_statement': [
        r'income\s*statement', r'profit\s*(?:&|and)?\s*loss', r'\bp\s*&?\s*l\b',
        r'statement\s*of\s*(?:profit|income|operations)',
    ],
    'balance_sheet': [
        r'balance\s*sheet', r'statement\s*of\s*(?:financial\s*)?position',
    ],
    'cash_flow': [
        r'cash\s*flow', r'statement\s*of\s*cash\s*flows?',
    ],
}

STOP_PATTERNS = [
    r'dcf\b', r'valuation\b', r'sensitivity', r'scenario\s*(?:assum|analy)',
    r'football\s*field', r'wacc\s*[↓↑]', r'comps?\s*(?:table|analy)',
    r'comparable', r'multiples', r'\blbo\b', r'monte\s*carlo',
]

SKIP_ROW_PATTERNS = [
    r'^assets?$', r'^equity\s*(?:&|and)\s*liabilities$',
    r'^(?:equity|liabilities)$', r'^current\s*(?:assets|liabilities)$',
    r'^non[\s-]*current\s*(?:assets|liabilities)$',
    r'^operating\s*activities$', r'^investing\s*activities$',
    r'^financing\s*activities$', r'^changes?\s*in\s*working\s*capital$',
    r'^total\s*income$', r'^total\s*expenses?$', r'^total\s*expenditure$',
]

# Strict period regex: FY2023, CY2024E, Q1-2025, H2-2024, or standalone 2024/2025E
PERIOD_RE = re.compile(
    r'^(?:FY|CY|Q[1-4][\s\-]?|H[12][\s\-]?)?\d{4}\s*[EePpFfAaBb]?$',
    re.IGNORECASE,
)


def _classify_row_text(text: str) -> Optional[str]:
    """Returns statement type if text is a section header, 'stop' if stop section, else None."""
    t = text.strip().lower()
    if not t or len(t) < 3:
        return None
    for p in STOP_PATTERNS:
        if re.search(p, t):
            return 'stop'
    for stmt_type, patterns in SECTION_PATTERNS.items():
        for p in patterns:
            if re.search(p, t):
                return stmt_type
    return None


def _should_skip_row(text: str) -> bool:
    t = text.strip().lower()
    for p in SKIP_ROW_PATTERNS:
        if re.match(p, t):
            return True
    return False


def _is_period(text: str) -> bool:
    """Strict check: is this string a financial period label?"""
    s = str(text).strip()
    return bool(PERIOD_RE.match(s))


def _detect_period_row(rows: List[list], start: int, end: int) -> Optional[int]:
    """Find the period header row within a range. Returns row index or None."""
    for i in range(start, min(end, len(rows))):
        row = rows[i]
        period_count = sum(1 for v in row if v is not None and _is_period(str(v)))
        if period_count >= 2:
            return i
    return None


def _extract_period_columns(row: list) -> Dict[str, int]:
    """Extract {period_label: col_index} from a header row."""
    result = {}
    for j, v in enumerate(row):
        if v is not None:
            s = str(v).strip()
            if _is_period(s) and s not in result:
                result[s] = j
    return result


def _detect_label_column(rows: List[list], start: int, end: int, period_cols: set) -> int:
    """
    Detect which column holds line item labels for a specific section.
    Ignores columns that are period data columns.
    Returns 0-based column index.
    """
    col_scores = {}
    for i in range(start, min(end, len(rows))):
        row = rows[i]
        for j, v in enumerate(row):
            if j in period_cols:
                continue
            if v is not None and isinstance(v, str):
                s = v.strip()
                if len(s) > 2 and not s.replace('.', '').replace('-', '').replace(',', '').isdigit():
                    col_scores[j] = col_scores.get(j, 0) + 1

    if not col_scores:
        return 0
    return max(col_scores, key=col_scores.get)


def _is_numeric(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return True
    try:
        s = str(v).strip()
        if s in ('', '-', '—', '–'):
            return False
        s = s.replace(',', '').replace('$', '').replace('₹', '').replace('%', '')
        if s.startswith('(') and s.endswith(')'):
            s = s[1:-1]
        float(s)
        return True
    except ValueError:
        return False


def _to_float(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ('-', '—', '–', 'N/A', '#N/A'):
        return 0.0
    neg = False
    if s.startswith('(') and s.endswith(')'):
        s = s[1:-1]
        neg = True
    s = s.replace(',', '').replace('$', '').replace('₹', '').replace('%', '').strip()
    if not s:
        return 0.0
    val = float(s)
    return -val if neg else val


STMT_CLASS = {
    'income_statement': IncomeStatement,
    'balance_sheet': BalanceSheet,
    'cash_flow': CashFlowStatement,
}
STMT_ATTR = {
    'income_statement': 'income_statements',
    'balance_sheet': 'balance_sheets',
    'cash_flow': 'cash_flows',
}


def parse_stacked_sheet(
    filepath: str,
    sheet_name: Optional[str] = None,
    mapping_config: Optional[str] = None,
) -> Tuple[FinancialModel, List[MappingDiagnostics]]:
    """
    Parse a single-sheet stacked financial model.

    Handles:
      - Section headers in any of the first 3 columns
      - Line item labels in a different column than headers
      - Indented sub-items with leading spaces
      - Stop sections (DCF, Sensitivity, Valuation)
      - Period headers like FY2023, Q1-2025, 2024E
    """
    wb = openpyxl.load_workbook(filepath, data_only=True)
    config = load_mapping_config(mapping_config)
    mapper = FieldMapper(config)

    ws = wb[sheet_name] if sheet_name else wb.active
    all_rows = [list(row) for row in ws.iter_rows(values_only=True)]

    if not all_rows:
        return FinancialModel(), []

    # ── Phase 1: Find section boundaries ──
    sections = []  # list of {stmt_type, header_idx, end_idx}
    current = None

    for i, row in enumerate(all_rows):
        for col in range(min(4, len(row))):
            v = row[col]
            if v is None or not isinstance(v, str):
                continue
            cls = _classify_row_text(v)
            if cls == 'stop':
                if current:
                    current['end_idx'] = i - 1
                    sections.append(current)
                    current = None
                # Mark everything from here as stopped — don't create new sections
                # until another financial section header is found
                break
            elif cls in STMT_CLASS:
                if current:
                    current['end_idx'] = i - 1
                    sections.append(current)
                current = {'stmt_type': cls, 'header_idx': i, 'end_idx': None}
                break

    if current:
        current['end_idx'] = len(all_rows) - 1
        sections.append(current)

    # ── Phase 2: Extract data per section ──
    model = FinancialModel()
    all_diagnostics = []
    all_periods_set = set()

    # Detect company name from early rows
    for row in all_rows[:5]:
        for cell in row:
            if cell and isinstance(cell, str) and '—' in cell:
                model.company_name = cell.split('—')[0].strip()
                break

    for sec in sections:
        stmt_type = sec['stmt_type']
        start = sec['header_idx']
        end = sec['end_idx'] or len(all_rows) - 1

        # Find the period header row
        period_row_idx = _detect_period_row(all_rows, start, min(start + 5, end + 1))
        if period_row_idx is None:
            continue

        period_col_map = _extract_period_columns(all_rows[period_row_idx])
        if not period_col_map:
            continue

        periods = list(period_col_map.keys())
        all_periods_set.update(periods)
        period_col_set = set(period_col_map.values())

        # Detect label column for THIS section's data rows
        data_start = period_row_idx + 1
        label_col = _detect_label_column(all_rows, data_start, end + 1, period_col_set)

        # Extract line items
        stmt_class = STMT_CLASS[stmt_type]
        statements = {p: stmt_class(period=p) for p in periods}
        input_field_names = []
        field_values = {}  # label -> {period -> value}

        for ri in range(data_start, end + 1):
            if ri >= len(all_rows):
                break
            row = all_rows[ri]

            # Get label — try label_col, then neighbors
            label = None
            for try_col in [label_col, label_col + 1, label_col - 1]:
                if 0 <= try_col < len(row) and try_col not in period_col_set:
                    v = row[try_col]
                    if v is not None and isinstance(v, str):
                        s = v.strip()
                        if len(s) > 1 and not s.replace('.', '').replace('-', '').replace(',', '').isdigit():
                            label = s
                            break

            if not label:
                continue

            # Stop if we hit another section or stop section
            if _classify_row_text(label) is not None:
                break

            # Skip sub-headers
            if _should_skip_row(label):
                continue

            # Skip balance check, EPS, and other computed rows
            label_lower = label.lower().strip()
            if any(skip in label_lower for skip in ['balance check', 'eps (']):
                continue

            input_field_names.append(label)
            field_values[label] = {}

            for period, col_idx in period_col_map.items():
                if col_idx < len(row):
                    field_values[label][period] = _to_float(row[col_idx])
                else:
                    field_values[label][period] = 0.0

        # Map fields
        field_mapping, diagnostics = mapper.map_fields(input_field_names, stmt_type)
        all_diagnostics.append(diagnostics)

        # Apply mapped values to statements
        for input_name, internal_field in field_mapping.items():
            for period in periods:
                val = field_values.get(input_name, {}).get(period, 0.0)
                if hasattr(statements[period], internal_field):
                    setattr(statements[period], internal_field, val)

        # Sign normalization
        if config.auto_sign_normalization:
            for period in periods:
                stmt = statements[period]
                data = {k: v for k, v in vars(stmt).items()
                        if k != 'period' and isinstance(v, (int, float))}
                normalized = normalize_signs(data, stmt_type, config)
                for k, v in normalized.items():
                    setattr(stmt, k, v)

        setattr(model, STMT_ATTR[stmt_type], statements)

    # Set periods
    all_periods = sorted(all_periods_set)
    model.periods = all_periods
    model.historical_periods = [p for p in all_periods if not re.search(r'[EePp]$', p)]
    model.projected_periods = [p for p in all_periods if re.search(r'[EePp]$', p)]

    return model, all_diagnostics
