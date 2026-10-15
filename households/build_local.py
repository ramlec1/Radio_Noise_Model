"""Build a local household SQLite snapshot from an OpenStreetMap PBF extract.

Pyosmium is imported only when this script runs. Install it with
``uv pip install -r requirements-local.txt``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# A direct ``python households/build_local.py`` has no package parent, so the
# relative imports below would fail. Re-enter through the households package.
if __name__ == "__main__" and __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from households.build_local import main

    raise SystemExit(main())

import argparse
import json
from typing import Dict, List, Optional, Sequence, Set, Tuple

import requests

from .config import USER_AGENT, local_database_path
from .local_store import add_households, finish_writer, open_writer


_GEOFABRIK_ROOT = "https://download.geofabrik.de"
_BATCH_SIZE = 5000
Coord = Tuple[float, float]


def geofabrik_pbf_url(region: str) -> str:
    """Return the Geofabrik ``-latest.osm.pbf`` URL for a regional path."""
    cleaned = region.strip().strip("/")
    if not cleaned or "\\" in cleaned or ".." in cleaned.split("/"):
        raise ValueError("Region must be a Geofabrik path such as europe/netherlands.")
    if cleaned.endswith(".osm.pbf"):
        cleaned = cleaned[: -len(".osm.pbf")]
    if cleaned.endswith("-latest"):
        cleaned = cleaned[: -len("-latest")]
    return f"{_GEOFABRIK_ROOT}/{cleaned}-latest.osm.pbf"


def download_pbf(url: str, destination: Path) -> None:
    """Stream a PBF to ``destination``. A failed download leaves no partial file."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with requests.get(
            url,
            stream=True,
            timeout=60,
            headers={"User-Agent": USER_AGENT},
        ) as response:
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _load_osmium():
    try:
        import osmium
    except ImportError as exc:
        raise SystemExit(
            "Pyosmium is required to build a local dataset. "
            "Install it with: uv pip install -r requirements-local.txt"
        ) from exc
    return osmium


def _tags_dict(tags) -> Optional[Dict[str, str]]:
    housenumber = tags.get("addr:housenumber")
    if housenumber is None or str(housenumber).strip() == "":
        return None
    return {tag.k: tag.v for tag in tags}


def _mean(coords: Sequence[Coord]) -> Optional[Coord]:
    if not coords:
        return None
    lat = sum(point[0] for point in coords) / len(coords)
    lon = sum(point[1] for point in coords) / len(coords)
    return lat, lon


def _way_coords(way) -> List[Coord]:
    coords: List[Coord] = []
    seen: Set[int] = set()
    for node in way.nodes:
        if node.ref in seen or not node.location.valid():
            continue
        seen.add(node.ref)
        coords.append((node.location.lat, node.location.lon))
    return coords


def _relation_member_ids(osmium, pbf_path: Path) -> Tuple[Set[int], Set[int]]:
    """Collect node and way ids used by relations that have a house number."""
    node_ids: Set[int] = set()
    way_ids: Set[int] = set()

    class RelationMemberHandler(osmium.SimpleHandler):
        def relation(self, relation) -> None:
            if _tags_dict(relation.tags) is None:
                return
            for member in relation.members:
                if member.type == "n":
                    node_ids.add(member.ref)
                elif member.type == "w":
                    way_ids.add(member.ref)

    RelationMemberHandler().apply_file(str(pbf_path), locations=False)
    return node_ids, way_ids


def extract_households(pbf_path: Path, output_path: Path) -> int:
    """Stream ``pbf_path`` and write households with ``addr:housenumber``."""
    osmium = _load_osmium()
    print(f"Scanning relations in {pbf_path}...")
    relation_node_ids, relation_way_ids = _relation_member_ids(osmium, pbf_path)
    print(
        "Relation members to resolve: "
        f"{len(relation_node_ids)} nodes, {len(relation_way_ids)} ways"
    )

    connection = open_writer(output_path)
    batch: List[Tuple[float, float, str, str]] = []
    count = 0
    node_coords: Dict[int, Coord] = {}
    way_coords: Dict[int, List[Coord]] = {}

    def emit(element_type: str, osm_id: int, lat: float, lon: float, tags: Dict[str, str]) -> None:
        nonlocal count
        batch.append((lat, lon, f"{element_type}/{osm_id}", json.dumps(tags, ensure_ascii=False)))
        count += 1
        if len(batch) >= _BATCH_SIZE:
            add_households(connection, batch)
            connection.commit()
            batch.clear()

    class HouseholdHandler(osmium.SimpleHandler):
        def node(self, node) -> None:
            if not node.location.valid():
                return
            point = (node.location.lat, node.location.lon)
            if node.id in relation_node_ids:
                node_coords[node.id] = point
            tags = _tags_dict(node.tags)
            if tags is None:
                return
            emit("node", node.id, point[0], point[1], tags)

        def way(self, way) -> None:
            coords = _way_coords(way)
            if way.id in relation_way_ids:
                way_coords[way.id] = coords
            tags = _tags_dict(way.tags)
            center = _mean(coords)
            if tags is None or center is None:
                return
            emit("way", way.id, center[0], center[1], tags)

        def relation(self, relation) -> None:
            tags = _tags_dict(relation.tags)
            if tags is None:
                return
            coords: List[Coord] = []
            for member in relation.members:
                if member.type == "n":
                    point = node_coords.get(member.ref)
                    if point is not None:
                        coords.append(point)
                elif member.type == "w":
                    coords.extend(way_coords.get(member.ref, ()))
            center = _mean(coords)
            if center is None:
                return
            emit("relation", relation.id, center[0], center[1], tags)

    print(f"Extracting households to {output_path}...")
    try:
        HouseholdHandler().apply_file(str(pbf_path), locations=True)
        if batch:
            add_households(connection, batch)
            batch.clear()
        print("Building spatial index...")
        finish_writer(connection)
    except Exception:
        connection.close()
        raise
    return count


def _pbf_filename(url: str) -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if not name.endswith(".pbf"):
        return "extract.osm.pbf"
    return name


def resolve_pbf(region: Optional[str], url: Optional[str], pbf: Optional[str], output: Path) -> Path:
    """Download a regional extract, or return a PBF that is already on disk."""
    if pbf:
        path = Path(pbf)
        if not path.is_file():
            raise FileNotFoundError(f"PBF file was not found: {path}")
        return path

    download_url = url if url else geofabrik_pbf_url(region or "")
    destination = output.parent / _pbf_filename(download_url)
    print(f"Downloading {download_url} to {destination}...")
    download_pbf(download_url, destination)
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a local household SQLite snapshot from an OpenStreetMap PBF extract.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--region",
        help="Geofabrik path, for example europe/netherlands",
    )
    source.add_argument(
        "--url",
        help="Direct .osm.pbf URL",
    )
    source.add_argument(
        "--pbf",
        help="Path to an .osm.pbf file already on disk",
    )
    parser.add_argument(
        "--output",
        default=str(local_database_path()),
        help="SQLite file to write (default: data/households.sqlite or HOUSEHOLD_LOCAL_PATH)",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    output = Path(args.output)
    try:
        pbf_path = resolve_pbf(args.region, args.url, args.pbf, output)
        count = extract_households(pbf_path, output)
    except Exception as exc:
        print(f"Failed to build household dataset: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {count} households to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
