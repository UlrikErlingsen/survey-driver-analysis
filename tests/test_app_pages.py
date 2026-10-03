from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / "app.py"
PAGES = [
    "Welcome",
    "1 · Data & scales",
    "2 · Reliability",
    "3 · Driver model",
    "4 · Interpret & export",
    "Methods & limits",
]


def _button(buttons, label: str):
    return next(button for button in buttons if button.label == label)


# Runs the app, but first applies a simulated upload when the test asks for one
# (AppTest cannot drive st.file_uploader). The upload goes through the app's own upload handler.
UPLOAD_SCRIPT = """
import io

import pandas as pd
import streamlit as st

from driversignal.examples import demo_csv_bytes
from driversignal.ui import app as ui

if st.session_state.pop("driver:test_upload", False):
    frame = pd.read_csv(io.BytesIO(demo_csv_bytes())).head(200).drop(columns=["region"])

    class Upload:
        name = "my_survey.csv"

        def getvalue(self):
            return frame.to_csv(index=False).encode("utf-8")

    ui._load_upload(Upload())
ui.render()
"""


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_on_first_open(page: str) -> None:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception, [error.value for error in app.exception]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_data(page: str) -> None:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    _button(app.sidebar.button, "Clear survey").click().run()
    assert app.session_state["driver:tables"] is None
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["driver:tables"] is None  # a cleared session is not preloaded again


def test_fresh_session_opens_with_the_fictional_demo_preloaded() -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["driver:page"] == "Welcome"
    assert app.session_state["driver:source_name"] == "demo_customer_experience_survey.csv"
    notes = "\n".join(str(item.value) for item in app.markdown)
    assert "fictional demo survey is already loaded" in notes
    assert any(caption.value.startswith("Loaded locally: demo_customer") for caption in app.sidebar.caption)

    _button(app.button, "Open the fictional survey").click().run()
    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["driver:page"] == "1 · Data & scales"
    respondents = next(metric for metric in app.metric if metric.label == "Respondents")
    assert respondents.value == "520"
    outcome = next(widget for widget in app.selectbox if widget.label == "Outcome to explain")
    assert outcome.value == "recommend_0_10"


def test_upload_replaces_the_preloaded_demo_and_the_demo_button_restores_it() -> None:
    app = AppTest.from_string(UPLOAD_SCRIPT, default_timeout=90)
    app.run()
    assert app.session_state["driver:source_name"] == "demo_customer_experience_survey.csv"

    app.session_state["driver:test_upload"] = True
    app.run()
    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["driver:source_name"] == "my_survey.csv"
    assert app.session_state["driver:page"] == "1 · Data & scales"
    respondents = next(metric for metric in app.metric if metric.label == "Respondents")
    assert respondents.value == "200"

    app.sidebar.radio[0].set_value("Welcome").run()
    notes = "\n".join(str(item.value) for item in app.markdown)
    assert "fictional demo survey is already loaded" not in notes

    _button(app.sidebar.button, "Demo · customer experience").click().run()
    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["driver:source_name"] == "demo_customer_experience_survey.csv"
    respondents = next(metric for metric in app.metric if metric.label == "Respondents")
    assert respondents.value == "520"


def test_demo_loads_nps_setup_and_expected_items() -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    _button(app.sidebar.button, "Demo · customer experience").click().run()
    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["driver:page"] == "1 · Data & scales"
    outcome = next(widget for widget in app.selectbox if widget.label == "Outcome to explain")
    assert outcome.value == "recommend_0_10"
    interpretation = next(widget for widget in app.radio if widget.label == "Outcome interpretation")
    assert interpretation.value == "NPS (0–10 recommendation)"
    items = next(widget for widget in app.multiselect if widget.label == "Survey items to use")
    assert len(items.value) == 12


