from flask import Flask, jsonify, request
from threading import Thread
from time import sleep
from os import getpid, kill
from signal import SIGINT

app = Flask(__name__)

@app.route('/read_file/<path:filename>')
def read_file(filename):
    try:
        with open(filename, 'r') as file:
            content = file.read()
        return jsonify({"content": content})
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def shutdown_server():
    sleep(10)  # Gracefully shutdown after 10 seconds
    print("Shutting down server gracefully...")
    kill(getpid(), SIGINT)

if __name__ == '__main__':
    # Start the shutdown timer in a separate thread
    Thread(target=shutdown_server, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
