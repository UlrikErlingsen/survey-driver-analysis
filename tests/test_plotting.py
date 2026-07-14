from __future__ import annotations

import numpy as np
import pandas as pd

from driversignal.plotting import importance_figure


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
