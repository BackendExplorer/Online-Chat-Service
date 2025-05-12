# ============================  server.py  ============================
import socket
import threading
import time
import secrets
import json
from Crypto.PublicKey import RSA
from Crypto.Cipher   import PKCS1_OAEP, AES


# ──── 共通暗号ユーティリティ（クラス化） ─────────────────────────────
class CryptoUtil:
    """AES-CFB128 + RSA-PKCS1_OAEP の簡易ラッパー"""
    # ---------- AES ----------
    @staticmethod
    def aes_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
        return AES.new(key, AES.MODE_CFB, iv=iv, segment_size=128).encrypt(data)

    @staticmethod
    def aes_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
        return AES.new(key, AES.MODE_CFB, iv=iv, segment_size=128).decrypt(data)

    # ---------- RSA ----------
    @staticmethod
    def rsa_encrypt(data: bytes, pub_key: RSA.RsaKey) -> bytes:
        return PKCS1_OAEP.new(pub_key).encrypt(data)

    @staticmethod
    def rsa_decrypt(data: bytes, priv_key: RSA.RsaKey) -> bytes:
        return PKCS1_OAEP.new(priv_key).decrypt(data)


# ──── 暗号鍵ハンドラ ────────────────────────────────────
class Encryption:
    def __init__(self):
        self.private_key = RSA.generate(2048)
        self.public_key  = self.private_key.publickey()
        self.peer_public_key = None
        self.aes_key = self.iv = None

    # --- RSA 公開鍵授受 --------------------------------
    def get_public_key_bytes(self) -> bytes:
        return self.public_key.export_key()

    def load_peer_public_key(self, data: bytes):
        self.peer_public_key = RSA.import_key(data)

    # --- 対称鍵（AES + IV） ------------------------------
    def decrypt_symmetric_key(self, encrypted: bytes):
        sym                    = CryptoUtil.rsa_decrypt(encrypted, self.private_key)
        self.aes_key, self.iv  = sym[:16], sym[16:32]

    def wrap_socket(self, sock: socket.socket):
        return EncryptedSocket(sock, self.aes_key, self.iv)


class EncryptedSocket:
    """send/recv を AES 暗号化する薄いラッパー"""
    def __init__(self, sock: socket.socket, key: bytes, iv: bytes):
        self.sock, self.key, self.iv = sock, key, iv

    # --- 内部 util --------------------------------------
    def _recvn(self, n: int) -> bytes:
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return data

    # --- 送受信 API -------------------------------------
    def sendall(self, data: bytes):
        ct = CryptoUtil.aes_encrypt(data, self.key, self.iv)
        self.sock.sendall(len(ct).to_bytes(4, 'big') + ct)
    send = sendall  # send() 互換

    def recv(self, bufsize: int = 4096) -> bytes:
        lb = self._recvn(4)
        if not lb:
            return b''
        return CryptoUtil.aes_decrypt(self._recvn(int.from_bytes(lb, 'big')),
                                      self.key, self.iv)

    def close(self):
        self.sock.close()


# ──── TCP サーバ ───────────────────────────────────────
class TCPServer:
    HEADER_MAX_BYTE   = 32
    TOKEN_MAX_BYTE    = 255

    room_tokens        = {}   # {room : [token, ...]}
    room_passwords     = {}   # {room : password}
    client_data        = {}   # {token: [addr, room, user, is_host, pw, last]}
    encryption_objects = {}   # {token: Encryption}

    def __init__(self, server_address: str, server_port: int):
        self.server_address, self.server_port = server_address, server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((server_address, server_port))
        self.sock.listen()

    # --- 接続受付 --------------------------------------
    def accept_tcp_connections(self):
        while True:
            conn, addr = self.sock.accept()
            try:
                self.handle_client_request(conn, addr)
            except Exception:
                conn.close()

    # --- 生ソケットで N バイト受信 -----------------------
    @staticmethod
    def _recvn(conn: socket.socket, n: int) -> bytes:
        data = b''
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return data

    # --- RSA-AES 鍵交換 --------------------------------
    def perform_key_exchange(self, conn: socket.socket):
        enc = Encryption()

        # ① クライアント公開鍵
        clen = int.from_bytes(self._recvn(conn, 4), 'big')
        enc.load_peer_public_key(self._recvn(conn, clen))

        # ② サーバ公開鍵
        spub = enc.get_public_key_bytes()
        conn.sendall(len(spub).to_bytes(4, 'big') + spub)

        # ③ 暗号化済み AES+IV
        elen = int.from_bytes(self._recvn(conn, 4), 'big')
        enc.decrypt_symmetric_key(self._recvn(conn, elen))

        # ④ 暗号化ソケットを返す
        return enc.wrap_socket(conn), enc

    # --- クライアント初回リクエスト処理 ------------------
    def handle_client_request(self, connection: socket.socket, client_address):
        connection, enc = self.perform_key_exchange(connection)

        # 最初の「ヘッダー＋ペイロード」
        data = connection.recv(4096)
        _, operation, _, _, room_name, payload = self.decode_message(data)

        # クライアント登録
        token = self.register_client(client_address, room_name, payload, operation)
        TCPServer.encryption_objects[token] = enc

        # 操作分岐
        if operation == 1:
            self.create_room(connection, room_name, token)
        elif operation == 2:
            self.join_room(connection, token)

    # --- 共通ヘッダー解析 -------------------------------
    def decode_message(self, data: bytes):
        header, body = data[:self.HEADER_MAX_BYTE], data[self.HEADER_MAX_BYTE:]
        room_len, operation, state = header[:3]
        payload_size               = int.from_bytes(header[3:], "big")

        room_name = body[:room_len].decode("utf-8")
        payload   = body[room_len:room_len + payload_size].decode("utf-8")
        return room_len, operation, state, payload_size, room_name, payload

    # --- クライアント登録 -------------------------------
    def register_client(self, addr, room_name, payload, operation):
        data  = json.loads(payload) if payload else {}
        token = secrets.token_bytes(self.TOKEN_MAX_BYTE)
        TCPServer.client_data[token] = [
            addr, "", data.get("username", ""),
            int(operation == 1), data.get("password", ""), time.time()
        ]
        return token

    # --- ルーム作成 -----------------------------------
    def create_room(self, conn, room_name, token):
        conn.sendall(token)
        self.room_tokens[room_name]  = [token]
        self.room_passwords[room_name] = TCPServer.client_data[token][4]
        TCPServer.client_data[token][1] = room_name

    # --- ルーム参加 -----------------------------------
    def join_room(self, conn, token):
        conn.sendall(str(list(self.room_tokens)).encode())
        _, _, _, _, room, payload = self.decode_message(conn.recv(4096))
        password = json.loads(payload).get("password", "")
        TCPServer.client_data[token][4] = password

        # ルーム存在 & パスワード検証
        if room not in self.room_tokens:
            conn.sendall(b"InvalidRoom"); return
        if self.room_passwords.get(room, "") != password \
           and self.room_passwords.get(room):
            conn.sendall(b"InvalidPassword"); return

        self.room_tokens[room].append(token)
        TCPServer.client_data[token][1] = room
        conn.sendall(token)


