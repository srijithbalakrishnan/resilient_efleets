from resilient_efleets.src.data.loader import load_all_network_data
from resilient_efleets.src.fleet.schedule import load_bus_schedules

d = load_all_network_data()
b = load_bus_schedules(d['routes'], d['depots'])

print(f'Buses: {len(b)}')
print(f'Stops: {len(d["stops"])}')
print(f'Charging Stations: {len(d["charging_stations"])}')
print(f'Depots: {len(d["depots"])}')
print(f'Routes: {len(d["routes"])}')
