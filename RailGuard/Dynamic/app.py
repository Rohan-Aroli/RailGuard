from flask import Flask, jsonify, request, render_template_string
import networkx as nx
import time
import threading
import copy
import os

app = Flask(__name__)

SAFETY_MARGIN_METERS = 200
# Acceleration applied per tick (km/h per simulation tick). User requested 10 km/h^2
# Here we interpret this as 10 km/h increase per tick (tick is 1 second in this simulation).
ACCELERATION_KMH_PER_TICK = 10.0

simulation_state = {
    'trains': {},
    'occupied_tracks': []
}

state_lock = threading.Lock()

track_data = {
    'nodes': [
        ("Ballari Junction", {"type": "station"}), ("Signal_BLR_1", {"type": "signal"}),
        ("Siding_Entry", {"type": "junction"}), ("Toranagallu", {"type": "station"}),
        ("Signal_TOR_1", {"type": "signal"}), ("Kudligi", {"type": "station"}),
        ("Hosapete", {"type": "station"})
    ],
    'edges': [
        ("Ballari Junction", "Signal_BLR_1", {"distance_km": 10, "base_time_mins": 8}),
        ("Signal_BLR_1", "Toranagallu", {"distance_km": 15, "base_time_mins": 12}),
        ("Toranagallu", "Signal_TOR_1", {"distance_km": 5, "base_time_mins": 4}),
        ("Signal_TOR_1", "Kudligi", {"distance_km": 20, "base_time_mins": 15}),
        ("Toranagallu", "Hosapete", {"distance_km": 25, "base_time_mins": 20}),
        ("Ballari Junction", "Siding_Entry", {"distance_km": 12, "base_time_mins": 15}),
        ("Siding_Entry", "Toranagallu", {"distance_km": 12, "base_time_mins": 15}),
    ]
}

def create_railway_graph():
    G = nx.Graph()
    G.add_nodes_from(track_data['nodes'])
    G.add_edges_from(track_data['edges'])
    for u, v, data in G.edges(data=True):
        data['time_cost'] = data.get('base_time_mins', 20)
    return G

def find_optimal_path(graph, start_node, end_node):
    try:
        return nx.astar_path(graph, start_node, end_node, weight="time_cost")
    except nx.NetworkXNoPath:
        return None

def update_graph_with_traffic(graph, current_state):
    for u, v, data in graph.edges(data=True):
        cost = data.get('base_time_mins', 20)
        if (u, v) in current_state['occupied_tracks'] or (v, u) in current_state['occupied_tracks']:
            cost = 9999
        graph[u][v]['time_cost'] = cost

def calculate_braking_distance(speed_kmh, braking_rate=0.8):
    speed_mps = speed_kmh / 3.6
    return (speed_mps ** 2) / (2 * braking_rate)

def calculate_dynamic_speed_limit(following_train, train_ahead):
    braking_distance_ahead = calculate_braking_distance(train_ahead['speed_kmh'], train_ahead['braking_rate'])
    safe_point_meters = train_ahead['position_km'] * 1000 - braking_distance_ahead - SAFETY_MARGIN_METERS
    distance_to_safe_point = safe_point_meters - (following_train['position_km'] * 1000)
    
    if distance_to_safe_point <= 0:
        return 0
        
    safe_speed_mps = (2 * distance_to_safe_point * following_train['braking_rate']) ** 0.5
    safe_speed_kmh = safe_speed_mps * 3.6
    return min(safe_speed_kmh, following_train['max_speed_kmh'])

