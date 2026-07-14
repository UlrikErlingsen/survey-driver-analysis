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


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_data(page: str) -> None:
    app = AppTest.from_file(APP, default_timeout=60)
    app.run()
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception, [error.value for error in app.exception]


def test_demo_loads_nps_setup_and_expected_items() -> None:
    app = AppTest.from_file(APP, default_timeout=90)
    app.run()
    _button(app.sidebar.button, "Demo · customer experience").click().run()
    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["nav_target"] == "1 · Data & scales"
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
    assert app.session_state["nav_target"] == "2 · Reliability"
    analysis = app.session_state["analysis"]
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
    cautions = "\n".join(str(warning.value) for warning in app.warning)
    assert "proven cause" in cautions.lower()


def test_setup_change_invalidates_saved_analysis() -> None:
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()
    _button(app.sidebar.button, "Demo · customer experience").click().run()
    _button(app.button, "Analyze survey").click().run()
    assert app.session_state["analysis"] is not None

    app.sidebar.radio[0].set_value("1 · Data & scales").run()
    scale_minimum = next(widget for widget in app.number_input if widget.label == "Item scale minimum")
    scale_minimum.set_value(0.0).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["analysis"] is None
    assert app.session_state["analysis_config"] is None
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
