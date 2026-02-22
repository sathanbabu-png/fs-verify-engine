"""
Configurable Field Mapping Engine
Resolves arbitrary input field names to internal schema fields using:
  1. Exact match (normalized)
  2. Alias match
  3. Fuzzy match (Levenshtein-based, configurable threshold)

Also handles sign normalization and provides diagnostics for unmapped fields.
"""

import re
import os
import yaml
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from difflib import SequenceMatcher


# ============================================================================
# Normalization
# ============================================================================

def normalize(name: str) -> str:
    """
    Normalize a field name for comparison.
    - Lowercase
    - Strip leading/trailing whitespace
    - Replace underscores, hyphens, dots, slashes with spaces
    - Collapse multiple spaces
    - Remove parentheses and their contents like '(net)' or '($M)'
    - Strip common prefixes: 'total ', 'net ', 'less '
    """
    s = name.lower().strip()
    # Remove content in parentheses
    s = re.sub(r'\([^)]*\)', '', s)
    # Replace separators with spaces
    s = re.sub(r'[_\-./\\]', ' ', s)
    # Remove special chars except & (used in SG&A, R&D, D&A)
    s = re.sub(r'[^a-z0-9& ]', '', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_aggressive(name: str) -> str:
    """
    More aggressive normalization for fuzzy matching.
    Strips common financial prefixes and filler words.
    """
    s = normalize(name)
    # Remove common filler words
    fillers = ['total', 'net', 'less', 'gross', 'of', 'the', 'and', 'in', 'from', 'for', 'to', 'at', 'on']
    words = s.split()
    words = [w for w in words if w not in fillers]
    return ' '.join(words)


# ============================================================================
# Mapping Config Loader
# ============================================================================

@dataclass
class MappingConfig:
    """Loaded and indexed mapping configuration."""
    settings: Dict[str, Any] = field(default_factory=dict)
    # statement_type -> internal_field -> list of normalized aliases
    alias_index: Dict[str, Dict[str, List[str]]] = field(default_factory=dict)
    # Reverse index: statement_type -> normalized_alias -> internal_field
    reverse_index: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # Raw config for reference
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def fuzzy_threshold(self) -> int:
        return self.settings.get('fuzzy_threshold', 85)

    @property
    def unmapped_fields_policy(self) -> str:
        return self.settings.get('unmapped_fields', 'warn')

    @property
    def auto_sign_normalization(self) -> bool:
        return self.settings.get('auto_sign_normalization', True)


def load_mapping_config(config_path: Optional[str] = None) -> MappingConfig:
    """
    Load mapping configuration from YAML file.
    Falls back to default_mapping.yaml if no path provided.
    """
    if config_path is None:
        # Look in engine/config, then project root config/
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'default_mapping.yaml'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'default_mapping.yaml'),
        ]
        config_path = next((c for c in candidates if os.path.exists(c)), candidates[0])

    with open(config_path, 'r') as f:
        raw = yaml.safe_load(f)

    config = MappingConfig(
        settings=raw.get('settings', {}),
        raw=raw,
    )

    # Build indexes for each statement type
    for stmt_type in ['income_statement', 'balance_sheet', 'cash_flow']:
        stmt_mappings = raw.get(stmt_type, {})
        config.alias_index[stmt_type] = {}
        config.reverse_index[stmt_type] = {}

        for internal_field, field_def in stmt_mappings.items():
            aliases = field_def.get('aliases', [])
            normalized_aliases = [normalize(a) for a in aliases]
            # Also add the internal field name itself as an alias
            normalized_aliases.append(normalize(internal_field))
            # Deduplicate
            normalized_aliases = list(set(normalized_aliases))

            config.alias_index[stmt_type][internal_field] = normalized_aliases

            for na in normalized_aliases:
                if na in config.reverse_index[stmt_type]:
                    # Collision — first mapping wins, log warning
                    existing = config.reverse_index[stmt_type][na]
                    if existing != internal_field:
                        print(f"  [MAPPING WARN] Alias '{na}' maps to both "
                              f"'{existing}' and '{internal_field}' in {stmt_type}. "
                              f"Keeping '{existing}'.")
                else:
                    config.reverse_index[stmt_type][na] = internal_field

    return config