def simulation_loop():
    TICK_RATE_SECONDS = 1.0

    while True:
        with state_lock:
            sorted_trains = sorted(simulation_state['trains'].values(), key=lambda t: t['position_km'])

            # --- (Inside simulation_loop) ---
            for i, current_train in enumerate(sorted_trains):
                train_ahead = None 
                if i + 1 < len(sorted_trains):
                    train_ahead = sorted_trains[i+1]

                # If the train is not yet dispatched, it must stay stopped
                if not current_train.get('dispatched', False):
                    current_train['speed_kmh'] = 0.0
                    continue

                # Default desired limit: allow trains to accelerate up to their configured maximum speed
                desired_limit = current_train.get('max_speed_kmh', current_train.get('target_speed_kmh', 0))

                # If there's a train ahead, calculate a more restrictive speed limit
                safe_speed_limit = desired_limit
                if train_ahead:
                    safe_speed_limit = min(safe_speed_limit, calculate_dynamic_speed_limit(current_train, train_ahead))

                # Now, apply acceleration or braking based on the final calculated limit
                if safe_speed_limit < current_train['speed_kmh']:
                    # Brake immediately for safety (braking rate unchanged)
                    current_train['speed_kmh'] = safe_speed_limit
                else:
                    # Accelerate towards the speed limit using configured acceleration per tick
                    current_train['speed_kmh'] = min(safe_speed_limit, current_train['speed_kmh'] + ACCELERATION_KMH_PER_TICK)

            for train_id, train in simulation_state['trains'].items():
                # Only update position if the train has been dispatched; safety: undispatched trains should remain at start
                if not train.get('dispatched', False):
                    continue
                distance_moved_km = train['speed_kmh'] * (TICK_RATE_SECONDS / 3600)
                train['position_km'] += distance_moved_km

            sorted_trains_after_update = sorted(simulation_state['trains'].values(), key=lambda t: t['position_km'])
            for i in range(len(sorted_trains_after_update) - 1):
                following_train = sorted_trains_after_update[i]
                train_ahead = sorted_trains_after_update[i+1]

                braking_dist_ahead_meters = calculate_braking_distance(train_ahead['speed_kmh'], train_ahead['braking_rate'])
                total_safety_bubble_meters = braking_dist_ahead_meters + SAFETY_MARGIN_METERS

                actual_distance_meters = (train_ahead['position_km'] - following_train['position_km']) * 1000

                if actual_distance_meters < total_safety_bubble_meters:
                    print(f"🔴 SAFETY ALERT: {following_train['id']} has breached the safety bubble of {train_ahead['id']}!")
                    print(f"   > Required Distance: {total_safety_bubble_meters:.2f}m, Actual Distance: {actual_distance_meters:.2f}m")
            display_simulation(simulation_state) # This will draw the updated state
        time.sleep(TICK_RATE_SECONDS)


def display_simulation(state):
    """
    Clears the terminal and draws a simple text-based representation of the simulation.
    """
    # Define the visual scale of our track
    TRACK_VISUAL_LENGTH_CHARS = 100  # How many characters wide the track is
    TOTAL_TRACK_KM = 10.0            # The total length of the railway in km this represents (reduced to 10 km)

    # --- Clear the screen ---
    # 'nt' is for Windows, 'posix' is for Mac/Linux
    os.system('cls' if os.name == 'nt' else 'clear')

    print("--- RAILWAY TRAFFIC CONTROL SIMULATION ---")
    print(f"Ballari Control Room - {time.strftime('%H:%M:%S')}")
    print("-" * TRACK_VISUAL_LENGTH_CHARS)

    # --- Prepare the track display ---
    track = ['.'] * TRACK_VISUAL_LENGTH_CHARS
    
    sorted_trains = sorted(state['trains'].values(), key=lambda t: t['position_km'])

    for train in sorted_trains:
        # --- Map the train's real position (km) to a character position on the visual track ---
        pos_ratio = train['position_km'] / TOTAL_TRACK_KM
        char_position = int(pos_ratio * TRACK_VISUAL_LENGTH_CHARS)
        
        # Ensure the character position is within the track bounds
        char_position = max(0, min(TRACK_VISUAL_LENGTH_CHARS - 1, char_position))
        
        # Use the first letter of the train ID as its icon (E, L, G)
        # If a spot is taken, show '*' to indicate close proximity
        if track[char_position] == '.':
            track[char_position] = train['id'][0]
        else:
            track[char_position] = '*'

    print(''.join(track))
    print("-" * TRACK_VISUAL_LENGTH_CHARS)

    # --- Print the detailed status of each train ---
    print("STATUS DASHBOARD:")
    for train in sorted_trains:
        print(f"  > {train['id']}: \t Pos: {train['position_km']:.2f} km | Speed: {train['speed_kmh']:.2f} km/h")


def dispatcher_loop(dispatch_sequence, delay_between_dispatches=2.0):
    """Marks trains as dispatched in the exact order provided, ignoring priority.
    dispatch_sequence is a list of train IDs in the order they should be released.
    """
    # Dispatch each train in order exactly once
    for i, tid in enumerate(dispatch_sequence):
        with state_lock:
            if tid in simulation_state['trains'] and not simulation_state['trains'][tid].get('dispatched', False):
                simulation_state['trains'][tid]['dispatched'] = True
                print(f"[DISPATCH] Train {tid} dispatched at {time.strftime('%H:%M:%S')}")
        # Sleep after dispatching unless it's the last one
        if i < len(dispatch_sequence) - 1:
            time.sleep(delay_between_dispatches)