def test_changing_outcome_resets_compatible_roles() -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    _button(app.sidebar.button, "Demo · customer experience").click().run()
    outcome = next(widget for widget in app.selectbox if widget.label == "Outcome to explain")
    outcome.set_value("satisfaction_1_7").run()
    assert not app.exception, [error.value for error in app.exception]
    interpretation = next(widget for widget in app.radio if widget.label == "Outcome interpretation")
    assert interpretation.value == "Satisfaction / other numeric rating"
    items = next(widget for widget in app.multiselect if widget.label == "Survey items to use")
    assert "satisfaction_1_7" not in items.value


def test_demo_analysis_runs_reliability_driver_and_export_pages() -> None:
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()
    _button(app.sidebar.button, "Demo · customer experience").click().run()
    _button(app.button, "Analyze survey").click().run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["driver:page"] == "2 · Reliability"
    analysis = app.session_state["driver:analysis"]
    assert analysis is not None
    assert analysis.driver_result.importance.iloc[0]["driver"] == "Service"
    assert [metric.label for metric in app.metric] == ["Service", "Value", "Ease", "Trust"]
    assert len(app.get("plotly_chart")) == 1

    app.sidebar.radio[0].set_value("3 · Driver model").run()
    assert not app.exception, [error.value for error in app.exception]
    assert len(app.get("plotly_chart")) == 3
    assert [tab.label for tab in app.tabs] == ["Model health", "Collinearity", "Residual check", "Nerd tables"]

    _button(app.button, "Build decision brief & export").click().run()
    assert not app.exception, [error.value for error in app.exception]
    assert len(app.get("download_button")) == 3
    # The association caution is a Signal warning note on every analysis page.
    cautions = "\n".join(str(item.value) for item in app.markdown if "sg-note warn" in str(item.value))
    assert "proven cause" in cautions.lower()


def test_setup_change_invalidates_saved_analysis() -> None:
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()
    _button(app.sidebar.button, "Demo · customer experience").click().run()
    _button(app.button, "Analyze survey").click().run()
    assert app.session_state["driver:analysis"] is not None

    app.sidebar.radio[0].set_value("1 · Data & scales").run()
    scale_minimum = next(widget for widget in app.number_input if widget.label == "Item scale minimum")
    scale_minimum.set_value(0.0).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["driver:analysis"] is None
    assert app.session_state["driver:analysis_config"] is None
    notices = "\n".join(str(message.value) for message in app.info)
    assert "setup changed" in notices.lower()


def test_methods_page_exposes_formulas_and_limits() -> None:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    app.sidebar.radio[0].set_value("Methods & limits").run()
    assert not app.exception, [error.value for error in app.exception]
    assert [tab.label for tab in app.tabs] == [
        "Plain-language method",
        "Reliability mathematics",
        "Driver mathematics",
        "Limits & references",
    ]
    body = "\n".join(str(markdown.value) for markdown in app.markdown)
    assert "does not establish" in body
    assert "survey weights" in body.lower()
    assert len(app.latex) == 5


def test_sampled_driver_model_is_labelled_on_screen_and_in_exports(monkeypatch: pytest.MonkeyPatch) -> None:
    # Shrink the model row limit (1,000,000 in production) so the labelled sampling path runs on the demo.
    from driversignal import drivers

    defaults = list(drivers.fit_driver_model.__defaults__)
    defaults[-1] = 300
    monkeypatch.setattr(drivers.fit_driver_model, "__defaults__", tuple(defaults))
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()
    _button(app.sidebar.button, "Demo · customer experience").click().run()
    _button(app.button, "Analyze survey").click().run()
    assert not app.exception, [error.value for error in app.exception]

    app.sidebar.radio[0].set_value("3 · Driver model").run()
    assert not app.exception, [error.value for error in app.exception]
    assert any("seeded random sample of 300" in str(message.value) for message in app.info)

    _button(app.button, "Build decision brief & export").click().run()
    assert not app.exception, [error.value for error in app.exception]
    tables = app.session_state["driver:export_cache"][1][0]
    manifest = tables["Manifest"].set_index("field")["value"]
    assert manifest["model_rows"] == 300
    assert "seeded random sample of 300" in manifest["model_sample"]
    assert manifest["alpha_bootstrap_basis"] == "Every complete respondent"
    assert manifest["influence_export_rows"] == "All 300 model rows"