# ──── UDP サーバ ───────────────────────────────────────
class UDPServer:
    def __init__(self, server_address: str, server_port: int):
        self.server_address, self.server_port = server_address, server_port
        self.room_tokens     = TCPServer.room_tokens
        self.room_passwords  = TCPServer.room_passwords
        self.client_data     = TCPServer.client_data
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((server_address, server_port))

    # --- サーバ開始 -----------------------------------
    def start_udp_server(self):
        threading.Thread(target=self.handle_messages).start()
        threading.Thread(target=self.remove_inactive_clients, daemon=True).start()

    # --- メッセージ処理 -------------------------------
    def handle_messages(self):
        while True:
            data, client_addr = self.sock.recvfrom(4096)
            room, token, msg  = self.decode_message(data)

            # アドレス & タイムスタンプ更新
            self.client_data[token][0] = client_addr
            self.client_data[token][5] = time.time()

            self.broadcast_to_room(room, msg)

    # --- パケットデコード ------------------------------
    def decode_message(self, data):
        header, body       = data[:2], data[2:]
        room_len, tok_len  = header
        room_name          = body[:room_len].decode()
        token              = body[room_len:room_len + tok_len]
        enc_msg            = body[room_len + tok_len:]

        enc_obj = TCPServer.encryption_objects.get(token)
        if enc_obj and enc_obj.aes_key:
            msg = CryptoUtil.aes_decrypt(enc_msg, enc_obj.aes_key, enc_obj.iv).decode()
        else:
            msg = enc_msg.decode()
        return room_name, token, msg

    # --- ブロードキャスト ------------------------------
    def broadcast_to_room(self, room: str, message: str):
        for token in self.room_tokens.get(room, []):
            info = self.client_data.get(token)
            if not info or not info[0]:
                continue

            enc_obj = TCPServer.encryption_objects.get(token)
            if enc_obj and enc_obj.aes_key:
                enc_msg = CryptoUtil.aes_encrypt(message.encode(), enc_obj.aes_key, enc_obj.iv)
            else:
                enc_msg = message.encode()

            packet = (len(room).to_bytes(1,'big') + len(token).to_bytes(1,'big') +
                      room.encode() + token + enc_msg)
            try:
                self.sock.sendto(packet, info[0])
            except Exception:
                pass

    # --- 非アクティブ切断 ------------------------------
    def remove_inactive_clients(self):
        while True:
            cutoff = time.time() - 30
            for token, info in list(self.client_data.items()):
                if info[5] < cutoff:
                    try:
                        self.disconnect_inactive_client(token, info)
                    except Exception:
                        pass
            time.sleep(60)

    def disconnect_inactive_client(self, token, info):
        addr, room, username, is_host = info[:4]
        members = self.room_tokens.get(room, [])

        if is_host == 1:
            self.broadcast_to_room(room,
                f"System: ホストの{username}がタイムアウトしたためルームを終了します")
            self.broadcast_to_room(room, "exit!")

            for t in members:
                self.client_data.pop(t, None)
                TCPServer.encryption_objects.pop(t, None)
            self.room_tokens.pop(room, None)
            self.room_passwords.pop(room, None)
            try:
                self.sock.sendto("Timeout!".encode(), addr)
            except Exception:
                pass
        else:
            self.broadcast_to_room(room, f"System: {username}がタイムアウトにより退出しました。")
            try:
                self.sock.sendto("Timeout!".encode(), addr)
            except Exception:
                pass
            if token in members:
                members.remove(token)
            self.client_data.pop(token, None)
            TCPServer.encryption_objects.pop(token, None)


# ──── エントリポイント --------------------------------
if __name__ == "__main__":
    SERVER = '0.0.0.0'
    TCP_PORT, UDP_PORT = 9001, 9002
    tcp_srv = TCPServer(SERVER, TCP_PORT)
    udp_srv = UDPServer(SERVER, UDP_PORT)

    threading.Thread(target=tcp_srv.accept_tcp_connections, daemon=True).start()
    udp_srv.start_udp_server()