@app.route("/")
def home():
    return "<h1>Railway AI Simulation API (Live)</h1><p>Endpoints: /api/state, /api/path/start/end</p>"

@app.route("/api/state")
def get_current_state():
    with state_lock:
        return jsonify(copy.deepcopy(simulation_state))


@app.route('/api/add_train', methods=['POST'])
def add_train():
    """Add a new train dynamically. Expects JSON with fields:
    id (optional, will be autogenerated if missing), category ('goods'|'local'|'express'), priority (int), max_speed_kmh (float)
    """
    data = request.get_json() or {}
    category = (data.get('category') or 'goods').lower()
    priority = int(data.get('priority', 3))
    max_speed = float(data.get('max_speed_kmh', 60.0))
    # Determine base target speed per category if not supplied
    if 'target_speed_kmh' in data:
        target_speed = float(data['target_speed_kmh'])
    else:
        if category == 'express':
            target_speed = min(max_speed, 90.0)
        elif category == 'local':
            target_speed = min(max_speed, 40.0)
        else:
            target_speed = min(max_speed, 30.0)

    # Generate an ID if not provided
    base = (data.get('id') or f"{category.capitalize()}_")
    with state_lock:
        # find a unique numeric suffix
        suffix = 1
        candidate = base + str(suffix)
        existing = set(simulation_state['trains'].keys())
        while candidate in existing:
            suffix += 1
            candidate = base + str(suffix)

        new_train = {
            'id': candidate,
            'position_km': float(data.get('position_km', 0.0)),
            'speed_kmh': 0.0,
            'target_speed_kmh': target_speed,
            'max_speed_kmh': max_speed,
            'braking_rate': float(data.get('braking_rate', 0.8 if category in ('express','local') else 0.6)),
            'priority': priority,
            # default: newly added trains are dispatched immediately onto the track
            'dispatched': True
        }

        simulation_state['trains'][candidate] = new_train

    return jsonify({'status': 'ok', 'train_id': candidate, 'train': new_train})

@app.route("/api/path/<string:start_node>/<string:end_node>")
def get_path(start_node, end_node):
    with state_lock:
        current_state = copy.deepcopy(simulation_state)

    railway_map = create_railway_graph()
    update_graph_with_traffic(railway_map, current_state)
    path = find_optimal_path(railway_map, start_node, end_node)
    
    result = {
        "start_node": start_node,
        "end_node": end_node,
        "optimal_path": path,
        "blocked_tracks_at_moment": current_state["occupied_tracks"]
    }
    return jsonify(result)



