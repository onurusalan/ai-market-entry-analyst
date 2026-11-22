"""
Plotly figures shared by the Streamlit app.

The EU map is a tile grid (one square per member state) instead of a choropleth, because
choropleths download country shapes from a CDN at view time and stay blank without internet.
"""

from __future__ import annotations

import plotly.graph_objects as go

from . import catalog
from . import knowledge as kb


def eu_tile_map(values: dict[str, float], title: str, unit: str = "", colorscale: str = "Blues") -> go.Figure:
    """values: ISO2 member code -> number. Members without a value are drawn grey."""
    codes = [c for c in catalog.EU_TILES if c in values]
    missing = [c for c in catalog.EU_TILES if c not in values]
    fig = go.Figure()
    if missing:
        fig.add_trace(go.Scatter(
            x=[catalog.EU_TILES[c][1] for c in missing], y=[-catalog.EU_TILES[c][0] for c in missing],
            mode="markers+text", text=missing, textfont={"color": "#5a6474", "size": 12},
            marker={"symbol": "square", "size": 46, "color": "#e3e7ed"}, hoverinfo="skip", showlegend=False))
    vals = [values[c] for c in codes]
    fig.add_trace(go.Scatter(
        x=[catalog.EU_TILES[c][1] for c in codes], y=[-catalog.EU_TILES[c][0] for c in codes],
        mode="markers+text", text=codes, textfont={"color": "#0e1726", "size": 12},
        customdata=[[kb.COUNTRIES[c]["name"], v] for c, v in zip(codes, vals, strict=True)],
        hovertemplate="%{customdata[0]}: %{customdata[1]:,.2f}" + unit + "<extra></extra>",
        marker={"symbol": "square", "size": 46, "color": vals, "colorscale": colorscale, "showscale": True,
                "colorbar": {"thickness": 10, "title": {"text": unit.strip()}}, "line": {"width": 0}},
        showlegend=False))
    fig.update_layout(title=title, height=520, margin={"t": 50, "b": 10, "l": 10, "r": 10},
                      xaxis={"visible": False, "range": [-0.7, 6.7], "fixedrange": True},
                      yaxis={"visible": False, "range": [-6.7, 0.7], "fixedrange": True, "scaleanchor": "x"},
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig
