"""Tests import the source skill without installing it."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/local-python-repair/scripts"
sys.path.insert(0, str(SCRIPTS))
