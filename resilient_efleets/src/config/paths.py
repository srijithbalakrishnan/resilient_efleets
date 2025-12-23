# src/config/paths.py
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

OUTPUT_DIR.mkdir(exist_ok=True)

def data_path(filename: str) -> Path:
    return DATA_DIR / filename

def output_path(filename: str) -> Path:
    return OUTPUT_DIR / filename