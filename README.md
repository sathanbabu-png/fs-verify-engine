# FS Verify — Financial Statement Verification Engine

A Streamlit-powered dashboard that runs **32 automated checks** on 3-statement financial models to catch arithmetic errors, broken linkages, and unreasonable assumptions.

## What It Checks

| Category | Checks | Validates |
|:---|:---:|:---|
| **Structural Integrity** | 15 | Intra-statement arithmetic — BS balances, IS build-up, CF reconciliation |
| **Cross-Statement Linkage** | 10 | NI linkage, RE rollforward, cash continuity, PPE/debt rollforwards, WC deltas |
| **Reasonableness & Sanity** | 7 | Margin drift, revenue growth, leverage ratios, DSO/DIO/DPO, negative balances |

## Supported Input Formats

- **JSON** — nested structure with `income_statements`, `balance_sheets`, `cash_flows`
- **Excel (.xlsx/.xlsm)** — sheets named `Income Statement`, `Balance Sheet`, `Cash Flow` (+ common variants)
- **CSV** — separate files: `income_statement.csv`, `balance_sheet.csv`, `cash_flow.csv`

## Quick Start

### Streamlit Dashboard

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

### CLI

```bash
# Run verification
python main.py model.json --output-json report.json --output-xlsx report.xlsx

# Run with custom field mapping
python main.py model.xlsx --mapping my_mapping.yaml

# Generate a mapping template from your model
python main.py model.xlsx --generate-mapping custom_mapping.yaml

# Show mapping diagnostics
python main.py model.xlsx --diagnose-mapping
```

## Dashboard Features

- **Overview** — KPI metrics, severity distribution (donut chart), category breakdown (stacked bar)
- **Check Results** — filterable table by severity, category, period, and free-text search
- **Field Mapping** — diagnostics showing how input fields map to the engine's schema (exact, alias, fuzzy, unmapped)
- **Period Analysis** — heatmap of check results across periods with summary table
- **Export** — download reports in JSON, Excel, or CSV

## Configuration

Engine tolerances can be adjusted in the sidebar:

- **Absolute tolerance** — max difference before flagging (default: 0.5, in model units)
- **Relative tolerance** — max relative difference (default: 0.1%)

Custom field mappings can be provided via YAML. See `config/default_mapping.yaml` for the default configuration.

## Project Structure

```
├── streamlit_app.py          # Streamlit dashboard
├── main.py                   # CLI entry point
├── requirements.txt          # Python dependencies
├── config/
│   └── default_mapping.yaml  # Default field name mappings
├── engine/
│   ├── __init__.py
│   ├── engine.py             # Core verification engine
│   ├── models.py             # Data models (FinancialModel, CheckResult, etc.)
│   ├── parsers.py            # JSON/Excel/CSV parsers
│   ├── stacked_parser.py     # Stacked Excel sheet parser
│   ├── field_mapper.py       # Fuzzy field name matching
│   ├── reporter.py           # JSON & Excel report export
│   └── checks/
│       ├── base.py           # Base check class
│       ├── structural.py     # Balance sheet, IS, CF arithmetic
│       ├── cross_statement.py# Cross-statement linkage checks
│       └── reasonableness.py # Ratio & sanity checks
└── sample_data/
    └── acme_corp.json        # Demo model with intentional errors
```
