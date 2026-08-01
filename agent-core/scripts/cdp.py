"""極簡 CDP 客戶端：只用標準函式庫做 WebSocket handshake + frame 收送。"""
import json, socket, base64, os, struct

def ws_connect(url):
    _, rest = url.split("://", 1)
    hostport, path = rest.split("/", 1)
    host, port = hostport.split(":")
    s = socket.create_connection((host, int(port))); s.settimeout(60)
    key = base64.b64encode(os.urandom(16)).decode()
    s.sendall(f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
              f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode())
    buf = b""
    while b"\r\n\r\n" not in buf: buf += s.recv(4096)
    return s

def send(s, msg):
    p = json.dumps(msg).encode(); mask = os.urandom(4); n = len(p)
    hdr = b"\x81"
    if n < 126: hdr += bytes([0x80 | n])
    elif n < 65536: hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
    else: hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
    s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(p)))

def recv(s):
    def rd(n):
        b = b""
        while len(b) < n:
            c = s.recv(n - len(b))
            if not c: raise EOFError
            b += c
        return b
    while True:
        h = rd(2); op = h[0] & 0x0F; ln = h[1] & 0x7F
        if ln == 126: ln = struct.unpack(">H", rd(2))[0]
        elif ln == 127: ln = struct.unpack(">Q", rd(8))[0]
        pay = rd(ln)
        if op == 1: return json.loads(pay)

def call(s, i, method, params=None):
    send(s, {"id": i, "method": method, "params": params or {}})
    while True:
        m = recv(s)
        if m.get("id") == i: return m
