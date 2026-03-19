import datetime
from flask import Flask, request, jsonify
import db_storage as storage
import constants
from config import config

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    """Add CORS headers to allow dashboard requests."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    return response


def _check_api_key() -> bool:
    api_key = config.get("SENSOR_API_KEY")
    if api_key and request.headers.get("X-API-Key") != api_key:
        return False
    return True


def _normalize_house(house: str) -> str | None:
    """Normalize house name to match constants (case-insensitive)."""
    house_lower = house.lower()
    for h in constants.HOUSES.keys():
        if h.lower() == house_lower:
            return h
    return None


def _get_machine_kind(machine_name: str) -> str:
    """Determine if machine is washer or dryer based on name."""
    return "washer" if "washer" in machine_name.lower() else "dryer"


def _build_machine_status(house_id: str, machine_name: str, now: datetime.datetime) -> dict:
    """Build a single machine's status in dashboard format."""
    curr_user, end_time, start_time = storage.get_laundry_timer(house_id, machine_name)
    kind = _get_machine_kind(machine_name)

    if end_time and end_time > now:
        return {
            "status": "in_use",
            "kind": kind,
            "currUser": None if curr_user == "sensor" else curr_user,
            "startTimeMs": int(start_time.timestamp() * 1000) if start_time else None,
            "endTime": int(end_time.timestamp() * 1000),
            "hardwareDetected": curr_user == "sensor",
            "queueLength": 0,
            "cycleEndedAtMs": None,
        }
    elif end_time and end_time <= now and curr_user:
        return {
            "status": "idle",
            "kind": kind,
            "currUser": None if curr_user == "sensor" else curr_user,
            "startTimeMs": None,
            "endTime": None,
            "hardwareDetected": curr_user == "sensor",
            "queueLength": 0,
            "cycleEndedAtMs": int(end_time.timestamp() * 1000),
        }
    else:
        return {
            "status": "available",
            "kind": kind,
            "currUser": None,
            "startTimeMs": None,
            "endTime": None,
            "hardwareDetected": False,
            "queueLength": 0,
            "cycleEndedAtMs": None,
        }


@app.route("/machine/update", methods=["POST"])
def update_machine():
    if not _check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    house = data.get("house")
    machine_name = data.get("machine_name")
    status = data.get("status")

    if house not in constants.HOUSES:
        return jsonify({"error": f"Invalid house. Valid: {list(constants.HOUSES.keys())}"}), 400
    if machine_name not in constants.MACHINE_NAMES:
        return jsonify({"error": f"Invalid machine_name. Valid: {constants.MACHINE_NAMES}"}), 400
    if status not in ("in_use", "available"):
        return jsonify({"error": "status must be 'in_use' or 'available'"}), 400

    if status == "in_use":
        # Sensor doesn't know cycle length, so set a 2-hour ceiling.
        # The "available" POST from the sensor will clear this early when vibration stops.
        end_time = datetime.datetime.now() + datetime.timedelta(hours=2)
        storage.set_laundry_timer_sensor(house, machine_name, end_time)
    else:
        storage.clear_laundry_timer(house, machine_name)

    return jsonify({"status": "ok", "house": house, "machine": machine_name, "new_status": status})


@app.route("/status", methods=["GET"])
def get_status_legacy():
    """Legacy endpoint - returns old format for backwards compatibility."""
    now = datetime.datetime.now()
    machines = {}
    for house_id in constants.HOUSES.keys():
        machines[house_id] = {}
        for machine_name in constants.MACHINE_NAMES:
            curr_user, end_time, _ = storage.get_laundry_timer(house_id, machine_name)
            if end_time and end_time > now:
                machines[house_id][machine_name] = {
                    "status": "in_use",
                    "curr_user": curr_user,
                    "end_time": int(end_time.timestamp()),
                    "minutes_remaining": int((end_time - now).total_seconds() / 60),
                }
            else:
                machines[house_id][machine_name] = {
                    "status": "available",
                    "last_user": curr_user if curr_user else None,
                }
    return jsonify(machines)


@app.route("/api/status", methods=["GET"])
def get_status():
    """Get status for all houses in dashboard format."""
    now = datetime.datetime.now()
    result = {}

    for house_id in constants.HOUSES.keys():
        machines = {}
        for machine_name in constants.MACHINE_NAMES:
            machines[machine_name] = _build_machine_status(house_id, machine_name, now)

        result[house_id] = {
            "college": "capt",
            "house": house_id,
            "lastUpdatedMs": int(now.timestamp() * 1000),
            "machines": machines,
        }

    return jsonify(result)


@app.route("/api/<house>/status", methods=["GET"])
def get_house_status(house: str):
    """Get status for a specific house in dashboard format."""
    normalized_house = _normalize_house(house)
    if not normalized_house:
        return jsonify({"error": f"Invalid house. Valid: {list(constants.HOUSES.keys())}"}), 400

    now = datetime.datetime.now()
    machines = {}
    for machine_name in constants.MACHINE_NAMES:
        machines[machine_name] = _build_machine_status(normalized_house, machine_name, now)

    return jsonify({
        "college": "capt",
        "house": normalized_house,
        "lastUpdatedMs": int(now.timestamp() * 1000),
        "machines": machines,
    })


@app.route("/api/start-cycle", methods=["POST"])
def start_cycle():
    """Start a laundry cycle from the dashboard."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    house = data.get("house")
    machine_name = data.get("machine_name")
    username = data.get("username")
    duration_mins = data.get("duration_mins", 30)

    normalized_house = _normalize_house(house) if house else None
    if not normalized_house:
        return jsonify({"error": f"Invalid house. Valid: {list(constants.HOUSES.keys())}"}), 400
    if machine_name not in constants.MACHINE_NAMES:
        return jsonify({"error": f"Invalid machine_name. Valid: {constants.MACHINE_NAMES}"}), 400
    if not username:
        return jsonify({"error": "username is required"}), 400

    now = datetime.datetime.now()
    curr_user, end_time, _ = storage.get_laundry_timer(normalized_house, machine_name)
    if end_time and end_time > now:
        return jsonify({"error": f"{machine_name} is currently in use"}), 409

    end_time = now + datetime.timedelta(minutes=duration_mins)
    storage.set_laundry_timer(normalized_house, machine_name, username, end_time, start_time=now)

    return jsonify({
        "status": "ok",
        "house": normalized_house,
        "machine": machine_name,
        "username": username,
        "endTimeMs": int(end_time.timestamp() * 1000),
    })


def start_api():
    port = config.get("SENSOR_API_PORT", 5001)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
