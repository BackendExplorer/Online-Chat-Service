import socket
import threading
import time
import secrets
import json
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES


class KeyExchangeManager:
    def __init__(self):
        self._private_key = RSA.generate(2048)

    def public_key_bytes(self):
        return self._private_key.publickey().export_key()

    def decrypt_symmetric_key(self, encrypted):
        sym = PKCS1_OAEP.new(self._private_key).decrypt(encrypted)
        return sym[:16], sym[16:]


class SymmetricCipher:
    def __init__(self, key, iv):
        self.key = key
        self.iv  = iv

    def encrypt(self, data):
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).encrypt(data)

    def decrypt(self, data):
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).decrypt(data)


class EncryptedSocket:
    def __init__(self, sock, cipher):
        self.sock = sock
        self.cipher = cipher

    def _recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    def sendall(self, plaintext):
        ciphertext = self.cipher.encrypt(plaintext)
        self.sock.sendall(len(ciphertext).to_bytes(4, 'big') + ciphertext)

    def recv(self):
        length = self._recv_exact(4)
        if not length:
            return b''
        ciphertext = self._recv_exact(int.from_bytes(length, 'big'))
        return self.cipher.decrypt(ciphertext)

    def close(self):
        self.sock.close()

# ──── TCP サーバ ───────────────────────────────────────
class TCPServer:
    HEADER_MAX_BYTE = 32
    TOKEN_MAX_BYTE  = 255

    room_tokens        = {}   # {room : [token, ...]}
    room_passwords     = {}   # {room : password}
    client_data        = {}   # {token: [addr, room, user, is_host, pw, last]}
    encryption_objects = {}   # {token: SymmetricCipher}

    def __init__(self, server_address: str, server_port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((server_address, server_port))
        self.sock.listen()

    # クライアント接続受付ループ
    def accept_tcp_connections(self):
        while True:
            conn, addr = self.sock.accept()
            try:
                self._handle_client(conn, addr)
            except Exception:
                conn.close()

    # クライアント初回リクエスト処理
    def _handle_client(self, connection: socket.socket, client_address):
        enc_sock, cipher = self._perform_key_exchange(connection)

        # 「ヘッダー＋ペイロード」を受信
        data = enc_sock.recv()
        _, op, _, _, room, payload = self._decode_message(data)

        # クライアント登録
        token = self._register_client(client_address, room, payload, op)
        TCPServer.encryption_objects[token] = cipher

        # 操作に応じた処理
        if op == 1:
            self._create_room(enc_sock, room, token)
        elif op == 2:
            self._join_room(enc_sock, token)

    # RSA-AES 鍵交換
    def _perform_key_exchange(self, conn: socket.socket):
        kem = KeyExchangeManager()

        # (1) 公開鍵送信
        pub = kem.public_key_bytes()
        conn.sendall(len(pub).to_bytes(4, 'big') + pub)

        # (2) 暗号化済 AES+IV 受信
        enc_len = int.from_bytes(self._recvn(conn, 4), 'big')
        enc_key = self._recvn(conn, enc_len)
        aes_key, aes_iv = kem.decrypt_symmetric_key(enc_key)

        # (3) 暗号ソケット作成
        cipher   = SymmetricCipher(aes_key, aes_iv)
        enc_sock = EncryptedSocket(conn, cipher)
        return enc_sock, cipher

    # 固定長受信 (生ソケット)
    @staticmethod
    def _recvn(conn: socket.socket, n: int) -> bytes:
        data = b''
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return data

    # TCP メッセージデコード
    def _decode_message(self, data: bytes):
        header, body = data[:self.HEADER_MAX_BYTE], data[self.HEADER_MAX_BYTE:]
        room_len, operation, state = header[:3]
        payload_size = int.from_bytes(header[3:], "big")
        room_name = body[:room_len].decode()
        payload   = body[room_len:room_len + payload_size].decode()
        return room_len, operation, state, payload_size, room_name, payload

    # クライアント登録
    def _register_client(self, addr, room_name, payload, operation):
        info  = json.loads(payload) if payload else {}
        token = secrets.token_bytes(self.TOKEN_MAX_BYTE)
        TCPServer.client_data[token] = [
            addr, "", info.get("username", ""),
            int(operation == 1), info.get("password", ""), time.time()
        ]
        return token

    # ルーム作成
    def _create_room(self, conn: EncryptedSocket, room_name: str, token: bytes):
        conn.sendall(token)
        self.room_tokens[room_name]   = [token]
        self.room_passwords[room_name] = TCPServer.client_data[token][4]
        TCPServer.client_data[token][1] = room_name

    # ルーム参加
    def _join_room(self, conn: EncryptedSocket, token: bytes):
        conn.sendall(str(list(self.room_tokens)).encode())
        _, _, _, _, room, payload = self._decode_message(conn.recv())
        password = json.loads(payload).get("password", "")
        TCPServer.client_data[token][4] = password

        if room not in self.room_tokens:
            conn.sendall(b"InvalidRoom"); return
        if self.room_passwords.get(room, "") != password and self.room_passwords.get(room):
            conn.sendall(b"InvalidPassword"); return

        self.room_tokens[room].append(token)
        TCPServer.client_data[token][1] = room
        conn.sendall(token)


# ──── UDP サーバ ───────────────────────────────────────
class UDPServer:
    def __init__(self, server_address: str, server_port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((server_address, server_port))
        self.room_tokens        = TCPServer.room_tokens
        self.room_passwords     = TCPServer.room_passwords
        self.client_data        = TCPServer.client_data
        self.encryption_objects = TCPServer.encryption_objects

    # サーバ開始
    def start_udp_server(self):
        threading.Thread(target=self._handle_messages).start()
        threading.Thread(target=self._remove_inactive_clients, daemon=True).start()

    # 受信処理
    def _handle_messages(self):
        while True:
            data, client_addr = self.sock.recvfrom(4096)
            room, token, msg  = self._decode_message(data)

            # アドレス・タイムスタンプ更新
            self.client_data[token][0] = client_addr
            self.client_data[token][5] = time.time()

            self._broadcast(room, msg)

    # パケットデコード
    def _decode_message(self, data: bytes):
        header, body   = data[:2], data[2:]
        room_len, tok_len = header
        room_name      = body[:room_len].decode()
        token          = body[room_len:room_len + tok_len]
        enc_msg        = body[room_len + tok_len:]

        cipher = self.encryption_objects.get(token)
        if cipher:
            msg = cipher.decrypt(enc_msg).decode()
        else:
            msg = enc_msg.decode()

        return room_name, token, msg

    # ブロードキャスト
    def _broadcast(self, room: str, message: str):
        for token in self.room_tokens.get(room, []):
            info = self.client_data.get(token)
            if not info or not info[0]:
                continue

            cipher = self.encryption_objects.get(token)
            if cipher:
                enc_msg = cipher.encrypt(message.encode())
            else:
                enc_msg = message.encode()

            packet = (len(room).to_bytes(1, 'big') + len(token).to_bytes(1, 'big') +
                      room.encode() + token + enc_msg)
            try:
                self.sock.sendto(packet, info[0])
            except Exception:
                pass

    # 非アクティブクライアント除去
    def _remove_inactive_clients(self):
        while True:
            cutoff = time.time() - 100
            for token, info in list(self.client_data.items()):
                if info[5] < cutoff:
                    try:
                        self._disconnect(token, info)
                    except Exception:
                        pass
            time.sleep(60)

    def _disconnect(self, token, info):
        addr, room, username, is_host = info[:4]
        members = self.room_tokens.get(room, [])

        if is_host == 1:
            self._broadcast(room, f"System: ホストの{username}がタイムアウトしたためルームを終了します")
            self._broadcast(room, "exit!")

            for t in members:
                self.client_data.pop(t, None)
                self.encryption_objects.pop(t, None)
            self.room_tokens.pop(room, None)
            self.room_passwords.pop(room, None)
            try:
                self.sock.sendto(b"Timeout!", addr)
            except Exception:
                pass
        else:
            self._broadcast(room, f"System: {username}がタイムアウトにより退出しました。")
            try:
                self.sock.sendto(b"Timeout!", addr)
            except Exception:
                pass
            if token in members:
                members.remove(token)
            self.client_data.pop(token, None)
            self.encryption_objects.pop(token, None)


# ──── メインエントリ ────────────────────────────────
if __name__ == "__main__":
    SERVER      = '0.0.0.0'
    TCP_PORT    = 9001
    UDP_PORT    = 9002

    tcp_server = TCPServer(SERVER, TCP_PORT)
    udp_server = UDPServer(SERVER, UDP_PORT)

    threading.Thread(target=tcp_server.accept_tcp_connections, daemon=True).start()
    udp_server.start_udp_server()
