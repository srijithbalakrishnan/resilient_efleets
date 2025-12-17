# src/visualization/animation.py
"""
Create an animated Folium map from simulation log showing bus movements over time.
"""

import pandas as pd
import folium
from datetime import datetime
from src.config.paths import output_path


def create_bus_animation(
    log_csv: str = "simulation_log.csv",
    output_file: str = "bus_animation.html",
    frame_interval_ms: int = 500
) -> str:
    """
    Generate animated map of bus positions from log.
    """
    print("Creating bus movement animation...")
    df = pd.read_csv(output_path(log_csv))

    # Convert sim_time to datetime for sorting
    df['sim_dt'] = pd.to_datetime(df['sim_time'], format='%H:%M:%S')
    df = df.sort_values(['sim_time', 'bus_id'])

    # Center map
    center_lat = df['latitude'].mean()
    center_lon = df['longitude'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=12)

    # Time index for animation
    timestamps = sorted(df['sim_time'].unique())

    # Add bus traces
    bus_colors = {}
    color_list = ["red", "blue", "green", "purple", "orange", "darkred", "lightblue", "pink"]
    for i, bus_id in enumerate(df['bus_id'].unique()):
        color = color_list[i % len(color_list)]
        bus_colors[bus_id] = color

        bus_df = df[df['bus_id'] == bus_id]
        coords = list(zip(bus_df['latitude'], bus_df['longitude']))

        # Trail line
        folium.PolyLine(
            coords,
            color=color,
            weight=3,
            opacity=0.6,
            popup=bus_id
        ).add_to(m)

        # Animated marker (using TimestampedGeoJson)
        features = []
        for _, row in bus_df.iterrows():
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row['longitude'], row['latitude']]
                },
                "properties": {
                    "time": row['sim_time'],
                    "popup": f"<b>{bus_id}</b><br>SoC: {row['soc']:.1f}%<br>Status: {row['status']}",
                    "icon": "circle",
                    "iconstyle": {
                        "fillColor": color,
                        "fillOpacity": 0.8,
                        "stroke": "true",
                        "radius": 8
                    }
                }
            }
            features.append(feature)

        folium.plugins.TimestampedGeoJson(
            {"type": "FeatureCollection", "features": features},
            period="PT1M",
            add_last_point=True,
            auto_play=False,
            loop=False,
            max_speed=1,
            loop_button=True,
            time_slider_drag_update=True
        ).add_to(m)

    output_path_full = output_path(output_file)
    m.save(str(output_path_full))
    print(f"Animation saved to: {output_path_full}")
    return str(output_path_full)