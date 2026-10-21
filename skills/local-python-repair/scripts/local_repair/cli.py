"""Private worker commands; public orchestration is completed separately."""
import argparse
from pathlib import Path
from .worker import run_attempt


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("command", choices=["worker"])
    parser.add_argument("identifier")
    args = parser.parse_args(argv)
    return run_attempt(args.state_dir, args.identifier)
