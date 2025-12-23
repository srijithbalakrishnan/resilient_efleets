import pandas as pd

df = pd.read_csv('resilient_efleets/output/simulation_log.csv')

print(f'Total rows: {len(df)}')
print(f'Time steps: {df["sim_time"].nunique()}')
print(f'Buses: {df["bus_id"].nunique()}')
print(f'Duration: {df["sim_time"].min()} to {df["sim_time"].max()}')

print(f'\n{"="*60}')
print('STATUS DISTRIBUTION:')
print(df['status'].value_counts())

print(f'\n{"="*60}')
print('SOC STATISTICS:')
print(df['soc'].describe())

print(f'\n{"="*60}')
print('ROUTE ACTIVITY:')
print(f'Unique routes: {df["current_route"].nunique()}')
print(f'Buses on route entries: {len(df[df["status"]=="on_route"])}')
print(f'Routes used: {df[df["current_route"].notna()]["current_route"].unique()}')

print(f'\n{"="*60}')
print('DEPOT DISTRIBUTION:')
depot_coords = df.groupby(['latitude', 'longitude']).size().reset_index(name='count')
print(depot_coords.head(10))

print(f'\n{"="*60}')
print('SAMPLE TIMELINE (first few unique times):')
for time in df['sim_time'].unique()[:10]:
    step_df = df[df['sim_time'] == time]
    on_route = len(step_df[step_df['status'] == 'on_route'])
    in_depot = len(step_df[step_df['status'] == 'in_depot'])
    print(f'{time}: {on_route} on route, {in_depot} in depot')