def merge_mapping_configs(base: MappingConfig, override: MappingConfig) -> MappingConfig:
    """
    Merge two configs: override extends and overrides base.
    Useful for layering a custom config on top of defaults.
    """
    merged = MappingConfig(
        settings={**base.settings, **override.settings},
        raw={**base.raw},
    )

    for stmt_type in ['income_statement', 'balance_sheet', 'cash_flow']:
        merged.alias_index[stmt_type] = dict(base.alias_index.get(stmt_type, {}))
        merged.reverse_index[stmt_type] = dict(base.reverse_index.get(stmt_type, {}))

        # Overlay overrides
        for internal_field, aliases in override.alias_index.get(stmt_type, {}).items():
            if internal_field in merged.alias_index[stmt_type]:
                # Extend existing aliases
                existing = set(merged.alias_index[stmt_type][internal_field])
                existing.update(aliases)
                merged.alias_index[stmt_type][internal_field] = list(existing)
            else:
                merged.alias_index[stmt_type][internal_field] = aliases

            for na in aliases:
                merged.reverse_index[stmt_type][na] = internal_field

    return merged


# ============================================================================
# Field Mapper
# ============================================================================

@dataclass
class MappingResult:
    """Result of a single field mapping attempt."""
    input_name: str
    normalized_name: str
    internal_field: Optional[str]
    match_type: str  # "exact", "alias", "fuzzy", "unmapped"
    confidence: float  # 0.0 - 1.0
    fuzzy_candidates: List[Tuple[str, float]] = field(default_factory=list)


@dataclass
class MappingDiagnostics:
    """Diagnostics from a complete mapping operation."""
    statement_type: str
    total_input_fields: int
    mapped_count: int
    unmapped_count: int
    exact_matches: int
    alias_matches: int
    fuzzy_matches: int
    results: List[MappingResult] = field(default_factory=list)
    unmapped_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"  {self.statement_type}: {self.mapped_count}/{self.total_input_fields} mapped "
            f"(exact={self.exact_matches}, alias={self.alias_matches}, fuzzy={self.fuzzy_matches})",
        ]
        if self.unmapped_fields:
            lines.append(f"    Unmapped: {', '.join(self.unmapped_fields)}")
        for w in self.warnings:
            lines.append(f"    ⚠ {w}")
        return '\n'.join(lines)


