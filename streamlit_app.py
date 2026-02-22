"""
Financial Statement Verification Engine — Streamlit Dashboard

Run:  streamlit run streamlit_app.py
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import json
import os
import sys
import tempfile
import io
from datetime import datetime

# ── Path setup ──
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import (
    VerificationEngine, VerificationReport,
    auto_parse, export_json, export_excel,
    FinancialModel, Severity, CheckCategory,
)
from engine.field_mapper import (
    FieldMapper, load_mapping_config, validate_mapping_config,
)

# ============================================================================
# Page Config
# ============================================================================

st.set_page_config(
    page_title="FS Verify — 3-Statement Model Verification",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# Custom CSS
# ============================================================================

st.markdown("""
<style>
    /* Global */
    .block-container { padding-top: 2rem; }
    
    /* Metric cards */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #0f1419 0%, #1a1f2e 100%);
        border: 1px solid #2a2f3e;
        border-radius: 10px;
        padding: 16px 20px;
    }
    div[data-testid="stMetric"] label {
        color: #8892a4 !important;
        font-size: 0.75rem !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    
    /* Severity badges */
    .sev-critical { background: #dc2626; color: white; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 0.75rem; }
    .sev-error { background: #ea580c; color: white; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 0.75rem; }
    .sev-warning { background: #ca8a04; color: white; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 0.75rem; }
    .sev-pass { background: #16a34a; color: white; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 0.75rem; }
    .sev-info { background: #2563eb; color: white; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 0.75rem; }
    
    /* Health badge */
    .health-clean { background: #059669; color: white; padding: 6px 20px; border-radius: 6px; font-weight: 700; font-size: 1rem; letter-spacing: 0.05em; }
    .health-warnings { background: #d97706; color: white; padding: 6px 20px; border-radius: 6px; font-weight: 700; font-size: 1rem; letter-spacing: 0.05em; }
    .health-errors { background: #ea580c; color: white; padding: 6px 20px; border-radius: 6px; font-weight: 700; font-size: 1rem; letter-spacing: 0.05em; }
    .health-critical { background: #dc2626; color: white; padding: 6px 20px; border-radius: 6px; font-weight: 700; font-size: 1rem; letter-spacing: 0.05em; }
    
    /* Section headers */
    .section-header {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #6b7280;
        border-bottom: 1px solid #2a2f3e;
        padding-bottom: 8px;
        margin-bottom: 16px;
        margin-top: 24px;
    }
    
    /* Dataframe styling */
    .stDataFrame { border-radius: 8px; overflow: hidden; }
    
    /* Sidebar */
    section[data-testid="stSidebar"] > div { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# Helpers
# ============================================================================

SEVERITY_COLORS = {
    "critical": "#dc2626",
    "error": "#ea580c",
    "warning": "#ca8a04",
    "info": "#2563eb",
    "pass": "#16a34a",
}

SEVERITY_ORDER = {"critical": 4, "error": 3, "warning": 2, "info": 1, "pass": 0}

HEALTH_CSS = {
    "CLEAN": "health-clean",
    "WARNINGS": "health-warnings",
    "ERRORS_FOUND": "health-errors",
    "CRITICAL": "health-critical",
}

CATEGORY_LABELS = {
    "structural": "Structural Integrity",
    "cross_statement": "Cross-Statement Linkage",
    "reasonableness": "Reasonableness & Sanity",
    "circular": "Circular Reference",
}


def sev_badge(severity: str) -> str:
    return f'<span class="sev-{severity}">{severity.upper()}</span>'


def health_badge(health: str) -> str:
    css = HEALTH_CSS.get(health, "health-critical")
    label = health.replace("_", " ")
    return f'<span class="{css}">{label}</span>'


def results_to_df(results: list) -> pd.DataFrame:
    rows = []
    for r in results:
        rows.append({
            "Check ID": r.check_id,
            "Check Name": r.check_name,
            "Category": r.category.value,
            "Period": r.period or "—",
            "Severity": r.severity.value,
            "Message": r.message,
            "Expected": r.expected_value,
            "Actual": r.actual_value,
            "Delta": r.delta,
            "Delta %": f"{r.delta_pct:.4%}" if r.delta_pct is not None else None,
        })
    return pd.DataFrame(rows)


def save_uploaded_file(uploaded_file) -> str:
    """Save uploaded file to temp dir and return path."""
    suffix = os.path.splitext(uploaded_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(uploaded_file.getvalue())
        return f.name


@st.cache_data
def run_verification(file_bytes: bytes, filename: str, mapping_bytes,
                     tolerance_abs: float, tolerance_pct: float):
    """Run the verification pipeline (cached)."""
    suffix = os.path.splitext(filename)[1]

    # Save input file
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(file_bytes)
        input_path = f.name

    # Save mapping config if provided
    mapping_path = None
    if mapping_bytes:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".yaml", mode="wb") as f:
            f.write(mapping_bytes)
            mapping_path = f.name

    try:
        model, diagnostics = auto_parse(input_path, mapping_path)
        engine = VerificationEngine(
            tolerance_abs=tolerance_abs,
            tolerance_pct=tolerance_pct,
        )
        report = engine.run(model)
        return model, diagnostics, report, None
    except Exception as e:
        return None, None, None, str(e)
    finally:
        try:
            os.unlink(input_path)
        except (PermissionError, OSError):
            pass
        if mapping_path:
            try:
                os.unlink(mapping_path)
            except (PermissionError, OSError):
                pass


# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.markdown("## 📊 FS Verify")
    st.caption("3-Statement Model Verification Engine")
    st.divider()

    # File Upload
    st.markdown("### Upload Model")
    uploaded_file = st.file_uploader(
        "Financial model file",
        type=["json", "xlsx", "xlsm", "csv"],
        help="Upload your 3-statement model in JSON, Excel, or CSV format.",
    )

    # Mapping Config
    with st.expander("⚙️ Custom Field Mapping", expanded=False):
        mapping_file = st.file_uploader(
            "Mapping YAML (optional)",
            type=["yaml", "yml"],
            help="Upload a custom field mapping config. Leave empty to use defaults.",
        )
        st.caption(
            "Use `--generate-mapping` from CLI to create a template, "
            "or edit `config/default_mapping.yaml`."
        )

    # Engine Settings
    with st.expander("🔧 Engine Settings", expanded=False):
        tolerance_abs = st.number_input(
            "Absolute tolerance",
            min_value=0.001, max_value=100.0, value=0.5, step=0.1,
            help="Maximum absolute difference before flagging (in model units, e.g. $M)",
        )
        tolerance_pct = st.number_input(
            "Relative tolerance",
            min_value=0.0001, max_value=0.1, value=0.001, step=0.0005,
            format="%.4f",
            help="Maximum relative difference (0.001 = 0.1%)",
        )

    st.divider()

    # Sample Data
    if st.button("📁 Load Sample Data", use_container_width=True):
        sample_path = os.path.join(os.path.dirname(__file__), "sample_data", "acme_corp.json")
        if os.path.exists(sample_path):
            with open(sample_path, "rb") as f:
                st.session_state["sample_bytes"] = f.read()
                st.session_state["sample_name"] = "acme_corp.json"
            st.rerun()

# ============================================================================
# Main Content
# ============================================================================

# Determine input source
file_bytes = None
file_name = None

if uploaded_file:
    file_bytes = uploaded_file.getvalue()
    file_name = uploaded_file.name
elif "sample_bytes" in st.session_state:
    file_bytes = st.session_state["sample_bytes"]
    file_name = st.session_state["sample_name"]

if file_bytes is None:
    # Landing page
    st.markdown("""
    # 📊 Financial Statement Verification Engine
    
    Upload a 3-statement financial model to run **32 automated checks** across three categories:
    
    | Category | Checks | Validates |
    |:---|:---:|:---|
    | **Structural Integrity** | 15 | Intra-statement arithmetic: BS balances, IS build-up, CF reconciliation |
    | **Cross-Statement Linkage** | 10 | NI linkage, RE rollforward, cash continuity, PPE/debt rollforwards, WC deltas |
    | **Reasonableness & Sanity** | 7 | Margin drift, revenue growth, leverage ratios, DSO/DIO/DPO, negative balances |
    
    ### Supported Formats
    - **JSON** — nested structure with `income_statements`, `balance_sheets`, `cash_flows`
    - **Excel (.xlsx)** — sheets named `Income Statement`, `Balance Sheet`, `Cash Flow` (+ common variants)
    - **CSV** — directory with `income_statement.csv`, `balance_sheet.csv`, `cash_flow.csv`
    
    ### Getting Started
    1. **Upload** your model using the sidebar  
    2. **Or** click **Load Sample Data** to try with a demo model  
    3. View verification results, drill into failures, and download reports
    """)
    st.stop()

# ── Run Verification ──
mapping_bytes = mapping_file.getvalue() if mapping_file else None

model, diagnostics, report, error = run_verification(
    file_bytes, file_name, mapping_bytes, tolerance_abs, tolerance_pct,
)

if error:
    st.error(f"**Parsing Error:** {error}")
    st.info("Check that your file format matches the expected layout. Use `--diagnose-mapping` from CLI for details.")
    st.stop()

summary = report.summary()

# ============================================================================
# Tab Layout
# ============================================================================

tab_overview, tab_results, tab_mapping, tab_periods, tab_export = st.tabs([
    "📊 Overview", "🔍 Check Results", "🔗 Field Mapping", "📅 Period Analysis", "📥 Export"
])

# ============================================================================
# TAB 1: Overview
# ============================================================================

with tab_overview:
    # Header row
    col_title, col_health = st.columns([3, 1])
    with col_title:
        st.markdown(f"## {summary['company_name']}")
        st.caption(f"Verified: {summary['timestamp']}  ·  {len(summary['periods_analyzed'])} periods  ·  Tolerance: ±{tolerance_abs}")
    with col_health:
        st.markdown(f"<div style='text-align:right; padding-top:16px;'>{health_badge(summary['overall_health'])}</div>",
                    unsafe_allow_html=True)

    st.divider()

    # KPI Row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Checks", summary["total_checks"])
    c2.metric("Passed", summary["passed"], delta=f"{summary['pass_rate']:.1%} pass rate")
    c3.metric("Failed", summary["failed"],
              delta=f"-{summary['failed']}" if summary["failed"] > 0 else "0",
              delta_color="inverse")
    c4.metric("Critical", summary["by_severity"]["critical"],
              delta="NONE" if summary["by_severity"]["critical"] == 0 else f'{summary["by_severity"]["critical"]} FOUND',
              delta_color="normal" if summary["by_severity"]["critical"] == 0 else "inverse")
    c5.metric("Errors", summary["by_severity"]["error"],
              delta="NONE" if summary["by_severity"]["error"] == 0 else f'{summary["by_severity"]["error"]} FOUND',
              delta_color="normal" if summary["by_severity"]["error"] == 0 else "inverse")

    st.markdown("")

    # Charts Row
    col_sev, col_cat = st.columns(2)

    with col_sev:
        st.markdown('<div class="section-header">Severity Distribution</div>', unsafe_allow_html=True)
        sev_data = summary["by_severity"]
        # Filter out zero values
        sev_labels = [k.upper() for k, v in sev_data.items() if v > 0]
        sev_values = [v for v in sev_data.values() if v > 0]
        sev_colors = [SEVERITY_COLORS.get(k, "#666") for k, v in sev_data.items() if v > 0]

        fig_sev = go.Figure(data=[go.Pie(
            labels=sev_labels, values=sev_values,
            marker=dict(colors=sev_colors),
            hole=0.55,
            textinfo="label+value",
            textfont=dict(size=12),
            hovertemplate="%{label}: %{value} checks<br>%{percent}<extra></extra>",
        )])
        fig_sev.update_layout(
            height=320, margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
            showlegend=False,
            annotations=[dict(
                text=f"<b>{summary['pass_rate']:.0%}</b><br><span style='font-size:11px;color:#888'>Pass Rate</span>",
                x=0.5, y=0.5, font_size=24, showarrow=False, font_color="#e5e5e5",
            )],
        )
        st.plotly_chart(fig_sev, use_container_width=True)

    with col_cat:
        st.markdown('<div class="section-header">Category Breakdown</div>', unsafe_allow_html=True)
        cat_data = summary["by_category"]
        cat_names = [CATEGORY_LABELS.get(k, k) for k in cat_data.keys()]
        cat_passed = [v["passed"] for v in cat_data.values()]
        cat_failed = [v["failed"] for v in cat_data.values()]

        fig_cat = go.Figure()
        fig_cat.add_trace(go.Bar(
            y=cat_names, x=cat_passed, name="Passed",
            orientation="h", marker_color="#16a34a",
            text=[f"{p}" for p in cat_passed], textposition="inside",
        ))
        fig_cat.add_trace(go.Bar(
            y=cat_names, x=cat_failed, name="Failed",
            orientation="h", marker_color="#dc2626",
            text=[f"{f}" if f > 0 else "" for f in cat_failed], textposition="inside",
        ))
        fig_cat.update_layout(
            barmode="stack", height=320,
            margin=dict(t=20, b=20, l=20, r=20),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc"),
            xaxis=dict(title="Checks", gridcolor="#1a1f2e"),
            yaxis=dict(gridcolor="#1a1f2e"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_cat, use_container_width=True)

    # Failures summary
    failures = report.get_failures()
    if failures:
        st.markdown('<div class="section-header">⚠️ Failures & Warnings</div>', unsafe_allow_html=True)
        for r in sorted(failures, key=lambda x: SEVERITY_ORDER.get(x.severity.value, 0), reverse=True):
            with st.container():
                cols = st.columns([1, 1.5, 6, 2])
                cols[0].markdown(sev_badge(r.severity.value), unsafe_allow_html=True)
                cols[1].code(f"{r.check_id} · {r.period}", language=None)
                cols[2].markdown(f"**{r.check_name}**: {r.message}")
                if r.delta is not None:
                    delta_str = f"Δ = {r.delta:+.4f}"
                    if r.delta_pct is not None:
                        delta_str += f" ({r.delta_pct:+.2%})"
                    cols[3].caption(delta_str)
    else:
        st.success("✅ All checks passed — model is clean.")


# ============================================================================
# TAB 2: Check Results
# ============================================================================

with tab_results:
    st.markdown("### All Check Results")

    # Filters
    fc1, fc2, fc3, fc4 = st.columns(4)

    with fc1:
        sev_filter = st.multiselect(
            "Severity",
            options=["critical", "error", "warning", "info", "pass"],
            default=["critical", "error", "warning"],
            format_func=str.upper,
        )
    with fc2:
        cat_options = list(set(r.category.value for r in report.results))
        cat_filter = st.multiselect(
            "Category",
            options=cat_options,
            default=cat_options,
            format_func=lambda x: CATEGORY_LABELS.get(x, x),
        )
    with fc3:
        period_options = sorted(set(r.period for r in report.results if r.period))
        period_filter = st.multiselect("Period", options=period_options, default=period_options)
    with fc4:
        search_text = st.text_input("🔍 Search", placeholder="Check ID, name, or message...")

    # Filter results
    filtered = [
        r for r in report.results
        if r.severity.value in sev_filter
        and r.category.value in cat_filter
        and (r.period in period_filter or r.period is None)
        and (not search_text or search_text.lower() in
             f"{r.check_id} {r.check_name} {r.message}".lower())
    ]

    st.caption(f"Showing {len(filtered)} of {len(report.results)} checks")

    if filtered:
        df = results_to_df(filtered)

        # Color-code severity column
        def style_severity(val):
            color = SEVERITY_COLORS.get(val, "#666")
            return f"color: {color}; font-weight: 700;"

        styled_df = df.style.applymap(style_severity, subset=["Severity"])
        st.dataframe(
            styled_df,
            use_container_width=True,
            height=600,
            column_config={
                "Expected": st.column_config.NumberColumn(format="%.2f"),
                "Actual": st.column_config.NumberColumn(format="%.2f"),
                "Delta": st.column_config.NumberColumn(format="%.4f"),
            }
        )
    else:
        st.info("No results match your filters.")


# ============================================================================
# TAB 3: Field Mapping
# ============================================================================

with tab_mapping:
    st.markdown("### Field Mapping Diagnostics")
    st.caption("Shows how your model's field names were mapped to the engine's internal schema.")

    if diagnostics:
        for diag in diagnostics:
            stmt_label = diag.statement_type.replace("_", " ").title()
            mapped_pct = diag.mapped_count / diag.total_input_fields * 100 if diag.total_input_fields > 0 else 0

            with st.expander(
                f"{'✅' if diag.unmapped_count == 0 else '⚠️'} "
                f"{stmt_label} — {diag.mapped_count}/{diag.total_input_fields} mapped ({mapped_pct:.0f}%)",
                expanded=diag.unmapped_count > 0,
            ):
                # Stats row
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Exact", diag.exact_matches)
                mc2.metric("Alias", diag.alias_matches)
                mc3.metric("Fuzzy", diag.fuzzy_matches)
                mc4.metric("Unmapped", diag.unmapped_count)

                # Mapping details table
                if diag.results:
                    mapping_rows = []
                    for r in diag.results:
                        mapping_rows.append({
                            "Input Field": r.input_name,
                            "Mapped To": r.internal_field or "—",
                            "Match Type": r.match_type.upper(),
                            "Confidence": f"{r.confidence:.0%}",
                        })
                    mdf = pd.DataFrame(mapping_rows)

                    def style_match(val):
                        colors = {
                            "EXACT": "color: #16a34a;",
                            "ALIAS": "color: #2563eb;",
                            "FUZZY": "color: #ca8a04;",
                            "UNMAPPED": "color: #dc2626; font-weight: 700;",
                        }
                        return colors.get(val, "")

                    st.dataframe(
                        mdf.style.applymap(style_match, subset=["Match Type"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                # Warnings
                if diag.warnings:
                    st.markdown("**Warnings:**")
                    for w in diag.warnings:
                        st.warning(w, icon="⚠️")

                # Unmapped
                if diag.unmapped_fields:
                    st.markdown("**Unmapped Fields** — add these to your mapping YAML:")
                    st.code("\n".join(diag.unmapped_fields), language=None)
    else:
        st.info("No mapping diagnostics available.")


# ============================================================================
# TAB 4: Period Analysis
# ============================================================================

with tab_periods:
    st.markdown("### Period-by-Period Analysis")

    periods_list = sorted(set(r.period for r in report.results if r.period))
    check_ids = sorted(set(r.check_id for r in report.results))

    # Build heatmap data
    heatmap_data = {}
    for r in report.results:
        if r.period:
            key = (r.check_id, r.period)
            heatmap_data[key] = SEVERITY_ORDER.get(r.severity.value, 0)

    if periods_list and check_ids:
        # Heatmap
        z_data = []
        hover_data = []
        check_labels = []
        for cid in check_ids:
            row = []
            hover_row = []
            # Get check name
            matching = [r for r in report.results if r.check_id == cid]
            cname = matching[0].check_name if matching else cid
            check_labels.append(f"{cid}: {cname[:40]}")
            for p in periods_list:
                val = heatmap_data.get((cid, p), -1)
                row.append(val)
                # Find the actual result for hover text
                result = next((r for r in report.results if r.check_id == cid and r.period == p), None)
                if result:
                    hover_row.append(f"{result.severity.value.upper()}<br>{result.message[:80]}")
                else:
                    hover_row.append("No data")
            z_data.append(row)
            hover_data.append(hover_row)

        # Custom colorscale: pass=green, warning=yellow, error=orange, critical=red
        colorscale = [
            [0.0, "#16a34a"],   # pass (0)
            [0.25, "#2563eb"],  # info (1)
            [0.5, "#ca8a04"],   # warning (2)
            [0.75, "#ea580c"],  # error (3)
            [1.0, "#dc2626"],   # critical (4)
        ]

        fig_heat = go.Figure(data=go.Heatmap(
            z=z_data,
            x=periods_list,
            y=check_labels,
            colorscale=colorscale,
            zmin=0, zmax=4,
            customdata=hover_data,
            hovertemplate="<b>%{y}</b><br>Period: %{x}<br>%{customdata}<extra></extra>",
            showscale=False,
        ))
        fig_heat.update_layout(
            height=max(400, len(check_ids) * 22),
            margin=dict(t=30, b=30, l=300, r=30),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#ccc", size=11),
            xaxis=dict(side="top", tickangle=0),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        # Period summary table
        st.markdown('<div class="section-header">Period Summary</div>', unsafe_allow_html=True)
        period_rows = []
        for p in periods_list:
            p_results = [r for r in report.results if r.period == p]
            p_pass = sum(1 for r in p_results if r.severity == Severity.PASS)
            p_fail = len(p_results) - p_pass
            p_crit = sum(1 for r in p_results if r.severity == Severity.CRITICAL)
            p_err = sum(1 for r in p_results if r.severity == Severity.ERROR)
            period_rows.append({
                "Period": p,
                "Total": len(p_results),
                "Passed": p_pass,
                "Failed": p_fail,
                "Critical": p_crit,
                "Errors": p_err,
                "Pass Rate": f"{p_pass / len(p_results):.0%}" if p_results else "—",
            })
        st.dataframe(pd.DataFrame(period_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Not enough data for period analysis.")


# ============================================================================
# TAB 5: Export
# ============================================================================

with tab_export:
    st.markdown("### Export Reports")

    ec1, ec2 = st.columns(2)

    with ec1:
        st.markdown("#### 📄 JSON Report")
        st.caption("Structured report for pipeline integration, APIs, or downstream processing.")
        json_str = report.to_json()
        st.download_button(
            label="⬇️ Download JSON Report",
            data=json_str,
            file_name=f"verification_{summary['company_name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.json",
            mime="application/json",
            use_container_width=True,
        )
        with st.expander("Preview JSON"):
            st.json(json.loads(json_str)["summary"])

    with ec2:
        st.markdown("#### 📊 Excel Report")
        st.caption("Formatted workbook with Summary, Check Results, and Failures sheets.")

        # Generate Excel in memory
        tmp_path = os.path.join(tempfile.gettempdir(), f"fs_verify_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx")
        try:
            export_excel(report, tmp_path)
            with open(tmp_path, "rb") as f:
                xlsx_bytes = f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except (PermissionError, OSError):
                pass  # Windows may hold a lock; file will be cleaned up later

        st.download_button(
            label="⬇️ Download Excel Report",
            data=xlsx_bytes,
            file_name=f"verification_{summary['company_name'].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.divider()

    # Raw data export
    st.markdown("#### 📋 Raw Results CSV")
    df_all = results_to_df(report.results)
    csv_data = df_all.to_csv(index=False)
    st.download_button(
        label="⬇️ Download CSV",
        data=csv_data,
        file_name=f"verification_results_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )

    # Model echo
    with st.expander("🔎 Parsed Model Echo"):
        st.caption("Verify the engine parsed your model correctly.")
        st.json(model.to_dict())
