import socket
import threading
import json
import time
import base64

SERVER_HOST = "127.0.0.2"
SERVER_PORT = 5000
SECRET_KEY = "distributed"

# =========================
# SIMPLE ENCRYPTION
# =========================
def encrypt(text):
    encrypted = "".join(chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)])) for i, c in enumerate(text))
    return base64.b64encode(encrypted.encode()).decode()

def decrypt(text):
    decoded = base64.b64decode(text).decode()
    return "".join(chr(ord(c) ^ ord(SECRET_KEY[i % len(SECRET_KEY)])) for i, c in enumerate(decoded))


def show_menu():
    """
    Displays available chat commands to the user.
    This improves usability and user guidance.
    """
    print("\n====== Distributed Chat Commands ======")
    print("/create <group_name>        - Create a new group")
    print("/join <group_name>          - Join an existing group")
    print("/group <group_name> <msg>   - Send message to a group")
    print("/private <user> <msg>       - Send a private message")
    print("/exit                       - Disconnect from server")
    print("/leave <group_name>         - Leave a group")
    print("=======================================\n")


# =========================
# RECEIVE THREAD
# =========================
def receive(sock):
    while True:
        try:
            msg = json.loads(sock.recv(4096).decode())
            t = msg["type"]

            if t == "group_message":
                print(f"\n[{msg['group']} #{msg['seq']}] {msg['sender']}: {decrypt(msg['content'])}")

            elif t == "private_message":
                print(f"\n[PRIVATE] {msg['sender']}: {decrypt(msg['content'])}")

            elif t == "system":
                print(f"\n[SYSTEM] {decrypt(msg['content'])}")

        except:
            break

# =========================
# HEARTBEAT THREAD
# =========================
def heartbeat(sock):
    while True:
        time.sleep(5)
        try:
            sock.sendall(json.dumps({"type": "heartbeat"}).encode())
        except:
            break

# =========================
# CLIENT MAIN
# =========================
def start():
    sock = socket.socket()
    sock.connect((SERVER_HOST, SERVER_PORT))

    username = input("Username: ")

    sock.sendall(json.dumps({
        "type": "connect",
        "sender": username
    }).encode())
    show_menu()

    threading.Thread(target=receive, args=(sock,), daemon=True).start()
    threading.Thread(target=heartbeat, args=(sock,), daemon=True).start()

    while True:
        cmd = input("> ")

        if cmd == "/exit":
            break

        elif cmd.startswith("/create"):
            _, g = cmd.split()
            sock.sendall(json.dumps({"type": "create_group", "target": g}).encode())

        elif cmd.startswith("/join"):
            _, g = cmd.split()
            sock.sendall(json.dumps({"type": "join_group", "target": g}).encode())

        elif cmd.startswith("/group"):
            _, g, m = cmd.split(maxsplit=2)
            sock.sendall(json.dumps({
                "type": "group_message",
                "target": g,
                "content": m
            }).encode())

        elif cmd.startswith("/private"):
            _, u, m = cmd.split(maxsplit=2)
            sock.sendall(json.dumps({
                "type": "private_message",
                "target": u,
                "content": m
            }).encode())

        elif cmd.startswith("/leave"):
            _, g = cmd.split()
            sock.sendall(json.dumps({
                "type": "leave_group",
                "target": g
            }).encode())

    sock.close()

if __name__ == "__main__":
    start()