class FieldMapper:
    """
    Maps input field names to internal schema fields using configurable rules.
    """

    def __init__(self, config: Optional[MappingConfig] = None):
        self.config = config or load_mapping_config()

    def resolve_field(
        self,
        input_name: str,
        statement_type: str,
    ) -> MappingResult:
        """
        Resolve a single input field name to an internal field.

        Args:
            input_name: The raw field name from the input file
            statement_type: One of 'income_statement', 'balance_sheet', 'cash_flow'

        Returns:
            MappingResult with the resolved field or None if unmapped
        """
        norm = normalize(input_name)
        reverse = self.config.reverse_index.get(statement_type, {})

        # 1. Exact match on normalized name
        if norm in reverse:
            return MappingResult(
                input_name=input_name,
                normalized_name=norm,
                internal_field=reverse[norm],
                match_type="exact",
                confidence=1.0,
            )

        # 2. Try with aggressive normalization
        norm_agg = normalize_aggressive(input_name)
        if norm_agg in reverse:
            return MappingResult(
                input_name=input_name,
                normalized_name=norm,
                internal_field=reverse[norm_agg],
                match_type="alias",
                confidence=0.95,
            )

        # 3. Substring containment — check if any alias is contained in input or vice versa
        for alias, field_name in reverse.items():
            if len(alias) > 3 and (alias in norm or norm in alias):
                return MappingResult(
                    input_name=input_name,
                    normalized_name=norm,
                    internal_field=field_name,
                    match_type="alias",
                    confidence=0.85,
                )

        # 4. Fuzzy matching
        threshold = self.config.fuzzy_threshold
        if threshold > 0:
            candidates = []
            for alias, field_name in reverse.items():
                ratio = SequenceMatcher(None, norm, alias).ratio() * 100
                if ratio >= threshold:
                    candidates.append((field_name, alias, ratio))

            if candidates:
                # Sort by ratio descending
                candidates.sort(key=lambda x: x[2], reverse=True)
                best_field, best_alias, best_ratio = candidates[0]

                # Check for ambiguity — if top 2 map to different fields with close scores
                fuzzy_cands = [(c[1], c[2]) for c in candidates[:3]]
                ambiguous = (
                    len(candidates) > 1 and
                    candidates[0][0] != candidates[1][0] and
                    candidates[0][2] - candidates[1][2] < 5
                )

                if ambiguous:
                    return MappingResult(
                        input_name=input_name,
                        normalized_name=norm,
                        internal_field=None,
                        match_type="unmapped",
                        confidence=0.0,
                        fuzzy_candidates=fuzzy_cands,
                    )

                return MappingResult(
                    input_name=input_name,
                    normalized_name=norm,
                    internal_field=best_field,
                    match_type="fuzzy",
                    confidence=best_ratio / 100.0,
                    fuzzy_candidates=fuzzy_cands,
                )

        # 5. Unmapped
        return MappingResult(
            input_name=input_name,
            normalized_name=norm,
            internal_field=None,
            match_type="unmapped",
            confidence=0.0,
        )

    def map_fields(
        self,
        input_fields: List[str],
        statement_type: str,
    ) -> Tuple[Dict[str, str], MappingDiagnostics]:
        """
        Map a list of input field names to internal fields.

        Args:
            input_fields: List of raw field names from input file
            statement_type: One of 'income_statement', 'balance_sheet', 'cash_flow'

        Returns:
            Tuple of:
              - Dict mapping input_name -> internal_field (only for mapped fields)
              - MappingDiagnostics with full details
        """
        mapping = {}
        diag = MappingDiagnostics(
            statement_type=statement_type,
            total_input_fields=len(input_fields),
            mapped_count=0,
            unmapped_count=0,
            exact_matches=0,
            alias_matches=0,
            fuzzy_matches=0,
        )

        used_internal_fields = set()

        for input_name in input_fields:
            if not input_name or not input_name.strip():
                continue

            result = self.resolve_field(input_name, statement_type)
            diag.results.append(result)

            if result.internal_field:
                # Prevent duplicate mapping to same internal field
                if result.internal_field in used_internal_fields:
                    diag.warnings.append(
                        f"'{input_name}' maps to '{result.internal_field}' "
                        f"which is already mapped. Skipping duplicate."
                    )
                    continue

                mapping[input_name] = result.internal_field
                used_internal_fields.add(result.internal_field)
                diag.mapped_count += 1

                if result.match_type == "exact":
                    diag.exact_matches += 1
                elif result.match_type == "alias":
                    diag.alias_matches += 1
                elif result.match_type == "fuzzy":
                    diag.fuzzy_matches += 1
                    diag.warnings.append(
                        f"Fuzzy match: '{input_name}' → '{result.internal_field}' "
                        f"(confidence={result.confidence:.0%})"
                    )
            else:
                diag.unmapped_count += 1
                diag.unmapped_fields.append(input_name)
                if result.fuzzy_candidates:
                    diag.warnings.append(
                        f"Ambiguous match for '{input_name}': "
                        f"{', '.join(f'{a} ({s:.0f}%)' for a, s in result.fuzzy_candidates)}"
                    )

        return mapping, diag

    def get_available_fields(self, statement_type: str) -> List[str]:
        """Return all internal fields defined for a statement type."""
        return list(self.config.alias_index.get(statement_type, {}).keys())

    def get_aliases(self, statement_type: str, internal_field: str) -> List[str]:
        """Return all aliases for a specific internal field."""
        return self.config.alias_index.get(statement_type, {}).get(internal_field, [])


# ============================================================================
# Sign Normalization
# ============================================================================

# Fields that should be positive in the internal representation
POSITIVE_FIELDS = {
    'income_statement': {
        'revenue', 'cogs', 'gross_profit', 'sga', 'rd', 'depreciation',
        'amortization', 'other_opex', 'total_opex', 'interest_expense',
        'tax_expense',
    },
    'balance_sheet': {
        'cash', 'accounts_receivable', 'inventory', 'total_current_assets',
        'ppe_gross', 'accumulated_depreciation', 'ppe_net', 'total_assets',
        'accounts_payable', 'total_current_liabilities', 'long_term_debt',
        'total_liabilities',
    },
    'cash_flow': {
        'depreciation_amortization', 'stock_based_compensation',
    },
}

