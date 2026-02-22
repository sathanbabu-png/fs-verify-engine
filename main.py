#!/usr/bin/env python3
"""
Financial Statement Verification Engine — Main Entry Point

Usage:
    # Run verification with default mapping
    python main.py model.json --output-json report.json --output-xlsx report.xlsx

    # Run with custom field mapping
    python main.py model.xlsx --mapping my_mapping.yaml

    # Generate a mapping template from your model's field names
    python main.py model.xlsx --generate-mapping custom_mapping.yaml

    # Validate a mapping config
    python main.py --validate-mapping my_mapping.yaml

    # Show mapping diagnostics (dry run, no verification)
    python main.py model.xlsx --diagnose-mapping
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import (
    VerificationEngine, auto_parse, export_json, export_excel,
    validate_mapping_config
)
from engine.field_mapper import FieldMapper, load_mapping_config, generate_mapping_template


def print_diagnostics(diagnostics):
    """Print field mapping diagnostics."""
    print(f"\n{'─'*60}")
    print("  FIELD MAPPING DIAGNOSTICS")
    print(f"{'─'*60}")
    for diag in diagnostics:
        print(f"\n  {diag.statement_type.upper().replace('_', ' ')}")
        print(f"  Mapped: {diag.mapped_count}/{diag.total_input_fields} fields")
        print(f"    Exact: {diag.exact_matches}  |  Alias: {diag.alias_matches}  |  Fuzzy: {diag.fuzzy_matches}")
        if diag.unmapped_fields:
            print(f"    Unmapped ({diag.unmapped_count}):")
            for f in diag.unmapped_fields:
                print(f"      ✗ {f}")
        if diag.warnings:
            print(f"    Warnings:")
            for w in diag.warnings:
                print(f"      ⚠ {w}")
    print(f"\n{'─'*60}\n")


def cmd_run(args):
    """Main verification run."""
    print(f"Parsing: {args.input}")
    model, diagnostics = auto_parse(args.input, args.mapping)
    print(f"Loaded: {model.company_name} | {len(model.periods)} periods | "
          f"IS={len(model.income_statements)} BS={len(model.balance_sheets)} CF={len(model.cash_flows)}")

    if args.diagnose_mapping:
        print_diagnostics(diagnostics)
        return 0

    # Print mapping summary
    for diag in diagnostics:
        mapped = diag.mapped_count
        total = diag.total_input_fields
        fuzzy = diag.fuzzy_matches
        unmapped = diag.unmapped_count
        stmt = diag.statement_type.replace('_', ' ').title()
        status = "✓" if unmapped == 0 else "⚠"
        print(f"  {status} {stmt}: {mapped}/{total} mapped"
              + (f" ({fuzzy} fuzzy)" if fuzzy else "")
              + (f" [{unmapped} unmapped]" if unmapped else ""))

    if any(d.warnings for d in diagnostics):
        print("\n  Mapping warnings (use --diagnose-mapping for details)")

    # Run engine
    engine = VerificationEngine(
        tolerance_abs=args.tolerance_abs,
        tolerance_pct=args.tolerance_pct,
    )
    report = engine.run(model)

    if not args.quiet:
        report.print_summary()

    if args.output_json:
        export_json(report, args.output_json)
        print(f"JSON report saved: {args.output_json}")

    if args.output_xlsx:
        export_excel(report, args.output_xlsx)
        print(f"Excel report saved: {args.output_xlsx}")

    if report.overall_health == "CRITICAL":
        return 2
    elif report.overall_health == "ERRORS_FOUND":
        return 1
    return 0


def cmd_generate_mapping(args):
    """Generate a mapping template from an input file."""
    print(f"Analyzing field names in: {args.input}")
    model, diagnostics = auto_parse(args.input)
    print_diagnostics(diagnostics)

    # Collect input field names by statement type
    # Re-read to get raw field names (diagnostics have them)
    input_fields = {}
    for diag in diagnostics:
        all_fields = [r.input_name for r in diag.results]
        input_fields[diag.statement_type] = all_fields

    output_path = args.generate_mapping
    generate_mapping_template(input_fields, output_path)
    print(f"Mapping template saved: {output_path}")
    print("Edit this file to fix unmapped fields and adjust aliases.")
    return 0


def cmd_validate_mapping(args):
    """Validate a mapping config file."""
    print(f"Validating: {args.validate_mapping}")
    issues = validate_mapping_config(args.validate_mapping)
    for issue in issues:
        print(f"  {issue}")
    return 0 if any("OK" in i for i in issues) else 1


def main():
    parser = argparse.ArgumentParser(
        description="3-Statement Financial Model Verification Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s model.json                                  # Basic run
  %(prog)s model.xlsx --mapping custom.yaml            # Custom mapping
  %(prog)s model.xlsx --diagnose-mapping               # Dry run, show mapping
  %(prog)s model.xlsx --generate-mapping custom.yaml   # Generate template
  %(prog)s --validate-mapping custom.yaml              # Validate config
        """
    )
    parser.add_argument("input", nargs='?', help="Input file (JSON, XLSX) or directory (CSV)")

    # Mapping options
    mapping_group = parser.add_argument_group("Field Mapping")
    mapping_group.add_argument(
        "--mapping", metavar="YAML",
        help="Path to custom field mapping YAML config"
    )
    mapping_group.add_argument(
        "--diagnose-mapping", action="store_true",
        help="Show field mapping diagnostics only (no verification)"
    )
    mapping_group.add_argument(
        "--generate-mapping", metavar="OUTPUT_YAML",
        help="Generate a mapping template from the input file's field names"
    )
    mapping_group.add_argument(
        "--validate-mapping", metavar="YAML",
        help="Validate a mapping config file"
    )

    # Output options
    output_group = parser.add_argument_group("Output")
    output_group.add_argument("--output-json", help="Path for JSON report output")
    output_group.add_argument("--output-xlsx", help="Path for Excel report output")

    # Engine options
    engine_group = parser.add_argument_group("Engine")
    engine_group.add_argument(
        "--tolerance-abs", type=float, default=0.5,
        help="Absolute tolerance for checks (default: 0.5)"
    )
    engine_group.add_argument(
        "--tolerance-pct", type=float, default=0.001,
        help="Relative tolerance for checks (default: 0.001)"
    )
    engine_group.add_argument("--quiet", action="store_true", help="Suppress console output")

    args = parser.parse_args()

    # Route to appropriate command
    if args.validate_mapping:
        return cmd_validate_mapping(args)

    if not args.input:
        parser.error("Input file is required (unless using --validate-mapping)")

    if args.generate_mapping:
        return cmd_generate_mapping(args)

    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
