from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "Faith Cheats Bot is online and alive!"

def run():
    # Render assigns a specific port, this grabs it so it doesn't crash
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()