# Fields that are typically negative (outflows) on the cash flow statement
NEGATIVE_CF_FIELDS = {
    'capex', 'acquisitions', 'purchase_of_investments', 'debt_repayment',
    'share_repurchases', 'dividends_paid',
}


def normalize_signs(
    data: Dict[str, float],
    statement_type: str,
    config: MappingConfig,
) -> Dict[str, float]:
    """
    Normalize signs based on accounting conventions.
    E.g., COGS should be positive, CapEx should be negative on CF.
    Only applied if auto_sign_normalization is enabled.
    """
    if not config.auto_sign_normalization:
        return data

    result = dict(data)

    if statement_type == 'cash_flow':
        for field_name in NEGATIVE_CF_FIELDS:
            if field_name in result and result[field_name] > 0:
                result[field_name] = -result[field_name]

    return result


# ============================================================================
# Config Generator / Validator
# ============================================================================

def generate_mapping_template(
    input_fields: Dict[str, List[str]],
    output_path: str,
):
    """
    Generate a YAML mapping template from actual input field names.
    Useful for bootstrapping a custom config from an analyst's model.

    Args:
        input_fields: Dict of statement_type -> list of field names from the file
        output_path: Where to save the generated YAML
    """
    mapper = FieldMapper()
    template = {
        'settings': {
            'fuzzy_threshold': 85,
            'header_row': True,
            'unmapped_fields': 'warn',
            'auto_sign_normalization': True,
        }
    }

    for stmt_type, fields in input_fields.items():
        mapping, diag = mapper.map_fields(fields, stmt_type)
        stmt_config = {}

        for input_name in fields:
            if not input_name or not input_name.strip():
                continue
            result = mapper.resolve_field(input_name, stmt_type)
            if result.internal_field:
                if result.internal_field not in stmt_config:
                    stmt_config[result.internal_field] = {'aliases': []}
                stmt_config[result.internal_field]['aliases'].append(input_name)
            else:
                # Add as commented suggestion
                stub_key = normalize(input_name).replace(' ', '_')
                stmt_config[f'# UNMAPPED: {stub_key}'] = {
                    'aliases': [input_name],
                    '_note': 'Map this to an internal field name or remove'
                }

        template[stmt_type] = stmt_config

    with open(output_path, 'w') as f:
        yaml.dump(template, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    return output_path


def validate_mapping_config(config_path: str) -> List[str]:
    """
    Validate a mapping config file for common issues.
    Returns list of warning/error messages.
    """
    issues = []

    try:
        config = load_mapping_config(config_path)
    except Exception as e:
        return [f"ERROR: Failed to load config: {e}"]

    for stmt_type in ['income_statement', 'balance_sheet', 'cash_flow']:
        aliases_seen = {}
        for field_name, aliases in config.alias_index.get(stmt_type, {}).items():
            if not aliases:
                issues.append(f"WARNING: {stmt_type}.{field_name} has no aliases defined")
            for alias in aliases:
                if alias in aliases_seen:
                    issues.append(
                        f"WARNING: Alias '{alias}' in {stmt_type} maps to both "
                        f"'{aliases_seen[alias]}' and '{field_name}'"
                    )
                aliases_seen[alias] = field_name

    # Check for critical missing fields
    critical_fields = {
        'income_statement': ['revenue', 'net_income', 'ebit'],
        'balance_sheet': ['total_assets', 'total_equity', 'total_liabilities_and_equity', 'cash'],
        'cash_flow': ['cash_from_operations', 'net_change_in_cash', 'ending_cash'],
    }
    for stmt_type, required in critical_fields.items():
        defined = set(config.alias_index.get(stmt_type, {}).keys())
        for req in required:
            if req not in defined:
                issues.append(f"WARNING: Critical field '{req}' not defined in {stmt_type}")

    if not issues:
        issues.append("OK: Config validation passed with no issues.")

    return issues
