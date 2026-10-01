from __future__ import annotations

import numpy as np
import pandas as pd

from driversignal.ui.plotting import importance_figure


def test_importance_chart_withholds_beta_when_direction_is_not_identified() -> None:
    table = pd.DataFrame(
        {
            "driver": ["A", "B"],
            "r2_contribution": [0.2, 0.1],
            "share_of_explained_percent": [66.7, 33.3],
            "standardized_beta": [np.nan, np.nan],
            "full_model_r2": [0.3, 0.3],
        }
    )
    figure = importance_figure(table, show_direction=False)
    trace = figure.data[0]
    assert all("β" not in label for label in trace.text)
    assert "beta" not in trace.hovertemplate.lower()
    assert "not identifiable" in figure.layout.xaxis.title.text


def test_figures_use_the_driver_signal_template_and_theme_colours() -> None:
    from driversignal.ui import signal_theme as sig

    table = pd.DataFrame(
        {
            "driver": ["A", "B"],
            "r2_contribution": [0.2, 0.1],
            "share_of_explained_percent": [66.7, 33.3],
            "standardized_beta": [0.4, -0.1],
            "full_model_r2": [0.3, 0.3],
        }
    )
    figure = importance_figure(table)
    assert figure.layout.template.layout.colorway == tuple(sig.colorway("driver"))
    assert figure.data[0].marker.color == sig.app("driver")["fam"]["600"]  # Research family 600
