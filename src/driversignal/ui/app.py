"""Driver Signal Streamlit UI.

Everything that draws the app runs inside ``render()`` (or the functions it calls), so it runs on every rerun,
both in the standalone ``app.py`` and inside Signal Hub. Module-level code here only defines constants and
functions. ``render()`` never calls ``st.set_page_config`` or ``st.navigation``.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import platform
import traceback

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import statsmodels
import streamlit as st

from driversignal import __version__
from driversignal.analysis import SurveyAnalysis, analyze_survey
from driversignal.errors import DataProblem, friendly_message
from driversignal.examples import (
    DEMO_FILENAME,
    demo_csv_bytes,
    template_csv_bytes,
    template_xlsx_bytes,
)
from driversignal.io import load_data, results_to_excel, results_to_json, tables_to_csv_zip
from driversignal.reporting import privacy_safe_influence
from driversignal.ui import signal_theme as sig
from driversignal.ui.plotting import (
    FITTED_MAX_POINTS,
    FITTED_TOP_INFLUENCE,
    coefficient_figure,
    fitted_figure,
    importance_figure,
    reliability_figure,
)
from driversignal.validation import default_item_spec, infer_column, numeric_candidates


NS = "driver"


def k(name: str) -> str:
    """Namespace a session-state or widget key with the app slug, so apps can share one Hub session."""
    return f"{NS}:{name}"


SIDEBAR_TAGLINE = "Survey ratings in. Reliable constructs and challengeable priorities out."
MASTHEAD_KICKER = "OPEN SURVEY DRIVER ANALYSIS"
MASTHEAD_PROMISES = ["Local-first", "Explainable", "Open source"]
FOOTER_LINE = "Associations to investigate, not causal proof"
CHART_CONFIG = {"displaylogo": False}

ASSOCIATION_NOTE = (
    "**Driver means measured association here—not proven cause.** A cross-sectional survey can prioritize questions "
    "and experiments, but respondent selection, common-method bias, omitted variables, and reverse direction can all "
    "produce a strong-looking relationship."
)

STATE_DEFAULTS = (
    ("tables", None),
    ("active_table", None),
    ("source_name", None),
    ("source_fingerprint", None),
    ("data_epoch", 0),
    ("upload_seen", None),
    ("analysis", None),
    ("analysis_config", None),
    ("item_spec", None),
    ("spec_signature", None),
    ("editor_epoch", 0),
    ("column_profile", None),
    ("export_cache", None),
)


def full_width(widget, *args, **kwargs):
    """Use Streamlit's current width API while retaining older compatibility."""
    try:
        parameters = inspect.signature(widget).parameters
    except (TypeError, ValueError):
        parameters = {}
    width_parameter = parameters.get("width")
    if width_parameter is not None and isinstance(width_parameter.default, str):
        kwargs["width"] = "stretch"
    elif "use_container_width" in parameters:
        kwargs["use_container_width"] = True
    return widget(*args, **kwargs)


def show_error(exc: Exception) -> None:
    st.error(friendly_message(exc))
    if not isinstance(exc, (DataProblem, ValueError)) and os.getenv("DRIVERSIGNAL_DEBUG") == "1":
        with st.expander("Technical details"):
            st.code("".join(traceback.format_exception(exc)))


def _association_note() -> None:
    sig.note("warn", ASSOCIATION_NOTE)


def go_to(page_name: str) -> None:
    """Ask the sidebar page selector to switch page on the next draw (it may already exist in this run)."""
    st.session_state[k("nav_target")] = page_name


