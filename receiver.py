from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)
DATA_FILE = 'data/machines.json'

@app.route('/api/update_sensor', methods=['POST'])
def update_sensor():
    """
    Receives updates from Shira's hardware sensors.
    Expected JSON payload:
    {
        "machine_id": "Washer One",
        "status": "in_use" or "available" or "idle"
    }
    """
    data = request.json
    machine_id = data.get('machine_id')
    new_status = data.get('status')

    if not machine_id or not new_status:
        return jsonify({"error": "machine_id and status required"}), 400

    # 1. Load the current state
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as file:
            state = json.load(file)
    else:
        state = {}

    # 2. Update the machine status
    if 'machines' not in state:
        state['machines'] = {}
    
    if machine_id in state['machines']:
        state['machines'][machine_id]['status'] = new_status
        state['machines'][machine_id]['hardwareDetected'] = True
        state['lastUpdatedMs'] = int(datetime.now().timestamp() * 1000)
    else:
        return jsonify({"error": f"Machine {machine_id} not found"}), 404

    # 3. Save the new state back to the file
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w') as file:
        json.dump(state, file, indent=2)

    # 4. Log the update
    print(f"[{datetime.now()}] Updated {machine_id} to {new_status}")

    return jsonify({
        "message": f"Machine {machine_id} updated to {new_status}",
        "success": True
    }), 200


@app.route('/api/status', methods=['GET'])
def get_status():
    """
    Returns current status of all machines (what the dashboard will call).
    """
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as file:
            state = json.load(file)
        return jsonify(state), 200
    else:
        return jsonify({"error": "No status data available"}), 404


if __name__ == '__main__':
    print("Starting Flask receiver on http://0.0.0.0:5000")
    print("POST to http://127.0.0.1:5000/api/update_sensor to update machine status")
    print("GET http://127.0.0.1:5000/api/status to fetch all machine data")
    app.run(host='0.0.0.0', port=5000, debug=True)
