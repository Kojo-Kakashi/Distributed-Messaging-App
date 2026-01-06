import socket
import threading
import json
import time
import base64
import datetime
import uuid
import os

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5000))
SECRET_KEY = "distributed"

clients = {}               # username -> socket
groups = {}                # group -> set(users)
group_seq = {}             # group -> sequence number
last_heartbeat = {}        # username -> timestamp
pending_msgs = {}          # username -> list of messages
lock = threading.Lock()

HISTORY_FILE = "chat_history.txt"

# =========================
# ENCRYPTION
# =========================
def encrypt(text):
    encrypted = "".join(
        chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)]))
        for i, c in enumerate(text)
    )
    return base64.b64encode(encrypted.encode()).decode()

def decrypt(text):
    decoded = base64.b64decode(text).decode()
    return "".join(
        chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)]))
        for i, c in enumerate(decoded)
    )

# =========================
# LOGGING & HISTORY
# =========================
def log_to_file(message):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{datetime.datetime.now()} - {message}\n")

def send_history(username):
    """Send stored chat history to reconnecting client"""
    try:
        with open(HISTORY_FILE, "r") as f:
            for line in f.readlines()[-20:]:  # last 20 messages
                send(username, {
                    "type": "history",
                    "content": encrypt(line.strip())
                })
    except:
        pass

# =========================
# SEND HELPERS
# =========================
def send(username, data):
    if username in clients:
        try:
            clients[username].sendall(json.dumps(data).encode())
            return True
        except:
            return False
    return False

def queue_message(username, data):
    pending_msgs.setdefault(username, []).append(data)

def deliver_pending(username):
    for msg in pending_msgs.get(username, []):
        send(username, msg)
    pending_msgs.pop(username, None)

def system_msg(username, text):
    send(username, {
        "type": "system",
        "content": encrypt(text)
    })

# =========================
# HEARTBEAT MONITOR
# =========================
def heartbeat_monitor():
    while True:
        time.sleep(5)
        now = time.time()
        for user in list(last_heartbeat):
            if now - last_heartbeat[user] > 15:
                log_to_file(f"{user} disconnected (timeout)")
                clients.pop(user, None)
                last_heartbeat.pop(user, None)

threading.Thread(target=heartbeat_monitor, daemon=True).start()

# =========================
# CLIENT HANDLER
# =========================
def handle_client(sock, addr):
    username = None
    try:
        while True:
            data = sock.recv(4096).decode()
            if not data:
                break

            msg = json.loads(data)
            t = msg["type"]

            if t == "heartbeat":
                last_heartbeat[username] = time.time()
                continue

            if t == "connect":
                username = msg["sender"]
                clients[username] = sock
                last_heartbeat[username] = time.time()
                system_msg(username, "Connected successfully")
                send_history(username)
                deliver_pending(username)

            elif t == "create_group":
                g = msg["target"]
                groups.setdefault(g, set())
                group_seq.setdefault(g, 0)
                system_msg(username, f"Group '{g}' created")

            elif t == "join_group":
                g = msg["target"]
                groups.setdefault(g, set()).add(username)
                system_msg(username, f"You joined {g}")

            elif t == "group_message":
                g = msg["target"]
                group_seq[g] += 1
                msg_id = str(uuid.uuid4())

                payload = {
                    "type": "group_message",
                    "group": g,
                    "seq": group_seq[g],
                    "sender": username,
                    "content": encrypt(msg["content"]),
                    "id": msg_id
                }

                for member in groups[g]:
                    if not send(member, payload):
                        queue_message(member, payload)

                system_msg(username, f"ACK: delivered seq {group_seq[g]}")
                log_to_file(f"[{g}] {username}: {msg['content']}")

            elif t == "private_message":
                payload = {
                    "type": "private_message",
                    "sender": username,
                    "content": encrypt(msg["content"]),
                    "id": str(uuid.uuid4())
                }

                if not send(msg["target"], payload):
                    queue_message(msg["target"], payload)

                system_msg(username, "ACK: private message delivered")
                log_to_file(f"[PM] {username} -> {msg['target']}")

            elif t == "leave_group":
                g = msg["target"]
                groups[g].remove(username)
                for m in groups[g]:
                    system_msg(m, f"{username} left {g}")

                system_msg(username, f"You left {g}")
                log_to_file(f"{username} left group {g}")

    finally:
        sock.close()
        if username:
            clients.pop(username, None)
            last_heartbeat.pop(username, None)

# =========================
# START SERVER
# =========================
def start():
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen()
    print(f"Server running on port {PORT}")

    while True:
        c, a = s.accept()
        threading.Thread(target=handle_client, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    start()
