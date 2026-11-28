#!/usr/bin/env python3
"""Write preview/ramp-finder/map-data.json from statewide.json (Ramp Finder Phase 2, step 1).

  python3 scripts/build_ramp_map_data.py           # write the file
  python3 scripts/build_ramp_map_data.py --check   # exit 1 if the file is missing or out of date
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ramp_map_data as rmd  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    sw = json.loads(rmd.STATEWIDE.read_text())
    want = rmd.dumps(rmd.build(sw))
    if args.check:
        have = rmd.OUT.read_text() if rmd.OUT.exists() else ""
        if have != want:
            print("map-data.json is out of date; run scripts/build_ramp_map_data.py")
            return 1
        print("map-data.json is current")
        return 0
    print(json.dumps(rmd.write(sw), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
