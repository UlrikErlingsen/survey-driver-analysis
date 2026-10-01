"""The shared Signal shell: theme, lockup, masthead, footer, chart template and runtime scaffolding."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

from driversignal import __version__


ROOT = Path(__file__).parents[1]
APP = str(ROOT / "app.py")
UI = ROOT / "src" / "driversignal" / "ui"
OLD_COLOURS = ("#173c3a", "#d95b40", "#83d2b4", "#f2c66d", "#17322e", "#102c2a", "#f8f5ed", "#59716c")


def test_shared_signal_shell_renders() -> None:
    app = AppTest.from_file(APP, default_timeout=120)
    app.run()

    assert not app.exception, [error.value for error in app.exception]
    body = "\n".join(str(item.value) for item in app.markdown)
    sidebar = "\n".join(str(item.value) for item in app.sidebar.markdown)
    assert "OPEN SURVEY DRIVER ANALYSIS" in body
    assert "SURVEY DRIVER ANALYSIS, WITHOUT THE BLACK BOX" in body
    assert f"Driver Signal v{__version__}" in body
    assert "Associations to investigate, not causal proof" in body
    assert "Part of the Signal suite" in body
    assert "AGPL-3.0-or-later" in body
    assert "proven cause" in body  # association caution on the welcome page
    assert "sg-mast" in body  # the shared Signal masthead
    assert "sg-foot" in body  # the shared Signal footer
    assert "sg-hero" in body
    assert "Reliable constructs and challengeable priorities out" in sidebar
    assert "sg-side" in sidebar  # the shared Signal sidebar lockup


def test_app_uses_shared_signal_theme_instead_of_pasted_styles() -> None:
    standalone = (ROOT / "app.py").read_text(encoding="utf-8")
    ui_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in UI.glob("*.py") if path.name != "signal_theme.py"
    )
    theme = (UI / "signal_theme.py").read_text(encoding="utf-8")
    assert 'st.set_page_config(**sig.page_config("driver"))' in standalone
    assert "sig.apply(NS)" in ui_sources
    assert "st.plotly_chart(" not in ui_sources  # charts go through sig.chart (template + theme=None)
    assert ui_sources.count("sig.chart(") == 5  # every Plotly figure goes through sig.chart
    assert "template=sig.template(NS)" in ui_sources
    assert "<style>" not in standalone + ui_sources
    assert "unsafe_allow_html" not in standalone + ui_sources
    for old_colour in OLD_COLOURS:
        assert old_colour not in (standalone + ui_sources).lower()
    assert (UI / "assets" / "marks" / "driversignal-mark-64.png").exists()
    assert ":focus-visible" in theme
    assert "@media (prefers-reduced-motion:reduce)" in theme
    assert "friendly_message" in ui_sources


def test_runtime_scaffolding_is_private_and_health_checked() -> None:
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    launcher = (ROOT / "run_app.command").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")

    assert "gatherUsageStats = false" in config
    assert 'base = "light"' in config
    assert 'primaryColor = "#a06f1f"' in config  # Signal Research family, 600 step
    assert "USER driversignal" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "8594" in dockerfile
    assert "DRIVERSIGNAL_PORT" in launcher
    assert 'python-version: ["3.10", "3.11", "3.12", "3.13"]' in workflow
