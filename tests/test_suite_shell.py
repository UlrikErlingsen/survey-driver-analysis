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
    windows_launcher = (ROOT / "run_app.bat").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")

    assert "gatherUsageStats = false" in config
    assert 'base = "light"' in config
    # Streamlit's upload cap: 10,000 MB (Signal Hub's apps.yaml), the same default in both launchers and Docker.
    assert "maxUploadSize = 10000" in config
    assert '"${DRIVERSIGNAL_MAX_UPLOAD_MB:-10000}"' in launcher
    assert 'set "DRIVERSIGNAL_MAX_UPLOAD_MB=10000"' in windows_launcher
    assert "STREAMLIT_SERVER_MAX_UPLOAD_SIZE=10000" in dockerfile
    assert "--server.maxUploadSize" not in dockerfile
    assert 'primaryColor = "#a06f1f"' in config  # Signal Research family, 600 step
    assert "USER driversignal" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "8594" in dockerfile
    assert "DRIVERSIGNAL_PORT" in launcher
    assert 'python-version: ["3.10", "3.11", "3.12", "3.13"]' in workflow


def test_readme_matches_suite_information_architecture() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Signal README template order: readers find the same section in the same place in every repo.
    sections = [
        "## Read this first",
        "## Scope",
        "## Try the demo in three minutes",
        "## Data contract",
        "## Analysis contract",
        "## Methods",
        "## Decision statuses",
        "## Exports",
        "## Run locally",
        "## Privacy",
        "## No install? Give this file to an AI",
        "## Development",
        "## Where this fits in Signal",
        "## References",
        "## Originality and license",
    ]
    positions = [readme.find(f"\n{heading}\n") for heading in sections]
    assert all(position >= 0 for position in positions), dict(zip(sections, positions, strict=True))
    assert positions == sorted(positions)
    assert readme.startswith('<p align="center">\n  <img src="assets/driversignal-banner.png"')
    assert "assets/driversignal-banner.svg" not in readme
    assert "Signal-Research-a06f1f" in readme  # family badge in the Research 600 colour
    assert "github.com/UlrikErlingsen/survey-driver-analysis/actions" in readme  # tests badge
    assert "> Which measured experiences move with satisfaction?" in readme
    assert "**Driver Signal**" in readme
    assert "DriverSignal" not in readme
    assert '<img src="assets/driversignal-mark-64.png"' in readme  # suite footer
    assert "Creator Signal" not in readme
    # Honesty statements and scope limits survive the restructure.
    assert "not proof of cause" in readme
    assert "Alpha does **not** establish unidimensionality" in readme
    assert "deliberately excluded from the evidence pack" in readme
    assert "No silent median imputation" in readme
    assert "Grömping, U. (2007)" in readme
    for path in ("assets/driversignal-banner.png", "assets/driversignal-mark-64.png", "assets/driversignal-social.png"):
        assert (ROOT / path).exists()
    assert not (ROOT / "assets" / "driversignal-banner.svg").exists()


def test_display_name_is_spaced_in_user_facing_text() -> None:
    files = [
        "AI_ANALYST.md", "CITATION.cff", "CONTRIBUTING.md", "PRIVACY.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
        "run_app.bat", "run_app.command", "docs/data_guide.md", "docs/methods.md", "docs/decision_guide.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml",
    ]
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "DriverSignal" not in text, name
    assert "Driver Signal" in (ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").read_text(encoding="utf-8")
