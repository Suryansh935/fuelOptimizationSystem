import json
import logging

import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from optimizer.services import (
    FuelPriceDataError,
    LocationNotFoundError,
    build_route_station_response,
)


logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def route_plan(request):
    """Return a route and nearby fuel stations for two US locations.

    Request JSON: {"start": "Chicago, IL", "destination": "Kansas City, MO"}
    """
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Request body must be valid JSON"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"error": "Request JSON must be an object"}, status=400)

    start = payload.get("start")
    destination = payload.get("destination")
    if not isinstance(start, str) or not start.strip():
        return JsonResponse(
            {"error": "'start' must be a non-empty location string"},
            status=400,
        )
    if not isinstance(destination, str) or not destination.strip():
        return JsonResponse(
            {"error": "'destination' must be a non-empty location string"},
            status=400,
        )

    try:
        result = build_route_station_response(
            start.strip(),
            destination.strip(),
        )
    except LocationNotFoundError as error:
        return JsonResponse({"error": str(error)}, status=422)
    except FuelPriceDataError:
        logger.exception("Fuel price data has no usable US average")
        return JsonResponse(
            {"error": "Fuel price data is unavailable for route optimization"},
            status=503,
        )
    except ValueError as error:
        if "GEOAPIFY_API_KEY is missing" in str(error):
            logger.error("Geoapify API key is not configured")
            return JsonResponse(
                {"error": "Location or station provider is not configured"},
                status=503,
            )
        return JsonResponse({"error": str(error)}, status=422)
    except requests.RequestException as error:
        logger.error(
            "External routing or station provider request failed (%s)",
            type(error).__name__,
        )
        return JsonResponse(
            {"error": "An external routing or station provider request failed"},
            status=502,
        )
    except OSError:
        logger.exception("Fuel price CSV could not be loaded")
        return JsonResponse(
            {"error": "Fuel price data is currently unavailable"},
            status=500,
        )

    return JsonResponse(result)