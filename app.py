from __future__ import annotations

import os

# Keep Streamlit/Arrow serialization stable on macOS. This must be set early.
os.environ.setdefault("ARROW_DEFAULT_MEMORY_POOL", "system")

import base64
import hashlib
import html
import inspect
import json
import platform
from pathlib import Path
import sys
import traceback

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import statsmodels
import streamlit as st


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from driversignal import __version__
from driversignal.analysis import SurveyAnalysis, analyze_survey
from driversignal.errors import DataProblem, friendly_message
from driversignal.io import load_data, results_to_excel, results_to_json, tables_to_csv_zip
from driversignal.plotting import coefficient_figure, fitted_figure, importance_figure, reliability_figure
from driversignal.reporting import privacy_safe_influence
from driversignal.validation import default_item_spec, infer_column, numeric_candidates


PAGES = [
    "Welcome",
    "1 · Data & scales",
    "2 · Reliability",
    "3 · Driver model",
    "4 · Interpret & export",
    "Methods & limits",
]
COLORS = {
    "ink": "#17322E",
    "deep": "#102C2A",
    "teal": "#173C3A",
    "coral": "#D95B40",
    "mint": "#83D2B4",
    "gold": "#F2C66D",
    "paper": "#F8F5ED",
    "muted": "#59716C",
}
ASSOCIATION_NOTE = (
    "**Driver means measured association here—not proven cause.** A cross-sectional survey can prioritize questions "
    "and experiments, but respondent selection, common-method bias, omitted variables, and reverse direction can all "
    "produce a strong-looking relationship."
)
mark_path = ROOT / "assets" / "driversignal-mark.svg"
MARK_URI = (
    "data:image/svg+xml;base64," + base64.b64encode(mark_path.read_bytes()).decode("ascii")
    if mark_path.exists()
    else ""
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


st.set_page_config(page_title="DriverSignal | Survey driver analysis", page_icon="↗", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --ds-ink:#17322e; --ds-deep:#102c2a; --ds-teal:#173c3a;
        --ds-coral:#d95b40; --ds-mint:#83d2b4; --ds-gold:#f2c66d;
        --ds-paper:#f8f5ed; --ds-line:rgba(23,50,46,.14);
    }
    [data-testid="stAppViewContainer"] {
        background:radial-gradient(circle at 94% 2%,rgba(242,198,109,.18),transparent 27rem),
                   radial-gradient(circle at 2% 92%,rgba(131,210,180,.13),transparent 25rem),
                   linear-gradient(180deg,#fbf9f3 0%,var(--ds-paper) 100%);
    }
    [data-testid="stHeader"] { background:rgba(248,245,237,.78); }
    [data-testid="stSidebar"] { background:linear-gradient(165deg,#173c3a 0%,#102c2a 65%,#0c2422 100%); }
    [data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] span { color:#f8f5ed; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color:#b9cbc5; }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] {
        background:rgba(255,255,255,.06); border-color:rgba(131,210,180,.32);
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small,
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small span { color:#b9cbc5 !important; }
    [data-testid="stSidebar"] [data-testid="stButton"] button {
        background:rgba(255,255,255,.08); color:#f8f5ed !important; border-color:rgba(255,255,255,.23);
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button:hover {
        background:rgba(131,210,180,.16); border-color:rgba(131,210,180,.48);
    }
    [data-testid="stSidebar"] [data-testid="stButton"] button * { color:#f8f5ed !important; }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button {
        background:#f8f5ed; color:#17322e !important;
    }
    [data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] button * { color:#17322e !important; }
    .block-container { max-width:1240px; padding-top:4.4rem; padding-bottom:4rem; }
    h1,h2,h3 { color:var(--ds-ink); letter-spacing:-.025em; }
    a { color:#9b3e2b; }
    [data-testid="stMetric"] {
        background:rgba(255,255,255,.75); border:1px solid var(--ds-line); border-radius:16px;
        padding:1rem 1.05rem; box-shadow:0 8px 28px rgba(23,50,46,.045);
    }
    [data-testid="stMetricValue"] { color:var(--ds-ink); font-size:clamp(1.45rem,2.3vw,1.95rem); }
    .stButton > button[kind="primary"] {
        background:linear-gradient(135deg,#e26748,#c94c34); color:white; border:0;
        box-shadow:0 8px 20px rgba(217,91,64,.22); font-weight:750;
    }
    .stButton > button[kind="primary"]:hover { background:linear-gradient(135deg,#c94c34,#b63f2b); color:white; }
    button:focus-visible,a:focus-visible,input:focus-visible { outline:3px solid #f2c66d !important; outline-offset:2px; }
    [data-testid="stExpander"],[data-testid="stAlert"],[data-testid="stVerticalBlockBorderWrapper"] { border-radius:14px; }
    .ds-brand { padding:.25rem 0 1.1rem; }
    .ds-lockup { display:flex; align-items:center; gap:.65rem; }
    .ds-mark { width:38px; height:38px; }
    .ds-name { color:white; font-size:1.28rem; line-height:1; font-weight:850; letter-spacing:-.04em; }
    .ds-name span { color:#f2c66d !important; }
    .ds-tag { margin:.55rem 0 0 !important; color:#b9cbc5 !important; font-size:.77rem; line-height:1.4; }
    .ds-masthead {
        display:flex; justify-content:space-between; align-items:center; gap:1rem; padding:.72rem 1rem .72rem .78rem;
        margin-bottom:1.35rem; background:rgba(255,255,255,.65); border:1px solid var(--ds-line);
        border-radius:18px; box-shadow:0 10px 36px rgba(23,50,46,.05);
    }
    .ds-masthead .ds-mark { width:48px; height:48px; }
    .ds-wordmark { color:var(--ds-ink); font-weight:850; letter-spacing:-.045em; font-size:1.55rem; line-height:1; }
    .ds-wordmark span { color:var(--ds-coral); }
    .ds-kicker { margin-top:.32rem; color:#59716c; font-size:.67rem; font-weight:800; letter-spacing:.13em; }
    .ds-promise { color:#47645e; font-size:.78rem; font-weight:700; white-space:nowrap; }
    .ds-promise span { color:var(--ds-coral); padding:0 .3rem; }
    .ds-hero {
        position:relative; overflow:hidden; padding:clamp(1.7rem,4vw,3.4rem); margin-bottom:1.3rem;
        background:linear-gradient(135deg,#173c3a 0%,#102c2a 75%); border-radius:26px;
        box-shadow:0 18px 50px rgba(23,50,46,.17);
    }
    .ds-hero:after {
        content:""; position:absolute; width:330px; height:330px; right:-102px; top:-150px;
        border-radius:50%; border:54px solid rgba(242,198,109,.12);
    }
    .ds-eyebrow { color:#83d2b4; font-size:.72rem; font-weight:850; letter-spacing:.16em; }
    .ds-hero h1 { color:white; font-size:clamp(2.25rem,5vw,4.7rem); line-height:.97; margin:.75rem 0 1rem; max-width:940px; }
    .ds-hero h1 em { color:#f2c66d; font-style:normal; }
    .ds-hero p { color:#d7e3df; font-size:1.06rem; line-height:1.6; max-width:810px; }
    .ds-pills { display:flex; flex-wrap:wrap; gap:.55rem; margin-top:1.15rem; }
    .ds-pill {
        padding:.4rem .72rem; border:1px solid rgba(255,255,255,.16); border-radius:999px;
        color:#f8f5ed; font-size:.78rem; font-weight:700; background:rgba(255,255,255,.055);
    }
    .ds-step,.ds-insight {
        height:100%; padding:1.2rem 1.2rem 1rem; background:rgba(255,255,255,.66);
        border:1px solid var(--ds-line); border-radius:18px;
    }
    .ds-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1rem; }
    .ds-step b,.ds-insight b { color:var(--ds-coral); font-size:.72rem; letter-spacing:.12em; }
    .ds-step h3,.ds-insight h3 { margin:.4rem 0 .5rem; }
    .ds-step p,.ds-insight p { color:#59716c; font-size:.9rem; line-height:1.55; }
    .ds-note {
        padding:1rem 1.1rem; margin:.75rem 0 1rem; border-left:4px solid var(--ds-mint);
        background:rgba(255,255,255,.62); border-radius:0 14px 14px 0; color:#47645e;
    }
    .ds-callout {
        padding:1.1rem 1.25rem; margin:1rem 0; background:linear-gradient(135deg,rgba(242,198,109,.20),rgba(255,255,255,.66));
        border:1px solid rgba(217,91,64,.18); border-radius:16px; color:#36534e;
    }
    .ds-footer { margin-top:3.2rem; padding-top:1rem; border-top:1px solid var(--ds-line); color:#617670; font-size:.76rem; text-align:center; }
    .ds-footer span { color:var(--ds-coral); padding:0 .38rem; }
    @media (max-width:1050px) { .ds-grid{grid-template-columns:1fr} }
    @media (max-width:760px) { .ds-promise{display:none}.ds-hero{border-radius:20px}.block-container{padding-top:3.5rem} }
    @media (prefers-reduced-motion:reduce) { * { scroll-behavior:auto !important; transition:none !important; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def show_error(exc: Exception) -> None:
    st.error(friendly_message(exc))
    if not isinstance(exc, (DataProblem, ValueError)) and os.getenv("DRIVERSIGNAL_DEBUG") == "1":
        with st.expander("Technical details"):
            st.code("".join(traceback.format_exception(exc)))


def masthead() -> None:
    image = f'<img class="ds-mark" src="{MARK_URI}" alt="DriverSignal rising-bars mark"/>' if MARK_URI else "↗"
    st.markdown(
        f"""
        <div class="ds-masthead"><div class="ds-lockup">{image}
        <div><div class="ds-wordmark">Driver<span>Signal</span></div>
        <div class="ds-kicker">OPEN SURVEY DRIVER ANALYSIS</div></div></div>
        <div class="ds-promise">Local-first <span>•</span> Explainable <span>•</span> Open source</div></div>
        """,
        unsafe_allow_html=True,
    )


def footer() -> None:
    st.markdown(
        f"<div class='ds-footer'>DriverSignal v{__version__}<span>◆</span>Associations to investigate, not causal proof"
        "<span>◆</span>Part of the Signal suite<span>◆</span>AGPL-3.0-or-later</div>",
        unsafe_allow_html=True,
    )


def go_to(page_name: str) -> None:
    st.session_state["nav_target"] = page_name
    st.session_state["nav_epoch"] = int(st.session_state["nav_epoch"]) + 1


def _fingerprint(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _setup_signature(spec: pd.DataFrame, settings: dict[str, object]) -> str:
    """Fingerprint every setting that can change a saved analysis."""
    payload = {**settings, "item_spec": json.loads(spec.to_json(orient="records"))}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clear_analysis() -> None:
    st.session_state["analysis"] = None
    st.session_state["analysis_config"] = None
    st.session_state["item_spec"] = None
    st.session_state["spec_signature"] = None
    st.session_state["editor_epoch"] = int(st.session_state.get("editor_epoch", 0)) + 1


def _set_loaded(tables: dict[str, pd.DataFrame], source_name: str, fingerprint: str) -> None:
    st.session_state["tables"] = tables
    st.session_state["active_table"] = next(iter(tables))
    st.session_state["source_name"] = source_name
    st.session_state["source_fingerprint"] = fingerprint
    st.session_state["data_epoch"] = int(st.session_state.get("data_epoch", 0)) + 1
    _clear_analysis()


def load_demo() -> None:
    path = ROOT / "examples" / "demo_customer_experience_survey.csv"
    raw = path.read_bytes()
    loaded = load_data(raw, name=path.name)
    _set_loaded(loaded.tables, loaded.source_name, _fingerprint(raw))
    go_to("1 · Data & scales")


def _load_upload(uploaded) -> None:
    raw = uploaded.getvalue()
    fingerprint = _fingerprint(raw)
    if st.session_state.get("upload_seen") == fingerprint:
        return
    loaded = load_data(raw, name=uploaded.name)
    st.session_state["upload_seen"] = fingerprint
    _set_loaded(loaded.tables, loaded.source_name, fingerprint)
    go_to("1 · Data & scales")


def active_frame() -> pd.DataFrame | None:
    tables = st.session_state.get("tables")
    table = st.session_state.get("active_table")
    return tables.get(table) if tables and table in tables else None


for key, default in (
    ("nav_target", PAGES[0]),
    ("nav_epoch", 0),
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
):
    st.session_state.setdefault(key, default)


with st.sidebar:
    image = f'<img class="ds-mark" src="{MARK_URI}" alt="DriverSignal mark"/>' if MARK_URI else "↗"
    st.markdown(
        f"<div class='ds-brand'><div class='ds-lockup'>{image}<div class='ds-name'>Driver<span>Signal</span></div></div>"
        "<p class='ds-tag'>Survey ratings in. Reliable constructs and challengeable priorities out.</p></div>",
        unsafe_allow_html=True,
    )
    st.markdown("### Start with a worked example")
    if full_width(st.button, "Demo · customer experience"):
        try:
            load_demo()
            st.rerun()
        except Exception as exc:
            show_error(exc)
    st.caption("Fictional 1–7 experience items plus satisfaction and a 0–10 recommendation score.")

    st.markdown("### Or bring your own survey")
    upload = st.file_uploader(
        "CSV, Excel, or JSON",
        type=["csv", "xlsx", "xls", "xlsm", "json"],
        key=f"survey_upload_{st.session_state['data_epoch']}",
    )
    if upload is not None:
        try:
            _load_upload(upload)
        except Exception as exc:
            show_error(exc)
    if st.session_state.get("tables"):
        names = list(st.session_state["tables"])
        current = st.session_state["active_table"]
        selected = st.selectbox("Table / sheet", names, index=names.index(current))
        if selected != current:
            st.session_state["active_table"] = selected
            st.session_state["data_epoch"] += 1
            _clear_analysis()
            st.rerun()
        st.caption(f"Loaded locally: {st.session_state['source_name']}")
        if full_width(st.button, "Clear survey", type="secondary"):
            st.session_state["tables"] = None
            st.session_state["active_table"] = None
            st.session_state["source_name"] = None
            st.session_state["source_fingerprint"] = None
            st.session_state["upload_seen"] = None
            st.session_state["data_epoch"] += 1
            _clear_analysis()
            go_to("Welcome")
            st.rerun()

    st.markdown("### Follow the workflow")
    page = st.radio(
        "Page",
        PAGES,
        index=PAGES.index(st.session_state["nav_target"]),
        key=f"nav_radio_{st.session_state['nav_epoch']}",
        label_visibility="collapsed",
    )
    st.session_state["nav_target"] = page

masthead()


def welcome_page() -> None:
    st.markdown(
        """
        <section class="ds-hero">
          <div class="ds-eyebrow">SURVEY DRIVER ANALYSIS, WITHOUT THE BLACK BOX</div>
          <h1>Find what moves with satisfaction.<br><em>Then test what truly moves it.</em></h1>
          <p>Turn respondent-level ratings into a ranked driver map, robust coefficient intervals, model-health checks,
          and honest scale-reliability diagnostics. The quick read is built for marketers; every assumption remains
          visible for analysts.</p>
          <div class="ds-pills"><span class="ds-pill">Satisfaction or NPS</span><span class="ds-pill">Cronbach's alpha</span>
          <span class="ds-pill">LMG / Shapley importance</span><span class="ds-pill">HC3 robust intervals</span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )
    st.warning(ASSOCIATION_NOTE)
    cards = [
        ("01 · DEFINE", "Build the right constructs", "Group related items, mark reverse-keyed questions, and keep the scoring rule explicit."),
        ("02 · CHECK", "Challenge the measurement", "Read alpha, item–total correlation, alpha-if-deleted, missingness, and inter-item correlation together."),
        ("03 · PRIORITIZE", "Separate importance from direction", "Allocate shared R² fairly with LMG/Shapley, then use standardized betas for conditional direction."),
    ]
    html = "".join(
        f"<article class='ds-step'><b>{number}</b><h3>{title}</h3><p>{body}</p></article>"
        for number, title, body in cards
    )
    st.markdown(f"<div class='ds-grid'>{html}</div>", unsafe_allow_html=True)
    st.write("")
    columns = st.columns(4)
    columns[0].metric("Input", "1 row / respondent")
    columns[1].metric("NPS model", "Original 0–10")
    columns[2].metric("Uncertainty", "HC3 robust")
    columns[3].metric("Data path", "Local only")
    st.markdown(
        "<div class='ds-note'><b>Two reading speeds.</b> Start with the ranked priority view and plain-language brief. "
        "Open the model, VIF, reliability, retention, and residual tables when the decision deserves an audit.</div>",
        unsafe_allow_html=True,
    )
    if st.button("Open the fictional survey", type="primary"):
        try:
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
    st.title("Data, outcome & scale setup")
    frame = active_frame()
    if frame is None:
        st.info("Load the fictional survey in the sidebar, or upload one row per respondent.")
        template_csv = ROOT / "examples" / "survey_template.csv"
        template_xlsx = ROOT / "examples" / "survey_template.xlsx"
        left, right = st.columns(2)
        full_width(
            left.download_button,
            "Download CSV template",
            template_csv.read_bytes(),
            "driversignal_survey_template.csv",
            "text/csv",
        )
        full_width(
            right.download_button,
            "Download Excel template + setup example",
            template_xlsx.read_bytes(),
            "driversignal_survey_template.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        return

    numeric = numeric_candidates(frame)
    if len(numeric) < 2:
        st.error("This table needs one numeric outcome and at least one numeric survey item.")
        return
    missing_cells = int(frame.isna().sum().sum())
    columns = st.columns(4)
    columns[0].metric("Respondents", f"{len(frame):,}")
    columns[1].metric("Columns", f"{frame.shape[1]:,}")
    columns[2].metric("Numeric candidates", f"{len(numeric):,}")
    columns[3].metric("Missing cells", f"{missing_cells:,}")
    st.caption("DriverSignal reads the selected table in memory. It does not upload it or modify the source file.")

    tabs = st.tabs(["Set up analysis", "Preview & privacy"])
    with tabs[0]:
        nps_named = [column for column in numeric if any(token in column.lower() for token in ("recommend", "nps"))]
        guess = nps_named[0] if nps_named else infer_column(numeric, ("satisfaction", "satisfied", "overall"))
        outcome = st.selectbox(
            "Outcome to explain",
            numeric,
            index=numeric.index(guess),
            key=f"outcome_{st.session_state['data_epoch']}",
            help="Use the respondent's original satisfaction or 0–10 recommendation response—not an aggregate NPS value.",
        )
        role_key = f"{st.session_state['data_epoch']}_{hashlib.sha256(outcome.encode('utf-8')).hexdigest()[:10]}"
        likely_nps = any(token in outcome.lower() for token in ("recommend", "nps"))
        outcome_kind = st.radio(
            "Outcome interpretation",
            ["NPS (0–10 recommendation)", "Satisfaction / other numeric rating"],
            index=0 if likely_nps else 1,
            horizontal=True,
            key=f"outcome_kind_{role_key}",
        )
        available_items = [column for column in numeric if column != outcome]
        selected_items = st.multiselect(
            "Survey items to use",
            available_items,
            default=_default_driver_items(frame, numeric, outcome),
            key=f"driver_items_{role_key}",
            help="Items assigned the same scale become one mean construct. Blank scale names stay as standalone drivers.",
        )
        signature = (st.session_state.get("source_fingerprint"), st.session_state.get("active_table"), tuple(selected_items))
        if st.session_state.get("spec_signature") != signature:
            st.session_state["item_spec"] = default_item_spec(selected_items)
            st.session_state["spec_signature"] = signature
            st.session_state["editor_epoch"] += 1
            st.session_state["analysis"] = None
            st.session_state["analysis_config"] = None

        st.markdown("#### Item setup")
        st.caption(
            "Edit the display label or construct name. Check reverse-scored only when theory and wording require it; "
            "DriverSignal never guesses beyond an obvious column-name hint."
        )
        spec = st.session_state.get("item_spec")
        if spec is None or spec.empty:
            st.info("Choose at least one numeric survey item.")
            return
        edited_spec = full_width(
            st.data_editor,
            spec,
            hide_index=True,
            num_rows="fixed",
            disabled=["item"],
            key=f"item_editor_{st.session_state['editor_epoch']}",
            column_config={
                "item": st.column_config.TextColumn("Source item"),
                "label": st.column_config.TextColumn("Readable label"),
                "scale": st.column_config.TextColumn("Scale / construct", help="Same non-empty name = one mean score"),
                "reverse_scored": st.column_config.CheckboxColumn("Reverse scored"),
            },
        )

        left, middle, right = st.columns(3)
        scale_minimum = left.number_input("Item scale minimum", value=1.0, step=1.0)
        scale_maximum = middle.number_input("Item scale maximum", value=7.0, step=1.0)
        completion_label = right.selectbox(
            "Answers needed per construct",
            ["All items", "At least 80%", "At least two-thirds"],
            index=0,
            help="This affects construct means. The final regression still uses one shared complete-case sample.",
        )
        completion_map = {"All items": 1.0, "At least 80%": 0.80, "At least two-thirds": 2.0 / 3.0}
        with st.expander("Advanced reproducibility settings"):
            confidence_percent = st.select_slider("Coefficient confidence level", options=[90, 95, 99], value=95)
            alpha_bootstrap = st.selectbox(
                "Alpha bootstrap repetitions",
                [0, 200, 400, 1000],
                index=2,
                format_func=lambda value: "Skip interval" if value == 0 else f"{value:,}",
            )
            importance_permutations = st.selectbox(
                "Approximate importance permutations (only above 10 drivers)", [500, 1000, 2000, 5000], index=2
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
        saved_config = st.session_state.get("analysis_config") or {}
        if st.session_state.get("analysis") is not None and saved_config.get("setup_signature") != setup_signature:
            st.session_state["analysis"] = None
            st.session_state["analysis_config"] = None
            st.info("The setup changed. Run the analysis again before using reliability, driver, or export results.")

        st.warning(ASSOCIATION_NOTE)
        if st.button("Analyze survey", type="primary"):
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
                st.session_state["analysis"] = analysis
                st.session_state["item_spec"] = edited_spec.copy()
                st.session_state["analysis_config"] = {**current_settings, "setup_signature": setup_signature}
                go_to("2 · Reliability")
                st.rerun()
            except Exception as exc:
                show_error(exc)

    with tabs[1]:
        st.markdown("#### Source preview")
        full_width(st.dataframe, frame.head(50), hide_index=True)
        st.markdown(
            "<div class='ds-callout'><b>Before uploading respondent data:</b> remove names, email addresses, phone numbers, "
            "free-text comments, direct customer IDs, and columns you do not need. Small groups and unusual combinations "
            "can still re-identify people even without a name.</div>",
            unsafe_allow_html=True,
        )
        missing = pd.DataFrame(
            {
                "column": frame.columns,
                "missing_rows": [int(frame[column].isna().sum()) for column in frame],
                "missing_percent": [float(frame[column].isna().mean() * 100) for column in frame],
                "unique_values": [int(frame[column].nunique(dropna=True)) for column in frame],
            }
        ).sort_values("missing_percent", ascending=False)
        full_width(st.dataframe, missing, hide_index=True)


def _analysis_or_prompt() -> SurveyAnalysis | None:
    analysis = st.session_state.get("analysis")
    if analysis is None:
        st.info("Set up and run an analysis on page 1 first.")
        if st.button("Go to data & scales"):
            go_to("1 · Data & scales")
            st.rerun()
        return None
    return analysis


def reliability_page() -> None:
    st.title("Scale reliability")
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
            full_width(st.plotly_chart, reliability_figure(analysis.scale_summary), config={"displaylogo": False})
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
    if st.button("Continue to driver model", type="primary"):
        go_to("3 · Driver model")
        st.rerun()


def _metric(result, name: str) -> float:
    values = result.metrics.loc[result.metrics["metric"].eq(name), "value"]
    return float(values.iloc[0]) if len(values) else float("nan")


def driver_page() -> None:
    st.title("Driver priorities & conditional associations")
    analysis = _analysis_or_prompt()
    if analysis is None:
        return
    result = analysis.driver_result
    st.warning(ASSOCIATION_NOTE)
    retained = int(_metric(result, "Usable respondents"))
    r2 = _metric(result, "R-squared")
    cv_r2 = _metric(result, "Five-fold CV R-squared")
    rmse = _metric(result, "RMSE")
    columns = st.columns(4)
    columns[0].metric("Usable respondents", f"{retained:,}")
    columns[1].metric("Model R²", f"{r2:.3f}")
    columns[2].metric("Five-fold CV R²", f"{cv_r2:.3f}" if np.isfinite(cv_r2) else "Not available")
    columns[3].metric("RMSE", f"{rmse:.2f}")

    top = result.importance.iloc[0]
    if result.inference_valid:
        direction_word = "positive" if top["standardized_beta"] >= 0 else "negative"
        callout = (
            f"<div class='ds-callout'><b>First measured priority: {html.escape(str(top['driver']))}.</b> It receives "
            f"{top['r2_contribution']:.3f} R², or {top['share_of_explained_percent']:.1f}% of the variation this model "
            f"explains. Its conditional association is {direction_word} (standardized β "
            f"{top['standardized_beta']:+.2f}). Use this to frame a hypothesis and a bounded test—not as proof of a "
            "lever.</div>"
        )
    else:
        callout = (
            f"<div class='ds-callout'><b>Shared model fit only: {html.escape(str(top['driver']))} receives the largest diagnostic "
            f"importance allocation ({top['share_of_explained_percent']:.1f}% of explained variance).</b> The predictor "
            "matrix is rank-deficient, so DriverSignal suppresses individual directions and intervals. Revise overlapping "
            "or duplicate drivers before making a priority claim.</div>"
        )
    st.markdown(callout, unsafe_allow_html=True)
    st.subheader("Priority when drivers overlap")
    full_width(
        st.plotly_chart,
        importance_figure(result.importance, show_direction=result.inference_valid),
        config={"displaylogo": False},
    )
    direction_note = "; direction comes from beta" if result.inference_valid else "; direction is suppressed"
    st.caption(result.importance_method + ". Importance shares sum to the full model R²" + direction_note + ".")
    st.subheader("Conditional direction & uncertainty")
    confidence = int(st.session_state.get("analysis_config", {}).get("confidence_percent", 95))
    if not result.inference_valid:
        st.error(
            "The predictor matrix is rank-deficient. Individual coefficients and intervals are not uniquely identified, "
            "so this chart is withheld. Remove or combine duplicate and perfectly overlapping drivers, then analyze again."
        )
    else:
        full_width(st.plotly_chart, coefficient_figure(result.coefficients, confidence), config={"displaylogo": False})

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
        full_width(st.plotly_chart, fitted_figure(result.fitted), config={"displaylogo": False})
        st.caption("Color highlights Cook's-distance influence. A flag is a sensitivity prompt, not proof that a row is wrong.")
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
    if st.button("Build decision brief & export", type="primary"):
        go_to("4 · Interpret & export")
        st.rerun()


def _manifest(analysis: SurveyAnalysis) -> tuple[pd.DataFrame, dict[str, object]]:
    config = st.session_state.get("analysis_config") or {}
    result = analysis.driver_result
    metadata: dict[str, object] = {
        "product": "DriverSignal",
        "version": __version__,
        "source_name": st.session_state.get("source_name"),
        "source_table": st.session_state.get("active_table"),
        "source_sha256": st.session_state.get("source_fingerprint"),
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
        "alpha_sample": "Listwise complete within each scale",
        "alpha_bootstrap_repetitions": config.get("alpha_bootstrap_repetitions"),
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


def decision_page() -> None:
    st.title("Decision brief & evidence pack")
    analysis = _analysis_or_prompt()
    if analysis is None:
        return
    result = analysis.driver_result
    st.warning(ASSOCIATION_NOTE)

    if not analysis.nps_composition.empty:
        nps_row = analysis.outcome_summary.loc[analysis.outcome_summary["metric"].eq("NPS")]
        nps_value = float(nps_row["value"].iloc[0]) if len(nps_row) else float("nan")
        columns = st.columns(4)
        columns[0].metric("NPS", f"{nps_value:+.1f}")
        for index, row in enumerate(analysis.nps_composition.itertuples(index=False), start=1):
            columns[index].metric(row.category.split(" (")[0], f"{row.percent:.1f}%", f"n={int(row.respondents):,}")
        figure = go.Figure(
            go.Bar(
                x=analysis.nps_composition["category"],
                y=analysis.nps_composition["percent"],
                marker_color=[COLORS["coral"], COLORS["gold"], COLORS["teal"]],
                text=analysis.nps_composition["percent"].map(lambda value: f"{value:.1f}%"),
                textposition="outside",
                hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
            )
        )
        figure.update_layout(
            height=330,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,.46)",
            font=dict(color=COLORS["ink"]),
            margin=dict(l=55, r=30, t=20, b=55),
            yaxis=dict(title="Respondents (%)", gridcolor="rgba(23,50,46,.10)", range=[0, max(55, float(analysis.nps_composition["percent"].max()) * 1.2)]),
            xaxis=dict(title=None),
            showlegend=False,
        )
        full_width(st.plotly_chart, figure, config={"displaylogo": False})

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

        top_three = brief.head(3)
        cards = "".join(
            f"<article class='ds-insight'><b>PRIORITY {int(row.importance_rank):02d}</b><h3>{html.escape(str(row.driver))}</h3>"
            f"<p>{row.share_of_explained_percent:.1f}% of explained variance · β {row.standardized_beta:+.2f}. "
            f"{html.escape(str(row.decision_prompt))}</p></article>"
            for row in top_three.itertuples(index=False)
        )
        st.markdown(f"<div class='ds-grid'>{cards}</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='ds-note'><b>A disciplined next step:</b> combine this priority map with reach, feasibility, "
            "cost, and customer verbatims; pre-register the outcome and test a bounded intervention. Re-run the survey "
            "and model after implementation instead of turning the first ranking into a permanent scorecard.</div>",
            unsafe_allow_html=True,
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
        tables, metadata = _evidence_tables(analysis)
        excel = results_to_excel(tables)
        csv_zip = tables_to_csv_zip(tables)
        json_bytes = results_to_json(tables, metadata)
        columns = st.columns(3)
        full_width(
            columns[0].download_button,
            "Excel evidence pack",
            excel,
            "driversignal_evidence_pack.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        full_width(
            columns[1].download_button,
            "Accessible CSV tables",
            csv_zip,
            "driversignal_evidence_tables.zip",
            "application/zip",
        )
        full_width(
            columns[2].download_button,
            "JSON + audit trail",
            json_bytes,
            "driversignal_evidence.json",
            "application/json",
        )
        with st.expander("Evidence-pack contents"):
            full_width(st.dataframe, pd.DataFrame({"table": list(tables), "rows": [len(table) for table in tables.values()]}), hide_index=True)
    except Exception as exc:
        show_error(exc)


def methods_page() -> None:
    st.title("Methods, assumptions & limits")
    st.warning(ASSOCIATION_NOTE)
    tabs = st.tabs(["Plain-language method", "Reliability mathematics", "Driver mathematics", "Limits & references"])
    with tabs[0]:
        st.markdown(
            """
            1. **Keep one row per respondent.** Select the original satisfaction rating or 0–10 recommendation response.
            2. **Define constructs before modeling.** Group items that theory says measure the same thing. Reverse only
               explicitly reverse-keyed wording against declared theoretical endpoints.
            3. **Score transparently.** DriverSignal averages answered items when the declared completion rule is met.
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
        st.markdown("DriverSignal standardizes the outcome and predictors, then estimates:")
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
        st.markdown("For standard NPS, DriverSignal reports:")
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


ROUTES = {
    "Welcome": welcome_page,
    "1 · Data & scales": data_page,
    "2 · Reliability": reliability_page,
    "3 · Driver model": driver_page,
    "4 · Interpret & export": decision_page,
    "Methods & limits": methods_page,
}

ROUTES[page]()
footer()
