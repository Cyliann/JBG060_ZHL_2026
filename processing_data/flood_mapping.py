"""
Visualize MODIS/VIIRS flood pixel data as a day-by-day 2D map with a slider,
without ever building a dense (day x lat x lon) 3D array.
"""

import glob

import numpy as np
import pandas as pd


def load_flood_data(
    recurring_glob="./raw_data/flood_masks/compact_recurring/*2025*.parquet",
    unusual_glob="./raw_data/flood_masks/compact_unusual/*2025*.parquet",
):
    recurring_files = glob.glob(recurring_glob)
    unusual_files = glob.glob(unusual_glob)
    if not recurring_files and not unusual_files:
        raise FileNotFoundError("No parquet files found - check your folder paths")

    cols = ["date", "lat", "lon"]
    dfs = []
    for f in recurring_files:
        d = pd.read_parquet(f, columns=cols)
        d["flood_type"] = "recurring"
        dfs.append(d)
    for f in unusual_files:
        d = pd.read_parquet(f, columns=cols)
        d["flood_type"] = "unusual"
        dfs.append(d)

    df = pd.concat(dfs, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def build_plotly_slider_map(
    df, out_path="flood_slider_map.html", max_points_per_day=None
):
    import plotly.graph_objects as go

    # Optional: if some days have huge point counts and the HTML gets too
    # big / slow, subsample per day rather than building any dense grid.
    if max_points_per_day:
        df = df.groupby(df["date"].dt.date, group_keys=False).apply(
            lambda g: g.sample(min(len(g), max_points_per_day), random_state=0)
        )

    frame_labels = df["date"].dt.strftime("%Y-%m-%d")

    fig = go.Figure(
        go.Scattergeo(
            df,
            lat="lat",
            lon="lon",
            color="flood_type",
            animation_frame=frame_labels,
            zoom=6,
            height=750,
            category_orders={"flood_type": sorted(df["flood_type"].unique())},
        )
    )
    # fig.update_traces(marker=dict(size=4))
    fig.update_geos(visible=False)

    fig.add_layout_image(
        source="./roads.pdf",
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        sizex=1,
        sizey=1,
        xanchor="center",
        yanchor="middle",
        opacity=1,
        layer="below",
    )
    # fig.write_html(out_path)
    # print(f"Wrote {out_path}")
    return fig


if __name__ == "__main__":
    df = load_flood_data()
    print(
        f"Loaded {len(df):,} flood-pixel events across "
        f"{df['date'].dt.date.nunique()} days"
    )

    # Standalone HTML you can open in a browser and share:
    build_plotly_slider_map(df, max_points_per_day=None)
