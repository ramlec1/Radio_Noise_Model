"""Build a local household SQLite snapshot from an OpenStreetMap PBF extract.

Run with uv from the repository root:

    uv run build_households.py --region europe/netherlands
"""

from households.build_local import main


if __name__ == "__main__":
    raise SystemExit(main())
