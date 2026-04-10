import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from backend.app import app, socketio

if __name__ == '__main__':
    print("Démarrage de Kise Tigi...")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)