@app.route("/viewer")
def viewer():
    # This HTML is now much more advanced, with CSS for styling and JS for rendering the state.
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Railway Simulation Viewer</title>
        <style>
            body { font-family: monospace, sans-serif; background-color: #1e1e1e; color: #d4d4d4; padding: 20px; }
            h1 { color: #569cd6; }
            .container { background-color: #252526; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
            #track { 
                font-size: 18px; 
                white-space: pre; 
                overflow-x: auto; 
                border: 1px solid #444;
                padding: 10px;
                letter-spacing: 2px;
            }
            .train { font-weight: bold; }
            .express { color: #c586c0; } /* Purple */
            .local { color: #4ec9b0; }   /* Teal */
            .goods { color: #dcdcaa; }   /* Yellow */
            .collision { color: #f44747; background-color: #ffcdd2; border-radius: 2px;} /* Red */

            #dashboard table { width: 100%; border-collapse: collapse; }
            #dashboard th, #dashboard td { padding: 8px; text-align: left; border-bottom: 1px solid #444; }
            #dashboard th { color: #9cdcfe; }
        </style>
    </head>
    <body>
        <h1>🚂 Railway Simulation Viewer</h1>
        <p>Live from Ballari Control Room - <span id="clock">{{ time_str }}</span></p>

        <div class="container">
            <h2>Live Track</h2>
            <div id="track">Loading track...</div>
        </div>

        <div class="container">
            <h2>Add a Train</h2>
            <form id="add-train-form">
                <label>Category:
                    <select id="train-category">
                        <option value="goods">Goods</option>
                        <option value="local">Local</option>
                        <option value="express">Express</option>
                    </select>
                </label>
                <label>Priority: <input id="train-priority" type="number" value="3" min="1" max="5" /></label>
                <label>Max Speed (km/h): <input id="train-maxspeed" type="number" value="60" /></label>
                <button type="submit">Add Train</button>
            </form>
            <div id="add-train-result" style="margin-top:8px;color:#9cdcfe"></div>
        </div>

        <div class="container" id="dashboard">
            <h2>Status Dashboard</h2>
            <table>
                <thead><tr><th>ID</th><th>Position (km)</th><th>Speed (km/h)</th></tr></thead>
                <tbody id="train-data"></tbody>
            </table>
        </div>

        <script>
            // These constants must match the ones in your Python display_simulation function
            const TRACK_VISUAL_LENGTH_CHARS = 100;
            const TOTAL_TRACK_KM = 10.0;

            function updateClock() {
                const now = new Date();
                document.getElementById('clock').textContent = now.toLocaleTimeString();
            }

            async function updateSimulationView() {
                try {
                    const response = await fetch("/api/state");
                    const state = await response.json();
                    
                    // --- Render the Track ---
                    let track = Array(TRACK_VISUAL_LENGTH_CHARS).fill('·');
                    const sortedTrains = Object.values(state.trains).sort((a, b) => a.position_km - b.position_km);

                    for (const train of sortedTrains) {
                        const posRatio = train.position_km / TOTAL_TRACK_KM;
                        let charPosition = Math.floor(posRatio * TRACK_VISUAL_LENGTH_CHARS);
                        charPosition = Math.max(0, Math.min(TRACK_VISUAL_LENGTH_CHARS - 1, charPosition));

                        let trainClass = 'train';
                        if (train.id.includes('Express')) trainClass += ' express';
                        if (train.id.includes('Local')) trainClass += ' local';
                        if (train.id.includes('Goods')) trainClass += ' goods';

                        const trainIcon = `<span class="${trainClass}">${train.id[0]}</span>`;

                        if (track[charPosition] === '·') {
                            track[charPosition] = trainIcon;
                        } else {
                            track[charPosition] = `<span class="collision">*</span>`; // Collision/overlap icon
                        }
                    }
                    document.getElementById('track').innerHTML = track.join('');

                    // --- Render the Dashboard Table ---
                    const tableBody = document.getElementById('train-data');
                    tableBody.innerHTML = ''; // Clear previous data
                    for (const train of sortedTrains) {
                        const row = `<tr>
                            <td>${train.id}</td>
                            <td>${train.position_km.toFixed(2)}</td>
                            <td>${train.speed_kmh.toFixed(2)}</td>
                        </tr>`;
                        tableBody.innerHTML += row;
                    }

                } catch (error) {
                    console.error("Failed to fetch simulation state:", error);
                    document.getElementById('track').textContent = "Error connecting to simulation server.";
                }
            }

            // --- Add train form handling ---
            document.getElementById('add-train-form').addEventListener('submit', async function (ev) {
                ev.preventDefault();
                const category = document.getElementById('train-category').value;
                const priority = parseInt(document.getElementById('train-priority').value, 10);
                const maxSpeed = parseFloat(document.getElementById('train-maxspeed').value);

                try {
                    const resp = await fetch('/api/add_train', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ category: category, priority: priority, max_speed_kmh: maxSpeed })
                    });
                    const json = await resp.json();
                    document.getElementById('add-train-result').textContent = 'Added ' + json.train_id;
                    // Refresh view immediately
                    updateSimulationView();
                } catch (err) {
                    document.getElementById('add-train-result').textContent = 'Failed to add train';
                    console.error(err);
                }
            });
            
            // Initial load and then set intervals to update
                    updateClock();
                    updateSimulationView();
                    setInterval(updateClock, 1000);
                    setInterval(updateSimulationView, 1000);
        </script>
    </body>
    </html>
    """, time_str=time.strftime('%H:%M:%S')) # Pass current time for initial load

if __name__ == "__main__":
    # Start simulation thread
    simulation_thread = threading.Thread(target=simulation_loop, daemon=True)
    simulation_thread.start()

    # Dispatch sequence requested by user (ignore priority):
    # 1.express, 2.local, 3.local, 4.goods, 5.express, 6.goods, 7.goods
    dispatch_sequence = [
        # 'Express_101',
        # 'Local_201',
        # 'Local_202',
        # 'Goods_301',
        # 'Express_102',
        # 'Goods_302',
        # 'Goods_303'
    ]

    dispatcher_thread = threading.Thread(target=dispatcher_loop, args=(dispatch_sequence, 2.0), daemon=True)
    dispatcher_thread.start()

    app.run(debug=True, use_reloader=False)