"""Households package: OSM data retrieval, map rendering, and search validation."""

from .models import DEFAULT_LAT, DEFAULT_LON, DEFAULT_RADIUS, Household
from .errors import ExternalServiceError, LocalDataError
from .source import get_households
from .map_builder import build_blank_map, build_household_map
from .validation import validate_search_params
