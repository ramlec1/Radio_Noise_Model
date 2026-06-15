"""Main blueprint: static page routes."""

from flask import render_template, Blueprint

from households.map_builder import build_blank_map
from households.overpass import DEFAULT_LAT, DEFAULT_LON, DEFAULT_RADIUS

main_bp = Blueprint('main', __name__)


@main_bp.route("/")
def home():
    """Render the main page with default form values and a blank map."""
    map_html = build_blank_map(DEFAULT_LAT, DEFAULT_LON, DEFAULT_RADIUS)
    return render_template(
        "index.html",
        map_html=map_html,
        lat=DEFAULT_LAT,
        lon=DEFAULT_LON,
        radius=DEFAULT_RADIUS,
        errors={},
    )


@main_bp.route("/propmods")
def propmods():
    """Propagation models reference page."""
    return render_template("propmods.html")
