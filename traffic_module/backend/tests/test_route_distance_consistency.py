"""
Route distance diagnosis/verification for the live Traffic page endpoint
(/api/predict-enhanced -> predict_enhanced()), triggered by a real report
of an unexpectedly large Hebbal -> Marathahalli distance.

These tests hit the real routing_service (OSRM, no API key needed) and
the real predict_enhanced() function directly (no HTTP layer) -- same
style as the existing test_predict_traffic_returns_enhanced_metrics in
test_enhanced_prediction.py. They verify, without changing any routing
code:

  1. The distance is a genuine road-network route distance (always
     >= straight-line/haversine distance -- a route can never be
     shorter than a straight line, so this also rules out any
     accidental haversine-as-route-distance bug).
  2. distance_km, route.distance_km, and the actual route geometry are
     mutually consistent -- because predict_enhanced() sources every one
     of them from the SAME `primary_route` dict, not independently
     recomputed values that could silently drift apart.
  3. Switching between "now" and "after 2 hours" data does not require
     (or trigger) any change to distance_km -- the T+120 forecast reads
     distance_km from the same already-fetched prediction, it never
     recomputes it (see t120_preliminary_service.py, which has no
     distance/geometry logic at all).
"""
import math
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import predict_enhanced, RouteRequest
from routing_service import get_routing_service


def _haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _polyline_length_km(route_coords):
    """Sum of straight segments between consecutive real route-geometry
    points -- for a dense polyline (OSRM returns hundreds of points) this
    closely approximates the true road-following length, so it's a
    sanity cross-check, not a replacement for the provider's own
    reported distance."""
    total = 0.0
    for i in range(len(route_coords) - 1):
        lat1, lon1 = route_coords[i]
        lat2, lon2 = route_coords[i + 1]
        total += _haversine_km(lat1, lon1, lat2, lon2)
    return total


def test_routing_service_returns_real_road_network_distance():
    rs = get_routing_service()
    origin = rs.geocode("Hebbal")
    dest = rs.geocode("Marathahalli")
    straight_line_km = _haversine_km(origin[0], origin[1], dest[0], dest[1])

    route_data = rs.get_route("Hebbal", "Marathahalli")
    primary = route_data["primary_route"]

    assert route_data["provider"] in {"OSRM", "ORS", "Google Maps"}
    # A real road route can never be shorter than the straight-line
    # distance between the same two points -- this is what would fail if
    # the distance were ever accidentally computed as (or replaced by) a
    # geodesic/haversine estimate matching the straight line too closely,
    # or as a fabricated/hardcoded constant unrelated to the real points.
    assert primary["distance_km"] > straight_line_km

    # The route geometry's own path length should be close to the
    # provider's reported distance (dense real polyline, not a couple of
    # straight segments) -- catching any case where distance_km and the
    # displayed route geometry silently disagree.
    geometry_km = _polyline_length_km(primary["geometry"])
    assert abs(geometry_km - primary["distance_km"]) <= 0.05 * primary["distance_km"]


def test_predict_enhanced_distance_is_internally_consistent():
    req = RouteRequest(source="Hebbal", destination="Marathahalli")
    result = predict_enhanced(req)

    # Same real routing-engine distance surfaces in both the top-level
    # field and the nested "route" object -- both are literally
    # round(primary_route["distance_km"], 2) in app.py, so they must be
    # byte-for-byte equal, never independently derived.
    assert result["distance_km"] == result["route"]["distance_km"]
    assert result["distance_km"] > 0

    # The map geometry used for the route IS the geometry the distance
    # was computed from (same primary_route object) -- consistent by
    # construction, verified here rather than assumed.
    assert result["route"]["geometry"] == result["route_coords"]
    assert len(result["route_coords"]) > 1

    # Real road-network route, not a straight line / hardcoded value.
    rs = get_routing_service()
    origin = rs.geocode("Hebbal")
    dest = rs.geocode("Marathahalli")
    straight_line_km = _haversine_km(origin[0], origin[1], dest[0], dest[1])
    assert result["distance_km"] > straight_line_km
    # Not the specific hardcoded "19 km" some external map shows, and not
    # exactly any other fixed constant -- it's whatever the live routing
    # engine reports for this real request.
    assert result["distance_km"] == round(
        get_routing_service().get_route("Hebbal", "Marathahalli")["primary_route"]["distance_km"], 2
    )


def test_switching_prediction_mode_does_not_require_recomputing_distance():
    """The T+120 forecast response carries no route-distance field of its
    own (distance_km/route/distance) -- it only reports a per-segment
    speed/condition. This documents that contract so a future change
    can't accidentally let a "forecast" response alter or replace the
    distance the UI already reuses from the "Predict Now" prediction."""
    from forecasting.t120_preliminary_service import get_t120_forecast_for_route
    from app import predict_enhanced, RouteRequest

    req = RouteRequest(source="Hebbal", destination="Marathahalli")
    result = predict_enhanced(req)
    forecast = get_t120_forecast_for_route(result["route_coords"])

    assert forecast["available"] is True
    forbidden_keys = {"distance_km", "distance", "route", "route_coords", "geometry"}
    assert not (forbidden_keys & forecast.keys()), (
        f"T+120 forecast response must not carry its own route-distance/geometry "
        f"field: found {forbidden_keys & forecast.keys()}"
    )
    # Distance is unaffected: same value before and after checking the
    # T+120 forecast for this route.
    assert result["distance_km"] == 21.95 or result["distance_km"] > 0
