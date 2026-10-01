"""Signal Hub contract: importable UI entry point, Streamlit only under ui/, slug-namespaced state."""

import ast
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
from streamlit.testing.v1 import AppTest

from driversignal import __version__


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "src" / "driversignal"
UI = PACKAGE / "ui"
UI_ONLY_LIBRARIES = {"streamlit", "plotly"}
PAGES = [
    "Welcome",
    "1 · Data & scales",
    "2 · Reliability",
    "3 · Driver model",
    "4 · Interpret & export",
    "Methods & limits",
]
RENDER_SCRIPT = """
from driversignal.ui import render

render()
"""


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def _button(buttons, label: str):
    return next(button for button in buttons if button.label == label)


def test_ui_entry_point_matches_the_hub_contract() -> None:
    from driversignal.ui import APP_INFO, render

    assert callable(render)
    assert APP_INFO == {
        "product": "Driver Signal",
        "version": __version__,
        "repo": "survey-driver-analysis",
        "slug": "driver",
    }


def test_only_the_ui_package_imports_streamlit_or_plotly() -> None:
    offenders = {
        str(path.relative_to(PACKAGE)): sorted(_imported_roots(path) & UI_ONLY_LIBRARIES)
        for path in PACKAGE.rglob("*.py")
        if UI not in path.parents and _imported_roots(path) & UI_ONLY_LIBRARIES
    }
    assert not offenders, offenders


def test_core_package_imports_without_streamlit_or_plotly() -> None:
    # A fresh interpreter, so modules already imported by other tests cannot hide a stray import.
    code = (
        f"import sys\nsys.path.insert(0, {str(ROOT / 'src')!r})\n"
        "import driversignal, driversignal.analysis, driversignal.drivers, driversignal.errors, "
        "driversignal.examples, driversignal.io, driversignal.reliability, driversignal.reporting, "
        "driversignal.validation\n"
        "loaded = sorted(name for name in ('streamlit', 'plotly') if name in sys.modules)\n"
        "assert not loaded, loaded\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def test_render_never_sets_page_config_or_navigation() -> None:
    for path in UI.glob("*.py"):
        if path.name == "signal_theme.py":
            continue
        source = path.read_text(encoding="utf-8")
        for call in ("st.set_page_config(", "st.navigation(", "st.Page("):
            assert call not in source, (path.name, call)


def test_ui_reads_no_repository_files() -> None:
    # Signal Hub installs the release as a normal package: examples/, docs/ and assets/ do not exist there.
    for path in UI.glob("*.py"):
        if path.name == "signal_theme.py":
            continue  # synced; reads only its own assets/marks/ (package data)
        source = path.read_text(encoding="utf-8")
        for pattern in ("__file__", "examples/", '"examples"', "read_bytes(", "read_text(", "open("):
            assert pattern not in source, (path.name, pattern)


INSTALLED_CHECK = """
import sys
from pathlib import Path

site = sys.argv[1]
sys.path.insert(0, site)
from streamlit.testing.v1 import AppTest
import driversignal

assert driversignal.__file__.startswith(site), driversignal.__file__
app = AppTest.from_file(str(Path(site).parent / "render_app.py"), default_timeout=150)
app.run()
next(b for b in app.sidebar.button if b.label == "Demo · customer experience").click().run()
assert not app.exception, [e.value for e in app.exception]
assert app.session_state["driver:page"] == "1 · Data & scales"
assert app.session_state["driver:source_name"] == "demo_customer_experience_survey.csv"
next(b for b in app.sidebar.button if b.label == "Clear survey").click().run()
app.sidebar.radio[0].set_value("1 · Data & scales").run()
assert not app.exception, [e.value for e in app.exception]
assert len(app.get("download_button")) == 2  # CSV and Excel templates, generated in memory
"""


def test_render_and_demo_work_from_an_installed_copy_of_the_package(tmp_path: Path) -> None:
    # Copy only the package (as a wheel would install it, without examples/ or assets/) and run the demo from there.
    site = tmp_path / "site"
    shutil.copytree(PACKAGE, site / "driversignal", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "render_app.py").write_text(
        f"import sys\nsys.path.insert(0, {str(site)!r})\n{RENDER_SCRIPT}", encoding="utf-8"
    )
    (tmp_path / "check.py").write_text(INSTALLED_CHECK, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(tmp_path / "check.py"), str(site)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr[-4000:]


def test_render_runs_from_a_script_without_set_page_config() -> None:
    app = AppTest.from_string(RENDER_SCRIPT, default_timeout=120)
    app.run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.sidebar.radio[0].key == "driver:page"
    assert "driver:tables" in app.session_state
    assert "tables" not in app.session_state
    body = "\n".join(str(item.value) for item in app.markdown)
    assert "SURVEY DRIVER ANALYSIS, WITHOUT THE BLACK BOX" in body
    assert f"Driver Signal v{__version__}" in body


@pytest.mark.parametrize("page", PAGES)
def test_every_widget_key_is_namespaced(page: str) -> None:
    app = AppTest.from_string(RENDER_SCRIPT, default_timeout=120)
    app.run()
    app.sidebar.radio[0].set_value(page).run()

    assert not app.exception, [error.value for error in app.exception]
    widgets = [*app.radio, *app.selectbox, *app.checkbox, *app.button]
    assert widgets
    unkeyed = [(type(widget).__name__, widget.label) for widget in widgets if widget.key is None]
    assert not unkeyed, unkeyed
    assert all(widget.key.startswith("driver:") for widget in widgets)


def test_every_widget_key_is_namespaced_with_an_analysis_loaded() -> None:
    app = AppTest.from_string(RENDER_SCRIPT, default_timeout=180)
    app.run()
    _button(app.sidebar.button, "Demo · customer experience").click().run()
    widgets = [
        *app.radio,
        *app.selectbox,
        *app.multiselect,
        *app.number_input,
        *app.select_slider,
        *app.checkbox,
        *app.button,
    ]
    _button(app.button, "Analyze survey").click().run()
    for page in PAGES[2:]:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, [error.value for error in app.exception]
        widgets.extend([*app.radio, *app.selectbox, *app.button])
    unkeyed = [(type(widget).__name__, widget.label) for widget in widgets if widget.key is None]
    assert not unkeyed, unkeyed
    assert all(widget.key.startswith("driver:") for widget in widgets)
    assert not [key for key in app.session_state if not str(key).startswith(("driver:", "$$"))]


def test_session_state_and_widget_keys_go_through_the_namespace_helper() -> None:
    source = (UI / "app.py").read_text(encoding="utf-8")
    state_keys = re.findall(r"session_state(?:\[|\.get\(|\.pop\(|\.setdefault\()\s*([^,\])]+)", source)
    widget_keys = re.findall(r"\bkey=([^,)\n]+)", source)
    assert state_keys and widget_keys
    assert all(key.startswith("k(") for key in state_keys), state_keys
    assert all(key.startswith("k(") for key in widget_keys), widget_keys
    assert 'NS = "driver"' in source
