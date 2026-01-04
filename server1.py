import socket
import threading
import json
import time
import base64
import datetime
import uuid

HOST = "0.0.0.0"
PORT = 5000
SECRET_KEY = "distributed"

clients = {}           # username -> socket
groups = {}            # group -> set(users)
group_seq = {}         # group -> sequence number
last_heartbeat = {}    # username -> timestamp
lock = threading.Lock()

HISTORY_FILE = "chat_history.txt"

# =========================
# SIMPLE ENCRYPTION
# =========================
def encrypt(text):
    encrypted = "".join(chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)])) for i, c in enumerate(text))
    return base64.b64encode(encrypted.encode()).decode()

def decrypt(text):
    decoded = base64.b64decode(text).decode()
    return "".join(chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)])) for i, c in enumerate(decoded))

# =========================
# LOGGING
# =========================
def log_to_file(message):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{datetime.datetime.now()} - {message}\n")

# =========================
# SEND HELPERS
# =========================
def send(username, data):
    if username in clients:
        clients[username].sendall(json.dumps(data).encode())

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
        with lock:
            now = time.time()
            for user in list(last_heartbeat):
                if now - last_heartbeat[user] > 15:
                    log_to_file(f"{user} timed out")
                    del clients[user]
                    del last_heartbeat[user]

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
            msg_type = msg["type"]

            # HEARTBEAT
            if msg_type == "heartbeat":
                last_heartbeat[username] = time.time()
                continue

            # CONNECT
            if msg_type == "connect":
                username = msg["sender"]
                clients[username] = sock
                last_heartbeat[username] = time.time()
                system_msg(username, "Connected successfully")

            # CREATE GROUP
            elif msg_type == "create_group":
                g = msg["target"]
                groups.setdefault(g, set())
                group_seq.setdefault(g, 0)
                system_msg(username, f"Group '{g}' created")

            # JOIN GROUP
            elif msg_type == "join_group":
                g = msg["target"]
                groups[g].add(username)
                system_msg(username, f"You joined {g}")

            # GROUP MESSAGE
            elif msg_type == "group_message":
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
                    send(member, payload)

                # ACK
                system_msg(username, f"Message delivered (seq {group_seq[g]})")
                log_to_file(f"[{g}] {username}: {msg['content']}")

            # PRIVATE MESSAGE
            elif msg_type == "private_message":
                msg_id = str(uuid.uuid4())
                send(msg["target"], {
                    "type": "private_message",
                    "sender": username,
                    "content": encrypt(msg["content"]),
                    "id": msg_id
                })
                system_msg(username, "Private message delivered")
                log_to_file(f"[PM] {username} -> {msg['target']}")

            elif msg_type == "leave_group":
                g = msg["target"]

                if g not in groups or username not in groups[g]:
                    system_msg(username, f"You are not a member of group '{g}'")
                    return

                # Remove user from group
                groups[g].remove(username)

                # Notify remaining members
                for member in groups[g]:
                    system_msg(member, f"{username} left group '{g}'")

                system_msg(username, f"You left group '{g}'")

                log_to_file(
                    "SYSTEM",
                    f"{username} left group {g}"
                )

                # Auto-delete group if empty
                if len(groups[g]) == 0:
                    del groups[g]
                    del group_seq[g]
                    log_to_file(
                        "SYSTEM",
                        f"Group '{g}' deleted (no members left)"
                    )
    except:
        pass
    finally:
        sock.close()

# =========================
# START SERVER
# =========================
def start():
    s = socket.socket()
    s.bind((HOST, PORT))
    s.listen()
    print("Server running...")

    while True:
        c, a = s.accept()
        threading.Thread(target=handle_client, args=(c, a), daemon=True).start()

if __name__ == "__main__":
    start()
