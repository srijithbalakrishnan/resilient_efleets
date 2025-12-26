# src/optimization/distance_cache.py

import json
import os
from geopy.distance import geodesic
from typing import Dict, Set, Tuple

CACHE_FILE = "distance_matrix_cache.json"

def compute_and_cache_distances(
    S_map: Dict[str, object],
    feasible_edges: Set[Tuple[str, str]],
    cache_dir: str = "."
) -> Dict[Tuple[str, str], float]:
    """
    Compute distances for feasible edges and save to cache file.
    """
    cache_path = os.path.join(cache_dir, CACHE_FILE)
    
    dist_matrix = {}
    print(f"Precomputing {len(feasible_edges)} distances (this may take 10-60 seconds first time)...")
    
    count = 0
    for s1, s2 in feasible_edges:
        if s1 == s2:
            dist_matrix[(s1, s2)] = 0.0
            continue
        try:
            coord1 = S_map[s1].geometry.coords[0][::-1]  # (lat, lon)
            coord2 = S_map[s2].geometry.coords[0][::-1]
            # dist_matrix[(s1, s2)] = geodesic(coord1, coord2).meters / 1000  # km
            dist_matrix[(s1, s2)] = haversine_km(coord1, coord2)
        except Exception as e:
            print(f"Warning: Distance failed {s1}->{s2}: {e}")
            dist_matrix[(s1, s2)] = 0.0
        count += 1
        if count % 500 == 0:
            print(f"  Progress: {count}/{len(feasible_edges)}")
    
    # Save to cache
    serializable = {f"{k[0]}|{k[1]}": v for k, v in dist_matrix.items()}
    with open(cache_path, "w") as f:
        json.dump(serializable, f)
    print(f"Distance matrix cached to {cache_path}")
    
    return dist_matrix

import numpy as np

def haversine_km(coord1, coord2):
    lat1, lon1 = np.radians(coord1)
    lat2, lon2 = np.radians(coord2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return 6371 * c  # Earth radius in km
    
def load_cached_distances(
    S_map: Dict[str, object],
    feasible_edges: Set[Tuple[str, str]],
    cache_dir: str = "."
) -> Dict[Tuple[str, str], float] | None:
    """
    Try to load from cache. Returns None if cache invalid/missing.
    """
    cache_path = os.path.join(cache_dir, CACHE_FILE)
    if not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
        
        # Validate: check if all current feasible edges are in cache
        missing = []
        for s1, s2 in feasible_edges:
            key = f"{s1}|{s2}"
            if key not in data:
                missing.append((s1, s2))
        
        if missing:
            print(f"Cache outdated: missing {len(missing)} edges. Recomputing...")
            return None
        
        dist_matrix = {tuple(k.split("|")): float(v) for k, v in data.items()}
        print(f"Loaded distance matrix from cache ({len(dist_matrix)} entries)")
        return dist_matrix
    
    except Exception as e:
        print(f"Failed to load cache: {e}")
        return None