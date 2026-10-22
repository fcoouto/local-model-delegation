#!/usr/bin/env python3
"""Build a numbered release from a clean, tagged checkout. Never publishes."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_model_delegation.contracts import canonical
from local_model_delegation.updates import build_release


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        print(canonical(build_release(ROOT,args.tag,args.output)))
        return 0
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        print(canonical({'status':'blocked','reason':str(error)}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
