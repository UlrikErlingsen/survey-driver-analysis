"""Plotly figures that keep importance, direction, and reliability distinct."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go


COLORS = {
    "ink": "#17322E",
    "deep": "#102C2A",
    "teal": "#173C3A",
    "coral": "#D95B40",
    "mint": "#83D2B4",
    "gold": "#F2C66D",
    "paper": "#F8F5ED",
    "muted": "#59716C",
    "line": "rgba(23,50,46,.14)",
}


def _layout(figure: go.Figure, *, height: int, x_title: str, margin_left: int = 120) -> go.Figure:
    figure.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(255,255,255,.46)",
        font=dict(color=COLORS["ink"]),
        margin=dict(l=margin_left, r=40, t=28, b=60),
        xaxis=dict(title=x_title, gridcolor="rgba(23,50,46,.10)", zeroline=False),
        yaxis=dict(title=None, gridcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor=COLORS["deep"], font_color=COLORS["paper"]),
        showlegend=False,
    )
    return figure


def importance_figure(table: pd.DataFrame, *, show_direction: bool = True) -> go.Figure:
    """Plot nonnegative LMG importance, adding beta direction only when identified."""
    ordered = table.sort_values("r2_contribution", ascending=True).copy()
    if show_direction:
        signs = np.where(ordered["standardized_beta"] >= 0, "+", "−")
        labels = [
            f"{share:.1f}% explained · β {sign}{abs(beta):.2f}"
            for share, beta, sign in zip(
                ordered["share_of_explained_percent"], ordered["standardized_beta"], signs, strict=True
            )
        ]
        customdata = np.column_stack(
            [ordered["share_of_explained_percent"], ordered["standardized_beta"], ordered["full_model_r2"]]
        )
        hovertemplate = (
            "<b>%{y}</b><br>R² contribution %{x:.3f}<br>Share of explained variance %{customdata[0]:.1f}%"
            "<br>Standardized beta %{customdata[1]:+.3f}<br>Full-model R² %{customdata[2]:.3f}<extra></extra>"
        )
        x_title = "Contribution to full-model R² (importance is nonnegative; β gives direction)"
    else:
        labels = [f"{share:.1f}% explained" for share in ordered["share_of_explained_percent"]]
        customdata = np.column_stack(
            [ordered["share_of_explained_percent"], ordered["full_model_r2"]]
        )
        hovertemplate = (
            "<b>%{y}</b><br>R² contribution %{x:.3f}<br>Share of explained variance %{customdata[0]:.1f}%"
            "<br>Full-model R² %{customdata[1]:.3f}<extra></extra>"
        )
        x_title = "Contribution to full-model R² (coefficient direction is not identifiable)"
    figure = go.Figure(
        go.Bar(
            x=ordered["r2_contribution"],
            y=ordered["driver"],
            orientation="h",
            marker_color=COLORS["teal"],
            text=labels,
            textposition="outside",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=hovertemplate,
        )
    )
    maximum = float(ordered["r2_contribution"].max()) if len(ordered) else 1.0
    figure.update_xaxes(range=[0, max(maximum * 1.48, 0.02)])
    return _layout(
        figure,
        height=max(330, 58 * len(ordered) + 110),
        x_title=x_title,
        margin_left=150,
    )


def coefficient_figure(table: pd.DataFrame, confidence_percent: int = 95) -> go.Figure:
    """Forest plot of standardized coefficients and robust intervals."""
    ordered = table.sort_values("standardized_beta", ascending=True).copy()
    valid = ordered[["ci_low", "ci_high", "standardized_beta"]].notna().all(axis=1)
    colors = [COLORS["coral"] if beta >= 0 else COLORS["gold"] for beta in ordered["standardized_beta"]]
    figure = go.Figure(
        go.Scatter(
            x=ordered["standardized_beta"],
            y=ordered["driver"],
            mode="markers",
            marker=dict(color=colors, size=11, line=dict(color=COLORS["deep"], width=1)),
            error_x=dict(
                type="data",
                symmetric=False,
                array=np.where(valid, ordered["ci_high"] - ordered["standardized_beta"], 0),
                arrayminus=np.where(valid, ordered["standardized_beta"] - ordered["ci_low"], 0),
                color=COLORS["muted"],
                thickness=1.5,
                width=5,
            ),
            customdata=np.column_stack([ordered["ci_low"], ordered["ci_high"], ordered["p_value_exploratory"]]),
            hovertemplate=(
                "<b>%{y}</b><br>Standardized β %{x:+.3f}<br>Robust interval %{customdata[0]:+.3f} to "
                "%{customdata[1]:+.3f}<br>Exploratory p %{customdata[2]:.4f}<extra></extra>"
            ),
        )
    )
    figure.add_vline(x=0, line_width=1, line_color=COLORS["muted"])
    return _layout(
        figure,
        height=max(330, 58 * len(ordered) + 110),
        x_title=f"Standardized conditional association (HC3 robust {confidence_percent}% interval)",
        margin_left=150,
    )


def reliability_figure(summary: pd.DataFrame) -> go.Figure:
    """Raw alpha estimates and deterministic bootstrap intervals."""
    plotted = summary.loc[summary["cronbach_alpha"].notna()].sort_values("cronbach_alpha").copy()
    figure = go.Figure()
    if not plotted.empty:
        figure.add_trace(
            go.Scatter(
                x=plotted["cronbach_alpha"],
                y=plotted["scale"],
                mode="markers",
                marker=dict(color=COLORS["coral"], size=12, line=dict(color=COLORS["deep"], width=1)),
                error_x=dict(
                    type="data",
                    symmetric=False,
                    array=(plotted["alpha_ci_high"] - plotted["cronbach_alpha"]).clip(lower=0).fillna(0),
                    arrayminus=(plotted["cronbach_alpha"] - plotted["alpha_ci_low"]).clip(lower=0).fillna(0),
                    color=COLORS["muted"],
                    thickness=1.5,
                    width=5,
                ),
                customdata=np.column_stack(
                    [plotted["items"], plotted["complete_for_alpha"], plotted["standardized_alpha"]]
                ),
                hovertemplate=(
                    "<b>%{y}</b><br>Raw alpha %{x:.3f}<br>Items %{customdata[0]:.0f}"
                    "<br>Complete respondents %{customdata[1]:.0f}<br>Standardized alpha %{customdata[2]:.3f}<extra></extra>"
                ),
            )
        )
    figure.add_vline(
        x=0.70,
        line_width=1,
        line_dash="dot",
        line_color=COLORS["muted"],
        annotation_text=".70 common exploratory convention",
        annotation_position="top left",
    )
    figure.add_vrect(x0=0.95, x1=1.05, fillcolor="rgba(242,198,109,.14)", line_width=0)
    lower = min(-0.2, float(plotted["alpha_ci_low"].min()) - 0.05) if not plotted.empty else -0.2
    figure.update_xaxes(range=[max(-1.0, lower), 1.03])
    return _layout(
        figure,
        height=max(300, 62 * len(plotted) + 120),
        x_title="Cronbach's alpha (contextual diagnostic, not a validity test)",
        margin_left=140,
    )


def fitted_figure(fitted: pd.DataFrame) -> go.Figure:
    """Observed-versus-fitted diagnostic with an equality reference."""
    low = float(min(fitted["observed"].min(), fitted["fitted"].min()))
    high = float(max(fitted["observed"].max(), fitted["fitted"].max()))
    figure = go.Figure(
        go.Scatter(
            x=fitted["fitted"],
            y=fitted["observed"],
            mode="markers",
            marker=dict(
                color=fitted["cooks_distance"],
                colorscale=[[0, COLORS["mint"]], [1, COLORS["coral"]]],
                size=7,
                opacity=0.72,
                colorbar=dict(title="Cook's d"),
            ),
            customdata=np.column_stack([fitted["source_row"], fitted["residual"], fitted["cooks_distance"]]),
            hovertemplate=(
                "Source row %{customdata[0]}<br>Fitted %{x:.2f}<br>Observed %{y:.2f}"
                "<br>Residual %{customdata[1]:+.2f}<br>Cook's d %{customdata[2]:.4f}<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[low, high],
            y=[low, high],
            mode="lines",
            line=dict(color=COLORS["muted"], width=1, dash="dot"),
            hoverinfo="skip",
        )
    )
    figure.update_yaxes(title="Observed outcome", gridcolor="rgba(23,50,46,.10)")
    return _layout(figure, height=480, x_title="Fitted outcome", margin_left=70)
