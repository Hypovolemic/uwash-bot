import datetime
import json
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import storage
import constants
from config import config

app = Flask(__name__)
CORS(app)

import os
MACHINES_JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "machines.json")


def _check_api_key() -> bool:
    api_key = config.get("SENSOR_API_KEY")
    if api_key and request.headers.get("X-API-Key") != api_key:
        return False
    return True


def _sync_to_machines_json(house: str, machine_name: str, status: str):
    """Sync sensor update to machines.json for dashboard consumption."""
    try:
        # Load or initialize machines.json
        if os.path.exists(MACHINES_JSON_PATH):
            with open(MACHINES_JSON_PATH, 'r') as f:
                state = json.load(f)
        else:
            state = {"college": "capt", "house": house, "lastUpdatedMs": 0, "machines": {}}
        
        # Ensure machines dict exists
        if "machines" not in state:
            state["machines"] = {}
        
        # Update the machine status
        if machine_name in state["machines"]:
            state["machines"][machine_name]["status"] = status
            state["machines"][machine_name]["hardwareDetected"] = True
            state["lastUpdatedMs"] = int(datetime.datetime.now().timestamp() * 1000)
        
        # Write back
        os.makedirs(os.path.dirname(MACHINES_JSON_PATH) or ".", exist_ok=True)
        with open(MACHINES_JSON_PATH, 'w') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[WARNING] Failed to sync to machines.json: {e}")


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

    # Sync to machines.json for dashboard
    _sync_to_machines_json(house, machine_name, status)

    return jsonify({"status": "ok", "house": house, "machine": machine_name, "new_status": status})


@app.route("/status", methods=["GET"])
def get_status():
    now = datetime.datetime.now()
    machines = {}
    for house_id in constants.HOUSES.keys():
        machines[house_id] = {}
        for machine_name in constants.MACHINE_NAMES:
            curr_user, end_time = storage.get_laundry_timer(house_id, machine_name)
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


def start_api():
    port = config.get("SENSOR_API_PORT", 5001)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