def _fingerprint(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _setup_signature(spec: pd.DataFrame, settings: dict[str, object]) -> str:
    """Fingerprint every setting that can change a saved analysis."""
    payload = {**settings, "item_spec": json.loads(spec.to_json(orient="records"))}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clear_analysis() -> None:
    st.session_state[k("analysis")] = None
    st.session_state[k("analysis_config")] = None
    st.session_state[k("item_spec")] = None
    st.session_state[k("spec_signature")] = None
    st.session_state[k("export_cache")] = None
    st.session_state[k("editor_epoch")] = int(st.session_state.get(k("editor_epoch"), 0)) + 1


def _set_loaded(tables: dict[str, pd.DataFrame], source_name: str, fingerprint: str) -> None:
    st.session_state[k("tables")] = tables
    st.session_state[k("active_table")] = next(iter(tables))
    st.session_state[k("source_name")] = source_name
    st.session_state[k("source_fingerprint")] = fingerprint
    st.session_state[k("data_epoch")] = int(st.session_state.get(k("data_epoch"), 0)) + 1
    _clear_analysis()


def load_demo(*, navigate: bool = True) -> None:
    # Generated in memory (byte-identical to the committed demo CSV), so the demo also
    # works when the package is installed without the repository's example files, e.g. inside Signal Hub.
    raw = demo_csv_bytes()
    loaded = load_data(raw, name=DEMO_FILENAME)
    _set_loaded(loaded.tables, loaded.source_name, _fingerprint(raw))
    if navigate:
        go_to("1 · Data & scales")


def demo_is_loaded() -> bool:
    return st.session_state.get(k("source_fingerprint")) == _fingerprint(demo_csv_bytes())


def _load_upload(uploaded) -> None:
    raw = uploaded.getvalue()
    fingerprint = _fingerprint(raw)
    if st.session_state.get(k("upload_seen")) == fingerprint:
        return
    loaded = load_data(raw, name=uploaded.name)
    st.session_state[k("upload_seen")] = fingerprint
    _set_loaded(loaded.tables, loaded.source_name, fingerprint)
    go_to("1 · Data & scales")


def active_frame() -> pd.DataFrame | None:
    tables = st.session_state.get(k("tables"))
    table = st.session_state.get(k("active_table"))
    return tables.get(table) if tables and table in tables else None


def _ensure_state() -> None:
    """Set state defaults and preload the fictional survey on first run, so the app (and Signal Hub) opens with a working demo.

    "Clear survey" sets the tables to None rather than deleting the key, so a cleared session stays empty.
    """
    first_run = k("tables") not in st.session_state
    for name, default in STATE_DEFAULTS:
        st.session_state.setdefault(k(name), default)
    if first_run:
        load_demo(navigate=False)


def welcome_page() -> None:
    sig.hero(
        NS,
        eyebrow="SURVEY DRIVER ANALYSIS, WITHOUT THE BLACK BOX",
        title="Find what moves with satisfaction.",
        em="Then test what truly moves it.",
        body=(
            "Turn respondent-level ratings into a ranked driver map, robust coefficient intervals, model-health checks, "
            "and honest scale-reliability diagnostics. The quick read is built for marketers; every assumption remains "
            "visible for analysts."
        ),
        pills=["Satisfaction or NPS", "Cronbach's alpha", "LMG / Shapley importance", "HC3 robust intervals"],
    )
    _association_note()
    sig.cards(
        [
            ("01 · DEFINE", "Build the right constructs", "Group related items, mark reverse-keyed questions, and keep the scoring rule explicit."),
            ("02 · CHECK", "Challenge the measurement", "Read alpha, item–total correlation, alpha-if-deleted, missingness, and inter-item correlation together."),
            ("03 · PRIORITIZE", "Separate importance from direction", "Allocate shared R² fairly with LMG/Shapley, then use standardized betas for conditional direction."),
        ]
    )
    columns = st.columns(4)
    columns[0].metric("Input", "1 row / respondent")
    columns[1].metric("NPS model", "Original 0–10")
    columns[2].metric("Uncertainty", "HC3 robust")
    columns[3].metric("Data path", "Local only")
    sig.note(
        "info",
        "**Two reading speeds.** Start with the ranked priority view and plain-language brief. "
        "Open the model, VIF, reliability, retention, and residual tables when the decision deserves an audit.",
    )
    if demo_is_loaded():
        sig.note(
            "info",
            "**The fictional demo survey is already loaded:** 520 synthetic respondents rating Service, Value, Ease, "
            "and Trust on 1–7 items, plus satisfaction and a 0–10 recommendation score. It describes no real person, "
            "company, or brand. Open it to run the analysis, or upload your own survey in the sidebar to replace it.",
        )
    if st.button("Open the fictional survey", type="primary", key=k("open_demo")):
        try:
            if demo_is_loaded():
                go_to("1 · Data & scales")
            else:
                load_demo()
            st.rerun()
        except Exception as exc:
            show_error(exc)
    with st.expander("What this tool deliberately does not claim"):
        st.markdown(
            """
            - A high-ranked survey driver is not automatically causal, actionable, or economically valuable.
            - Cronbach's alpha does not prove one dimension, construct validity, temporal stability, or good wording.
            - A small exploratory p-value does not repair convenience sampling, omitted variables, or common-method bias.
            - NPS is reported as an aggregate, while its driver model uses the information-preserving 0–10 response.
            - This release does not apply survey weights, cluster-robust errors, latent-variable models, or automatic imputation.
            """
        )


def _default_driver_items(frame: pd.DataFrame, candidates: list[str], outcome: str) -> list[str]:
    prefixes = {"service", "value", "ease", "trust", "quality", "support", "product", "price"}
    preferred = [column for column in candidates if column != outcome and column.lower().split("_")[0] in prefixes]
    if preferred:
        return preferred[:16]
    excluded_tokens = ("id", "age", "tenure", "year", "month", "weight")
    return [
        column
        for column in candidates
        if column != outcome and not any(token in column.lower() for token in excluded_tokens)
    ][:10]


def data_page() -> None:
    sig.header("Step 1", "Data, outcome & scale setup")
    frame = active_frame()
    if frame is None:
        st.info("Load the fictional survey in the sidebar, or upload one row per respondent.")
        left, right = st.columns(2)
        full_width(
            left.download_button,
            "Download CSV template",
            template_csv_bytes(),
            "driversignal_survey_template.csv",
            "text/csv",
            key=k("download_csv_template"),
        )
        full_width(
            right.download_button,
            "Download Excel template + setup example",
            template_xlsx_bytes(),
            "driversignal_survey_template.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=k("download_xlsx_template"),
        )
        return

    profile = _column_profile(frame)
    numeric = profile["numeric"]
    if len(numeric) < 2:
        st.error("This table needs one numeric outcome and at least one numeric survey item.")
        return
    missing_cells = profile["missing_cells"]
    columns = st.columns(4)
    columns[0].metric("Respondents", f"{len(frame):,}")
    columns[1].metric("Columns", f"{frame.shape[1]:,}")
    columns[2].metric("Numeric candidates", f"{len(numeric):,}")
    columns[3].metric("Missing cells", f"{missing_cells:,}")
    st.caption("Driver Signal reads the selected table in memory. It does not upload it or modify the source file.")

    data_epoch = st.session_state[k("data_epoch")]
    tabs = st.tabs(["Set up analysis", "Preview & privacy"])
    with tabs[0]:
        nps_named = [column for column in numeric if any(token in column.lower() for token in ("recommend", "nps"))]
        guess = nps_named[0] if nps_named else infer_column(numeric, ("satisfaction", "satisfied", "overall"))
        outcome = st.selectbox(
            "Outcome to explain",
            numeric,
            index=numeric.index(guess),
            key=k(f"outcome_{data_epoch}"),
            help="Use the respondent's original satisfaction or 0–10 recommendation response—not an aggregate NPS value.",
        )
        role_key = f"{data_epoch}_{hashlib.sha256(outcome.encode('utf-8')).hexdigest()[:10]}"
        likely_nps = any(token in outcome.lower() for token in ("recommend", "nps"))
        outcome_kind = st.radio(
            "Outcome interpretation",
            ["NPS (0–10 recommendation)", "Satisfaction / other numeric rating"],
            index=0 if likely_nps else 1,
            horizontal=True,
            key=k(f"outcome_kind_{role_key}"),
        )
        available_items = [column for column in numeric if column != outcome]
        selected_items = st.multiselect(
            "Survey items to use",
            available_items,
            default=_default_driver_items(frame, numeric, outcome),
            key=k(f"driver_items_{role_key}"),
            help="Items assigned the same scale become one mean construct. Blank scale names stay as standalone drivers.",
        )
        signature = (
            st.session_state.get(k("source_fingerprint")),
            st.session_state.get(k("active_table")),
            tuple(selected_items),
        )
        if st.session_state.get(k("spec_signature")) != signature:
            st.session_state[k("item_spec")] = default_item_spec(selected_items)
            st.session_state[k("spec_signature")] = signature
            st.session_state[k("editor_epoch")] += 1
            st.session_state[k("analysis")] = None
            st.session_state[k("analysis_config")] = None

        st.markdown("#### Item setup")
        st.caption(
            "Edit the display label or construct name. Check reverse-scored only when theory and wording require it; "
            "Driver Signal never guesses beyond an obvious column-name hint."
        )
        spec = st.session_state.get(k("item_spec"))
        if spec is None or spec.empty:
            st.info("Choose at least one numeric survey item.")
            return
        editor_epoch = st.session_state[k("editor_epoch")]
        edited_spec = full_width(
            st.data_editor,
            spec,
            hide_index=True,
            num_rows="fixed",
            disabled=["item"],
            key=k(f"item_editor_{editor_epoch}"),
            column_config={
                "item": st.column_config.TextColumn("Source item"),
                "label": st.column_config.TextColumn("Readable label"),
                "scale": st.column_config.TextColumn("Scale / construct", help="Same non-empty name = one mean score"),
                "reverse_scored": st.column_config.CheckboxColumn("Reverse scored"),
            },
        )

        left, middle, right = st.columns(3)
        scale_minimum = left.number_input("Item scale minimum", value=1.0, step=1.0, key=k("scale_minimum"))
        scale_maximum = middle.number_input("Item scale maximum", value=7.0, step=1.0, key=k("scale_maximum"))
        completion_label = right.selectbox(
            "Answers needed per construct",
            ["All items", "At least 80%", "At least two-thirds"],
            index=0,
            key=k("completion_rule"),
            help="This affects construct means. The final regression still uses one shared complete-case sample.",
        )
        completion_map = {"All items": 1.0, "At least 80%": 0.80, "At least two-thirds": 2.0 / 3.0}
        with st.expander("Advanced reproducibility settings"):
            confidence_percent = st.select_slider(
                "Coefficient confidence level", options=[90, 95, 99], value=95, key=k("confidence_percent")
            )
            alpha_bootstrap = st.selectbox(
                "Alpha bootstrap repetitions",
                [0, 200, 400, 1000],
                index=2,
                format_func=lambda value: "Skip interval" if value == 0 else f"{value:,}",
                key=k("alpha_bootstrap"),
            )
            importance_permutations = st.selectbox(
                "Approximate importance permutations (only above 10 drivers)",
                [500, 1000, 2000, 5000],
                index=2,
                key=k("importance_permutations"),
            )
            st.caption("All resampling and permutation routines use the fixed seed 2026. Up to 10 drivers use exact LMG/Shapley.")

        current_settings = {
            "outcome": outcome,
            "outcome_kind": outcome_kind,
            "confidence_percent": confidence_percent,
            "alpha_bootstrap_repetitions": alpha_bootstrap,
            "importance_permutations": importance_permutations,
            "seed": 2026,
            "completion_rule": completion_label,
            "minimum_answered_fraction": completion_map[completion_label],
            "scale_minimum": scale_minimum,
            "scale_maximum": scale_maximum,
        }
        setup_signature = _setup_signature(edited_spec, current_settings)
        saved_config = st.session_state.get(k("analysis_config")) or {}
        if st.session_state.get(k("analysis")) is not None and saved_config.get("setup_signature") != setup_signature:
            st.session_state[k("analysis")] = None
            st.session_state[k("analysis_config")] = None
            st.info("The setup changed. Run the analysis again before using reliability, driver, or export results.")

        _association_note()
        if st.button("Analyze survey", type="primary", key=k("analyze")):
            try:
                analysis = analyze_survey(
                    frame,
                    outcome,
                    edited_spec,
                    outcome_kind=outcome_kind,
                    scale_minimum=float(scale_minimum),
                    scale_maximum=float(scale_maximum),
                    minimum_answered_fraction=completion_map[completion_label],
                    confidence=confidence_percent / 100.0,
                    reliability_bootstrap_repetitions=int(alpha_bootstrap),
                    nps_bootstrap_repetitions=5000,
                    importance_permutations=int(importance_permutations),
                    seed=2026,
                )
                st.session_state[k("analysis")] = analysis
                st.session_state[k("item_spec")] = edited_spec.copy()
                st.session_state[k("analysis_config")] = {**current_settings, "setup_signature": setup_signature}
                go_to("2 · Reliability")
                st.rerun()
            except Exception as exc:
                show_error(exc)

    with tabs[1]:
        st.markdown("#### Source preview")
        full_width(st.dataframe, frame.head(50), hide_index=True)
        sig.note(
            "warn",
            "**Before uploading respondent data:** remove names, email addresses, phone numbers, free-text comments, "
            "direct customer IDs, and columns you do not need. Small groups and unusual combinations can still "
            "re-identify people even without a name.",
        )
        full_width(st.dataframe, profile["missing"], hide_index=True)


def _column_profile(frame: pd.DataFrame) -> dict[str, object]:
    """Numeric candidates and missingness, computed once per loaded table rather than on every rerun."""
    signature = (st.session_state.get(k("data_epoch")), id(frame), frame.shape)
    cached = st.session_state.get(k("column_profile"))
    if cached and cached.get("signature") == signature:
        return cached
    missing_rows = frame.isna().sum()
    profile = {
        "signature": signature,
        "numeric": numeric_candidates(frame),
        "missing_cells": int(missing_rows.sum()),
        "missing": pd.DataFrame(
            {
                "column": frame.columns,
                "missing_rows": missing_rows.astype(int).to_numpy(),
                "missing_percent": (missing_rows / max(len(frame), 1) * 100).astype(float).to_numpy(),
                "unique_values": [int(frame[column].nunique(dropna=True)) for column in frame],
            }
        ).sort_values("missing_percent", ascending=False),
    }
    st.session_state[k("column_profile")] = profile
    return profile


def _analysis_or_prompt() -> SurveyAnalysis | None:
    analysis = st.session_state.get(k("analysis"))
    if analysis is None:
        st.info("Set up and run an analysis on page 1 first.")
        if st.button("Go to data & scales", key=k("go_to_data")):
            go_to("1 · Data & scales")
            st.rerun()
        return None
    return analysis


def reliability_page() -> None:
    sig.header("Step 2", "Scale reliability")
    analysis = _analysis_or_prompt()
    if analysis is None:
        return
    st.markdown(
        "Cronbach's alpha asks whether items move together under a tau-equivalent reliability model. Read it beside "
        "item wording, corrected item–total correlations, inter-item correlations, missingness, and theory."
    )
    if analysis.scale_summary.empty:
        st.info("This setup uses only standalone drivers, so there are no multi-item scales to assess.")
    else:
        scored = analysis.scale_summary.loc[analysis.scale_summary["cronbach_alpha"].notna()]
        if not scored.empty:
            metric_columns = st.columns(min(4, len(scored)))
            for index, row in enumerate(scored.itertuples(index=False)):
                column = metric_columns[index % len(metric_columns)]
                column.metric(row.scale, f"α {row.cronbach_alpha:.2f}", f"n={int(row.complete_for_alpha):,} complete")
            sig.chart(NS, reliability_figure(analysis.scale_summary), key=k("reliability_chart"), config=CHART_CONFIG)
        full_width(
            st.dataframe,
            analysis.scale_summary,
            hide_index=True,
            column_config={
                "cronbach_alpha": st.column_config.NumberColumn("Raw alpha", format="%.3f"),
                "alpha_ci_low": st.column_config.NumberColumn("Bootstrap low", format="%.3f"),
                "alpha_ci_high": st.column_config.NumberColumn("Bootstrap high", format="%.3f"),
                "standardized_alpha": st.column_config.NumberColumn("Standardized alpha", format="%.3f"),
                "mean_interitem_correlation": st.column_config.NumberColumn("Mean inter-item r", format="%.3f"),
            },
        )

    tabs = st.tabs(["Item diagnostics", "Inter-item correlations", "What alpha cannot tell you"])
    with tabs[0]:
        if analysis.item_diagnostics.empty:
            st.info("No multi-item scale diagnostics are available.")
        else:
            full_width(
                st.dataframe,
                analysis.item_diagnostics,
                hide_index=True,
                column_config={
                    "missing_percent": st.column_config.NumberColumn("Missing %", format="%.1f"),
                    "mean": st.column_config.NumberColumn("Mean", format="%.2f"),
                    "sd": st.column_config.NumberColumn("SD", format="%.2f"),
                    "corrected_item_total": st.column_config.NumberColumn("Corrected item–total r", format="%.3f"),
                    "alpha_if_deleted": st.column_config.NumberColumn("Alpha if deleted", format="%.3f"),
                },
            )
            st.caption("Alpha-if-deleted is a diagnostic, not an instruction to delete items until alpha rises.")
    with tabs[1]:
        if analysis.interitem_correlations.empty:
            st.info("No multi-item correlations are available.")
        else:
            full_width(st.dataframe, analysis.interitem_correlations, hide_index=True)
    with tabs[2]:
        st.markdown(
            """
            Alpha does **not** establish one-dimensionality, construct validity, absence of response bias, stability over
            time, or measurement equivalence across groups. It also tends to increase as items are added. A negative
            item–total correlation is a reason to inspect direction and meaning—not permission to reverse or delete an
            item automatically. For high-stakes measurement, follow with factor analysis, validation against external
            criteria, and subgroup invariance checks.
            """
        )
    scale_warnings = [warning for warning in analysis.warnings if any(str(scale) + ":" in warning for scale in analysis.scale_summary.get("scale", []))]
    if scale_warnings:
        with st.expander(f"Reliability notes ({len(scale_warnings)})", expanded=True):
            for warning in scale_warnings:
                st.warning(warning)
    if st.button("Continue to driver model", type="primary", key=k("continue_to_drivers")):
        go_to("3 · Driver model")
        st.rerun()


def _metric(result, name: str) -> float:
    values = result.metrics.loc[result.metrics["metric"].eq(name), "value"]
    return float(values.iloc[0]) if len(values) else float("nan")


def driver_page() -> None:
    sig.header("Step 3", "Driver priorities & conditional associations")
    analysis = _analysis_or_prompt()
    if analysis is None:
        return
    result = analysis.driver_result
    _association_note()
    retained = int(_metric(result, "Usable respondents"))
    r2 = _metric(result, "R-squared")
    cv_r2 = _metric(result, "Five-fold CV R-squared")
    rmse = _metric(result, "RMSE")
    columns = st.columns(4)
    columns[0].metric("Usable respondents", f"{retained:,}")
    columns[1].metric("Model R²", f"{r2:.3f}")
    columns[2].metric("Five-fold CV R²", f"{cv_r2:.3f}" if np.isfinite(cv_r2) else "Not available")
    columns[3].metric("RMSE", f"{rmse:.2f}")

    # sig.note escapes HTML, so survey column names cannot inject markup into the callout.
    top = result.importance.iloc[0]
    if result.inference_valid:
        direction_word = "positive" if top["standardized_beta"] >= 0 else "negative"
        sig.note(
            "info",
            f"**First measured priority: {top['driver']}.** It receives "
            f"{top['r2_contribution']:.3f} R², or {top['share_of_explained_percent']:.1f}% of the variation this model "
            f"explains. Its conditional association is {direction_word} (standardized β "
            f"{top['standardized_beta']:+.2f}). Use this to frame a hypothesis and a bounded test—not as proof of a "
            "lever.",
        )
    else:
        sig.note(
            "warn",
            f"**Shared model fit only: {top['driver']} receives the largest diagnostic "
            f"importance allocation ({top['share_of_explained_percent']:.1f}% of explained variance).** The predictor "
            "matrix is rank-deficient, so Driver Signal suppresses individual directions and intervals. Revise overlapping "
            "or duplicate drivers before making a priority claim.",
        )
    st.subheader("Priority when drivers overlap")
    sig.chart(
        NS,
        importance_figure(result.importance, show_direction=result.inference_valid),
        key=k("importance_chart"),
        config=CHART_CONFIG,
    )
    direction_note = "; direction comes from beta" if result.inference_valid else "; direction is suppressed"
    st.caption(result.importance_method + ". Importance shares sum to the full model R²" + direction_note + ".")
    st.subheader("Conditional direction & uncertainty")
    confidence = int((st.session_state.get(k("analysis_config")) or {}).get("confidence_percent", 95))
    if not result.inference_valid:
        st.error(
            "The predictor matrix is rank-deficient. Individual coefficients and intervals are not uniquely identified, "
            "so this chart is withheld. Remove or combine duplicate and perfectly overlapping drivers, then analyze again."
        )
    else:
        sig.chart(NS, coefficient_figure(result.coefficients, confidence), key=k("coefficient_chart"), config=CHART_CONFIG)

    tabs = st.tabs(["Model health", "Collinearity", "Residual check", "Nerd tables"])
    with tabs[0]:
        left, right = st.columns(2)
        full_width(left.dataframe, result.metrics, hide_index=True)
        full_width(right.dataframe, analysis.retention, hide_index=True)
        full_width(st.dataframe, analysis.missingness, hide_index=True)
        st.caption("Every coefficient and LMG/Shapley subset uses the same complete-case respondent sample.")
    with tabs[1]:
        full_width(st.dataframe, result.vif, hide_index=True)
        st.markdown(
            "VIF describes how strongly one driver can be predicted from the others. High VIF makes individual betas "
            "unstable; LMG/Shapley still allocates shared R², but it cannot tell which correlated construct is causal."
        )
    with tabs[2]:
        sig.chart(NS, fitted_figure(result.fitted), key=k("fitted_chart"), config=CHART_CONFIG)
        st.caption("Color highlights Cook's-distance influence. A flag is a sensitivity prompt, not proof that a row is wrong.")
        if len(result.fitted) > FITTED_MAX_POINTS:
            st.caption(
                f"The chart draws {FITTED_MAX_POINTS:,} of {len(result.fitted):,} model rows: the "
                f"{FITTED_TOP_INFLUENCE:,} with the highest Cook's distance plus a seeded random sample of the rest."
            )
    with tabs[3]:
        st.markdown("#### Standardized and raw coefficients")
        full_width(st.dataframe, result.coefficients, hide_index=True)
        st.markdown("#### Driver correlations")
        full_width(st.dataframe, result.correlations, hide_index=True)
        st.markdown("#### Relative-importance allocation")
        full_width(st.dataframe, result.importance, hide_index=True)

    model_warnings = [warning for warning in analysis.warnings if not any(str(scale) + ":" in warning for scale in analysis.scale_summary.get("scale", []))]
    if model_warnings:
        with st.expander(f"Model notes ({len(model_warnings)})", expanded=True):
            for warning in model_warnings:
                st.warning(warning)
    if st.button("Build decision brief & export", type="primary", key=k("build_brief")):
        go_to("4 · Interpret & export")
        st.rerun()


def _manifest(analysis: SurveyAnalysis) -> tuple[pd.DataFrame, dict[str, object]]:
    config = st.session_state.get(k("analysis_config")) or {}
    result = analysis.driver_result
    metadata: dict[str, object] = {
        "product": "Driver Signal",
        "version": __version__,
        "source_name": st.session_state.get(k("source_name")),
        "source_table": st.session_state.get(k("active_table")),
        "source_sha256": st.session_state.get(k("source_fingerprint")),
        "outcome": analysis.outcome_column,
        "outcome_kind": analysis.outcome_kind,
        "drivers": list(analysis.predictor_columns),
        "construct_scoring": "Row mean after declared reverse scoring",
        "construct_completion_rule": config.get("completion_rule"),
        "minimum_answered_fraction": analysis.minimum_answered_fraction,
        "item_scale_minimum": analysis.scale_minimum,
        "item_scale_maximum": analysis.scale_maximum,
        "missing_data_rule": "One listwise-complete sample across outcome and all nonconstant model drivers",
        "coefficient_model": "OLS on standardized outcome and predictors",
        "covariance": "HC3 heteroskedasticity-robust",
        "confidence_percent": config.get("confidence_percent", 95),
        "importance_method": result.importance_method,
        "importance_seed": config.get("seed", 2026),
        "model_rows": len(result.fitted),
        "alpha_sample": "Listwise complete within each scale",
        "alpha_bootstrap_repetitions": config.get("alpha_bootstrap_repetitions"),
        "alpha_bootstrap_basis": _bootstrap_basis(analysis),
        "causal_status": "Observational association; no causal effect claimed",
        "inference_valid": result.inference_valid,
        "python": platform.python_version(),
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "statsmodels": statsmodels.__version__,
        "streamlit": st.__version__,
        "warnings": list(analysis.warnings),
    }
    rows = []
    for key, value in metadata.items():
        if key == "warnings":
            continue
        if isinstance(value, list):
            value = "; ".join(map(str, value))
        rows.append({"field": key, "value": value})
    return pd.DataFrame(rows), metadata


def _bootstrap_basis(analysis: SurveyAnalysis) -> str:
    summary = analysis.scale_summary
    if summary.empty or "alpha_bootstrap_rows" not in summary:
        return "No multi-item scales"
    subsampled = summary.loc[
        (summary["alpha_bootstrap_rows"] > 0) & (summary["alpha_bootstrap_rows"] < summary["complete_for_alpha"]),
        "scale",
    ].tolist()
    if not subsampled:
        return "Every complete respondent"
    return "Seeded subsample rescaled by sqrt(m/n) for: " + ", ".join(map(str, subsampled))


def _evidence_tables(analysis: SurveyAnalysis) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    manifest, metadata = _manifest(analysis)
    result = analysis.driver_result
    settings = pd.DataFrame(
        [
            {"setting": "Outcome", "value": analysis.outcome_column},
            {"setting": "Outcome interpretation", "value": analysis.outcome_kind},
            {"setting": "Scale minimum", "value": analysis.scale_minimum},
            {"setting": "Scale maximum", "value": analysis.scale_maximum},
            {"setting": "Minimum answered fraction", "value": analysis.minimum_answered_fraction},
            {"setting": "Importance method", "value": result.importance_method},
            {"setting": "Causal claim", "value": "None — observational association only"},
        ]
    )
    warnings = pd.DataFrame({"warning": list(analysis.warnings)})
    tables = {
        "Manifest": manifest,
        "Outcome summary": analysis.outcome_summary,
        "NPS composition": analysis.nps_composition,
        "Retention": analysis.retention,
        "Missingness": analysis.missingness,
        "Scale definitions": analysis.scale_definitions,
        "Scale summary": analysis.scale_summary,
        "Item diagnostics": analysis.item_diagnostics,
        "Inter-item correlations": analysis.interitem_correlations,
        "Driver coefficients": result.coefficients,
        "Relative importance": result.importance,
        "VIF": result.vif,
        "Driver correlations": result.correlations,
        "Model metrics": result.metrics,
        "Influence diagnostics": privacy_safe_influence(result.fitted),
        "Analysis settings": settings,
        "Warnings": warnings,
    }
    return tables, metadata


def _nps_figure(composition: pd.DataFrame) -> go.Figure:
    """NPS group shares: detractors and promoters at the two ends of the diverging palette, passives neutral."""
    figure = go.Figure(
        go.Bar(
            x=composition["category"],
            y=composition["percent"],
            marker_color=[sig.DIVERGING[-2], sig.CORE["soft"], sig.DIVERGING[1]],
            text=composition["percent"].map(lambda value: f"{value:.1f}%"),
            textposition="outside",
            hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
        )
    )
    figure.update_layout(
        template=sig.template(NS),
        height=330,
        margin=dict(l=55, r=30, t=20, b=55),
        yaxis=dict(title="Respondents (%)", range=[0, max(55, float(composition["percent"].max()) * 1.2)]),
        xaxis=dict(title=None),
        showlegend=False,
    )
    return figure


def decision_page() -> None:
    sig.header("Step 4", "Decision brief & evidence pack")
    analysis = _analysis_or_prompt()
    if analysis is None:
        return
    result = analysis.driver_result
    _association_note()

    if not analysis.nps_composition.empty:
        nps_row = analysis.outcome_summary.loc[analysis.outcome_summary["metric"].eq("NPS")]
        nps_value = float(nps_row["value"].iloc[0]) if len(nps_row) else float("nan")
        columns = st.columns(4)
        columns[0].metric("NPS", f"{nps_value:+.1f}")
        for index, row in enumerate(analysis.nps_composition.itertuples(index=False), start=1):
            columns[index].metric(row.category.split(" (")[0], f"{row.percent:.1f}%", f"n={int(row.respondents):,}")
        sig.chart(NS, _nps_figure(analysis.nps_composition), key=k("nps_chart"), config=CHART_CONFIG)

    st.subheader("Measured priorities")
    brief = result.importance.merge(
        result.coefficients[["driver", "ci_low", "ci_high", "p_value_exploratory"]],
        on="driver",
        how="left",
    ).merge(result.vif[["driver", "vif", "diagnostic"]], on="driver", how="left")
    if result.inference_valid:
        brief["decision_prompt"] = brief.apply(
            lambda row: (
                "Frame a targeted improvement hypothesis and test it with a holdout or staged rollout."
                if row["standardized_beta"] > 0
                else "Check scoring and overlap, then investigate why a higher rating travels with a lower outcome."
            ),
            axis=1,
        )
        brief = brief[
            [
                "importance_rank",
                "driver",
                "r2_contribution",
                "share_of_explained_percent",
                "standardized_beta",
                "ci_low",
                "ci_high",
                "vif",
                "diagnostic",
                "decision_prompt",
            ]
        ].sort_values("importance_rank")
        full_width(st.dataframe, brief, hide_index=True)

        # sig.cards escapes HTML, so survey column names cannot inject markup into the cards.
        sig.cards(
            [
                (
                    f"PRIORITY {int(row.importance_rank):02d}",
                    str(row.driver),
                    f"{row.share_of_explained_percent:.1f}% of explained variance · β {row.standardized_beta:+.2f}. "
                    f"{row.decision_prompt}",
                )
                for row in brief.head(3).itertuples(index=False)
            ]
        )
        sig.note(
            "info",
            "**A disciplined next step:** combine this priority map with reach, feasibility, cost, and customer "
            "verbatims; pre-register the outcome and test a bounded intervention. Re-run the survey and model after "
            "implementation instead of turning the first ranking into a permanent scorecard.",
        )
    else:
        diagnostic_brief = brief[
            [
                "importance_rank",
                "driver",
                "r2_contribution",
                "share_of_explained_percent",
                "vif",
                "diagnostic",
            ]
        ].sort_values("importance_rank")
        st.error(
            "A decision brief is withheld because individual driver directions are not identifiable. Treat the allocation "
            "below only as a diagnostic of shared model fit; remove or combine overlapping drivers and analyze again."
        )
        full_width(st.dataframe, diagnostic_brief, hide_index=True)

    st.subheader("Portable evidence pack")
    st.caption(
        "Exports include method settings, source fingerprint, retention, scales, reliability, importance, coefficients, "
        "diagnostics, and warnings. They exclude raw responses and direct identifiers."
    )
    try:
        payload = _export_payload(analysis)
        tables = payload["tables"]
        excel, csv_zip, json_bytes = (_download_data(payload, kind) for kind in ("excel", "csv", "json"))
        columns = st.columns(3)
        full_width(
            columns[0].download_button,
            "Excel evidence pack",
            excel,
            "driversignal_evidence_pack.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=k("download_excel"),
        )
        full_width(
            columns[1].download_button,
            "Accessible CSV tables",
            csv_zip,
            "driversignal_evidence_tables.zip",
            "application/zip",
            key=k("download_csv_zip"),
        )
        full_width(
            columns[2].download_button,
            "JSON + audit trail",
            json_bytes,
            "driversignal_evidence.json",
            "application/json",
            key=k("download_json"),
        )
        with st.expander("Evidence-pack contents"):
            full_width(st.dataframe, pd.DataFrame({"table": list(tables), "rows": [len(table) for table in tables.values()]}), hide_index=True)
    except Exception as exc:
        show_error(exc)


# Streamlit versions that accept a callable build each file only when its button is clicked, so a large evidence pack
# (every influence row of millions of respondents) never blocks the page.
LAZY_DOWNLOADS = "callable" in (st.download_button.__doc__ or "")


def _export_payload(analysis: SurveyAnalysis) -> dict[str, object]:
    """Evidence tables for this analysis plus memoized builders for the three export files."""
    cache_key = (id(analysis), (st.session_state.get(k("analysis_config")) or {}).get("setup_signature"))
    cached = st.session_state.get(k("export_cache"))
    if cached and cached[0] == cache_key:
        return cached[1]
    tables, metadata = _evidence_tables(analysis)
    builders = {
        "excel": lambda: results_to_excel(tables),
        "csv": lambda: tables_to_csv_zip(tables),
        "json": lambda: results_to_json(tables, metadata),
    }
    built: dict[str, bytes] = {}

    def build(kind: str) -> bytes:
        if kind not in built:
            built[kind] = builders[kind]()
        return built[kind]

    payload = {"tables": tables, "build": build}
    st.session_state[k("export_cache")] = (cache_key, payload)
    return payload


def _download_data(payload: dict[str, object], kind: str):
    build = payload["build"]
    return (lambda: build(kind)) if LAZY_DOWNLOADS else build(kind)


def methods_page() -> None:
    sig.header("Methods and limits", "Methods, assumptions & limits")
    _association_note()
    tabs = st.tabs(["Plain-language method", "Reliability mathematics", "Driver mathematics", "Limits & references"])
    with tabs[0]:
        st.markdown(
            """
            1. **Keep one row per respondent.** Select the original satisfaction rating or 0–10 recommendation response.
            2. **Define constructs before modeling.** Group items that theory says measure the same thing. Reverse only
               explicitly reverse-keyed wording against declared theoretical endpoints.
            3. **Score transparently.** Driver Signal averages answered items when the declared completion rule is met.
            4. **Check reliability.** Raw and standardized alpha, item–total correlation, alpha-if-deleted, and inter-item
               correlations all use one listwise-complete sample within each construct.
            5. **Fit one shared sample.** After structurally constant candidates are removed, the final model removes any
               row missing the outcome or a retained driver. Every coefficient and relative-importance subset uses that
               same sample.
            6. **Read two different answers.** LMG/Shapley says how much of model R² a driver receives when predictors
               overlap; standardized beta says conditional direction and magnitude.
            7. **Turn priorities into tests.** The output is a map of observational evidence, not a causal effect estimate.
            """
        )
    with tabs[1]:
        st.markdown("For a scale with *k* items, raw Cronbach's alpha is:")
        st.latex(r"\alpha=\frac{k}{k-1}\left(1-\frac{\sum_{j=1}^{k}s_j^2}{s_T^2}\right)")
        st.markdown("Standardized alpha uses the mean inter-item correlation:")
        st.latex(r"\alpha_s=\frac{k\bar r}{1+(k-1)\bar r}")
        st.markdown(
            """
            The raw calculation uses sample variances and a listwise-complete item matrix. The bootstrap interval resamples
            respondents deterministically with replacement. With two items, alpha is simply a transformation of their
            correlation. Negative alpha is retained rather than clipped. Alpha assumes roughly tau-equivalent items and
            does not establish unidimensionality or validity. The often-used .70 convention is context—not a pass/fail law.
            Values above .95 can signal redundant wording.
            """
        )
    with tabs[2]:
        st.markdown("Driver Signal standardizes the outcome and predictors, then estimates:")
        st.latex(r"z_y=\beta_1z_{x_1}+\cdots+\beta_pz_{x_p}+\varepsilon")
        st.markdown(
            "Coefficient intervals and exploratory p-values use HC3 heteroskedasticity-robust covariance. HC3 does not "
            "solve clustering, repeated measures, omitted variables, nonlinearity, selection bias, or reverse causality."
        )
        st.markdown("LMG/Shapley allocates shared R² by averaging each driver's marginal contribution over predictor orderings:")
        st.latex(
            r"\phi_j=\sum_{S\subseteq P\setminus\{j\}}\frac{|S|!(p-|S|-1)!}{p!}"
            r"\left[R^2(S\cup\{j\})-R^2(S)\right]"
        )
        st.markdown(
            "Up to ten drivers use every subset exactly. Larger models use deterministic sampled orderings and label the "
            "result approximate. Importance is nonnegative and sums to full-model R²; beta supplies direction. Five-fold "
            "cross-validation provides a deterministic held-out check when the sample is large enough."
        )
        st.markdown("For standard NPS, Driver Signal reports:")
        st.latex(r"NPS=100\,(P_{promoter}-P_{detractor})")
        st.markdown(
            "Detractors are 0–6, passives 7–8, and promoters 9–10. The regression uses the original 0–10 score because "
            "the aggregate index has no respondent-level value and dichotomizing promoter status discards information."
        )
    with tabs[3]:
        st.markdown(
            """
            **Current limits**

            - OLS treats bounded rating scales as approximately interval-scaled and linear.
            - Complete-case analysis can be biased when missingness is systematic; no automatic imputation is performed.
            - Survey weights, clustered/repeated observations, nonlinear effects, interactions, factor analysis, measurement
              invariance, ordinal models, and latent-variable structural models are outside this release.
            - VIF and LMG/Shapley describe overlap but do not resolve causal identity among correlated constructs.
            - Data size: run locally, Driver Signal has no built-in limit on file size, respondents, items or
              drivers; the computer's memory is the limit. Every calculation and export uses all rows. The residual
              chart draws at most 5,000 points, and when an alpha bootstrap would resample more than 50,000,000
              cells it uses a seeded subsample rescaled by √(m/n), labelled in the results and exports. A public
              demo (`SIGNAL_PUBLIC=1`) applies demo caps instead.
            - Convenience samples, low response rates, leading questions, same-source measurement, and post-treatment
              controls can make technically precise estimates strategically wrong.

            **Method references**

            - Cronbach, L. J. (1951). Coefficient alpha and the internal structure of tests. *Psychometrika, 16*, 297–334.
            - White, H. (1980). A heteroskedasticity-consistent covariance matrix estimator. *Econometrica, 48*, 817–838.
            - MacKinnon, J. G., & White, H. (1985). Some heteroskedasticity-consistent covariance matrix estimators with
              improved finite sample properties. *Journal of Econometrics, 29*, 305–325.
            - Lindeman, R. H., Merenda, P. F., & Gold, R. Z. (1980). *Introduction to Bivariate and Multivariate Analysis*.
            - Grömping, U. (2007). Estimators of relative importance in linear regression based on variance decomposition.
              *The American Statistician, 61*(2), 139–147.
            """
        )


PAGES = {
    "Welcome": welcome_page,
    "1 · Data & scales": data_page,
    "2 · Reliability": reliability_page,
    "3 · Driver model": driver_page,
    "4 · Interpret & export": decision_page,
    "Methods & limits": methods_page,
}


def _sidebar() -> str:
    """Draw the sidebar lockup, data controls and page selector; return the selected page."""
    sig.sidebar_brand(NS, SIDEBAR_TAGLINE)
    with st.sidebar:
        st.markdown("### Start with a worked example")
        if full_width(st.button, "Demo · customer experience", key=k("demo")):
            try:
                load_demo()
                st.rerun()
            except Exception as exc:
                show_error(exc)
        st.caption(
            "Preloaded when the app opens. Fictional 1–7 experience items plus satisfaction and a 0–10 "
            "recommendation score; click to restore it after an upload."
        )

        st.markdown("### Or bring your own survey")
        data_epoch = st.session_state[k("data_epoch")]
        upload = st.file_uploader(
            "CSV, Excel, or JSON",
            type=["csv", "xlsx", "xls", "xlsm", "json"],
            key=k(f"survey_upload_{data_epoch}"),
        )
        if upload is not None:
            try:
                _load_upload(upload)
            except Exception as exc:
                show_error(exc)
        if st.session_state.get(k("tables")):
            names = list(st.session_state[k("tables")])
            current = st.session_state[k("active_table")]
            selected = st.selectbox(
                "Table / sheet",
                names,
                index=names.index(current),
                key=k(f"table_select_{data_epoch}"),
            )
            if selected != current:
                st.session_state[k("active_table")] = selected
                st.session_state[k("data_epoch")] += 1
                _clear_analysis()
                st.rerun()
            st.caption(f"Loaded locally: {st.session_state[k('source_name')]}")
            if full_width(st.button, "Clear survey", type="secondary", key=k("clear_survey")):
                st.session_state[k("tables")] = None
                st.session_state[k("active_table")] = None
                st.session_state[k("source_name")] = None
                st.session_state[k("source_fingerprint")] = None
                st.session_state[k("upload_seen")] = None
                st.session_state[k("data_epoch")] += 1
                _clear_analysis()
                go_to("Welcome")
                st.rerun()

        st.markdown("### Follow the workflow")
        # A page switch requested by a button or a fresh upload is applied here, before the selector is drawn.
        target = st.session_state.pop(k("nav_target"), None)
        if target in PAGES:
            st.session_state[k("page")] = target
        page = st.radio("Page", list(PAGES), key=k("page"), label_visibility="collapsed")
    return page


def render() -> None:
    """Draw the whole Driver Signal app on the current page. Never calls st.set_page_config or st.navigation."""
    sig.apply(NS)
    _ensure_state()
    page = _sidebar()
    sig.masthead(NS, MASTHEAD_PROMISES, MASTHEAD_KICKER)
    try:
        PAGES[page]()
    except Exception as exc:
        show_error(exc)
    sig.footer(NS, __version__, FOOTER_LINE)
