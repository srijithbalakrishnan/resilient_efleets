# src/visualization/dashboard.py
"""
Interactive Plotly dashboard from simulation log.
Shows fleet-wide metrics over time.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from src.config.paths import output_path


def create_dashboard(log_csv: str = "simulation_log.csv", output_file: str = "dashboard.html"):
    """
    Generate a multi-panel dashboard with key performance indicators.
    """
    print("Creating simulation dashboard...")
    df = pd.read_csv(output_path(log_csv))

    # Parse time
    df['sim_time_dt'] = pd.to_datetime(df['sim_time'], format='%H:%M:%S')
    df = df.sort_values('sim_time_dt')

    # Aggregate metrics
    fleet_df = df.groupby('sim_time').agg({
        'soc': 'mean',
        'delay_seconds': 'sum',
        'unserved_demand': 'sum',
        'bus_id': 'count'
    }).reset_index()
    fleet_df.rename(columns={'bus_id': 'active_buses'}, inplace=True)

    # Create subplots
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=("Average Fleet SoC (%)", "Total Delay (seconds)", "Cumulative Unserved Demand"),
        vertical_spacing=0.1
    )

    # SoC
    fig.add_trace(
        go.Scatter(x=fleet_df['sim_time'], y=fleet_df['soc'],
                   mode='lines+markers', name='Avg SoC', line=dict(color='green')),
        row=1, col=1
    )

    # Delay
    fig.add_trace(
        go.Scatter(x=fleet_df['sim_time'], y=fleet_df['delay_seconds'],
                   mode='lines+markers', name='Total Delay', line=dict(color='orange')),
        row=2, col=1
    )

    # Unserved demand
    fig.add_trace(
        go.Scatter(x=fleet_df['sim_time'], y=fleet_df['unserved_demand'],
                   mode='lines+markers', name='Unserved Demand', line=dict(color='red')),
        row=3, col=1
    )

    fig.update_layout(height=900, title_text="Electric Bus Fleet Simulation Dashboard", showlegend=True)
    fig.update_xaxes(title_text="Simulation Time", row=3, col=1)

    output_path_full = output_path(output_file)
    fig.write_html(str(output_path_full))
    print(f"Dashboard saved to: {output_path_full}")
    return str(output_path_full)