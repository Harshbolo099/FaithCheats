from flask import Flask, abort
from threading import Thread
from pymongo import MongoClient
import os

app = Flask('')

# Safely grab the database password from Render's environment variables
MONGO_URI = os.environ.get("MONGO_URI")

# We only try to connect if the URI exists (prevents crashes during local testing)
if MONGO_URI:
    client = MongoClient(MONGO_URI)
    db = client["faith_tickets"]
    collection = db["transcripts"]
else:
    collection = None

# 1. The Ping Route (Keeps the bot awake)
@app.route('/')
def home():
    return "Faith Cheats Bot & Transcript Server are online and alive!"

# 2. The Transcript Route (The Web Dashboard)
@app.route('/transcript/<ticket_id>')
def view_transcript(ticket_id):
    if not collection:
        return "Database not connected. Please set MONGO_URI in Render.", 500
        
    # Look up the ticket in the database
    ticket = collection.find_one({"_id": ticket_id})
    
    if ticket:
        # If found, spit out the raw HTML to the browser
        return ticket["html_content"]
    else:
        # If not found, show a 404 error
        abort(404, description="Transcript not found or invalid link.")

# 3. The Server Engine
def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
