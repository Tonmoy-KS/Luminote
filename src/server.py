# server.py
# Luminote Online Leaderboard Server

from flask import Flask, request, jsonify
import json
import os
from datetime import datetime

# --- Configuration ---
# This is the name of the file that will act as our simple database.
DB_FILE = 'leaderboard.json'
# The maximum number of scores to keep for any single song.
MAX_SCORES_PER_SONG = 100

# --- Flask App Initialization ---
# This creates the web server application.
app = Flask(__name__)

# --- Helper Functions ---
def get_db():
    """
    Loads the leaderboard data from the JSON file.
    If the file doesn't exist, it returns an empty dictionary.
    """
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, 'r') as f:
            # Handle the case where the file is empty
            content = f.read()
            if not content:
                return {}
            return json.loads(content)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error reading database file: {e}")
        # Return an empty dict to prevent a crash, the next save will fix the file.
        return {}

def save_db(db):
    """
    Saves the provided dictionary to the leaderboard JSON file.
    This function overwrites the file with the new data.
    """
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(db, f, indent=4)
    except IOError as e:
        print(f"Error writing to database file: {e}")

# --- API Endpoints (Web Routes) ---

@app.route('/submit', methods=['POST'])
def submit_score():
    """
    Handles incoming score submissions from the game client.
    Expects a JSON payload with 'name', 'score', and 'song'.
    Validates the data, adds it to the database, sorts the scores,
    and trims the list to prevent it from growing indefinitely.
    """
    # 1. Get the data sent by the game
    data = request.get_json()

    # 2. Validate the incoming data
    if not data or 'name' not in data or 'score' not in data or 'song' not in data:
        return jsonify({"error": "Invalid data format. Required fields: name, score, song"}), 400
    
    try:
        player_name = str(data['name']).strip()
        score = int(data['score'])
        song_id = str(data['song']).strip()
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid data types for name, score, or song"}), 400

    if not player_name or not song_id:
        return jsonify({"error": "Name and song fields cannot be empty"}), 400

    # 3. Load the current database
    db = get_db()
    
    # 4. Prepare the new score entry
    new_score_entry = {
        'name': player_name,
        'score': score,
        'timestamp': datetime.utcnow().isoformat() + "Z" # Add a timestamp (optional but good practice)
    }
    
    # 5. Add the new score to the correct song's list
    if song_id not in db:
        db[song_id] = []
    
    db[song_id].append(new_score_entry)
    
    # 6. Sort the scores for this song in descending order (highest first)
    db[song_id] = sorted(db[song_id], key=lambda x: x['score'], reverse=True)
    
    # 7. Trim the list to the maximum allowed size
    db[song_id] = db[song_id][:MAX_SCORES_PER_SONG]
    
    # 8. Save the updated database back to the file
    save_db(db)
    
    print(f"Received score: {player_name} got {score} on {song_id}")
    return jsonify({"success": True, "message": "Score submitted successfully"}), 200

@app.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """
    Serves the leaderboard data for a specific song.
    The song is specified as a query parameter in the URL, e.g., /leaderboard?song=MySongID
    """
    # 1. Get the 'song' ID from the URL query parameters
    song_id = request.args.get('song')
    
    # 2. Validate that a song ID was provided
    if not song_id:
        return jsonify({"error": "Song ID is required as a query parameter"}), 400
    
    # 3. Load the database
    db = get_db()
    
    # 4. Get the scores for the requested song, or an empty list if the song isn't found
    scores_for_song = db.get(song_id, [])
    
    print(f"Served leaderboard for song: {song_id}")
    return jsonify(scores_for_song)

# --- Main Entry Point ---
# This block ensures the server only runs when the script is executed directly.
if __name__ == '__main__':
    # host='0.0.0.0' makes the server accessible from other devices on the same network.
    app.run(host='0.0.0.0', port=5000, debug=True)