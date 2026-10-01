"""Driver Signal user interface: the Signal Hub entry point.

The only package under ``driversignal`` that imports Streamlit or Plotly. ``render()`` draws the whole app on the
current page and never calls ``st.set_page_config``; the standalone ``app.py`` or Signal Hub owns the page config.
"""

from driversignal import __version__
from driversignal.ui import signal_theme
from driversignal.ui.app import render

APP_INFO = {"product": "Driver Signal", "version": __version__, "repo": "survey-driver-analysis", "slug": "driver"}

__all__ = ["APP_INFO", "render", "signal_theme"]
