import socket
import threading
import time
import secrets
import json
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES


class KeyExchangeManager:
    def __init__(self):
        self.private_key = RSA.generate(2048)

    def public_key_bytes(self):
        return self.private_key.publickey().export_key()

    def decrypt_symmetric_key(self, encrypted):
        sym = PKCS1_OAEP.new(self.private_key).decrypt(encrypted)
        return sym[:16], sym[16:]


class SymmetricCipher:
    def __init__(self, key, iv):
        self.key = key
        self.iv = iv

    def encrypt(self, data):
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).encrypt(data)

    def decrypt(self, data):
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).decrypt(data)


class EncryptedSocket:
    def __init__(self, sock, cipher):
        self.sock = sock
        self.cipher = cipher

    def recv_exact(self, n):
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
        length = self.recv_exact(4)
        if not length:
            return b''
        ciphertext = self.recv_exact(int.from_bytes(length, 'big'))
        return self.cipher.decrypt(ciphertext)

    def close(self):
        self.sock.close()


# ──── TCP サーバ ───────────────────────────────────────
class TCPServer:
    HEADER_MAX_BYTE = 32
    TOKEN_MAX_BYTE = 255

    room_tokens = {}        # {room : [token, ...]}
    room_passwords = {}     # {room : password}
    client_data = {}        # {token: [addr, room, user, is_host, pw, last]}
    encryption_objects = {} # {token: SymmetricCipher}

    def __init__(self, server_address: str, server_port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((server_address, server_port))
        self.sock.listen()

    
    def start_tcp_server(self):
        while True:
            conn, addr = self.sock.accept()
            try:
                self.handle_client(conn, addr)
            except Exception:
                conn.close()

    # クライアント初回リクエスト処理
    def handle_client(self, connection, client_address):
        secure_socket, symmetric_cipher = self.perform_key_exchange(connection)

        request_data = secure_socket.recv()
        _, operation, _, _, room_name, payload = self.decode_message(request_data)

        token = self.register_client(client_address, room_name, payload, operation)
        TCPServer.encryption_objects[token] = symmetric_cipher

        if operation == 1:
            self.create_room(secure_socket, room_name, token)
        elif operation == 2:
            self.join_room(secure_socket, token)

    # RSA-AES 鍵交換
    def perform_key_exchange(self, conn):
        key_manager = KeyExchangeManager()

        public_key_bytes = key_manager.public_key_bytes()
        conn.sendall(len(public_key_bytes).to_bytes(4, 'big') + public_key_bytes)

        encrypted_key_length = int.from_bytes(self.recvn(conn, 4), 'big')
        encrypted_key_iv = self.recvn(conn, encrypted_key_length)
        aes_key, aes_iv = key_manager.decrypt_symmetric_key(encrypted_key_iv)

        symmetric_cipher = SymmetricCipher(aes_key, aes_iv)
        secure_socket = EncryptedSocket(conn, symmetric_cipher)
        return secure_socket, symmetric_cipher

    @staticmethod
    def recvn(conn, n):
        data = b''
        while len(data) < n:
            chunk = conn.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return data

    def decode_message(self, data):
        header = data[:self.HEADER_MAX_BYTE]
        body   = data[self.HEADER_MAX_BYTE:]

        room_len     = int.from_bytes(header[:1], "big")
        operation    = int.from_bytes(header[1:2], "big")
        state        = int.from_bytes(header[2:3], "big")
        payload_size = int.from_bytes(header[3:self.HEADER_MAX_BYTE], "big")

        room_name = body[:room_len].decode("utf-8")
        payload   = body[room_len:room_len + payload_size].decode("utf-8")
        return room_len, operation, state, payload_size, room_name, payload

    def register_client(self, addr, room_name, payload, operation):
        info = json.loads(payload) if payload else {}
        token = secrets.token_bytes(self.TOKEN_MAX_BYTE)

        username    = info.get("username", "")
        password    = info.get("password", "")
        is_host     = int(operation == 1)
        joined_room = ""
        last_active = time.time()

        TCPServer.client_data[token] = [
            addr, joined_room, username, is_host, password, last_active
        ]
        return token

    def create_room(self, conn, room_name, token):
        conn.sendall(token)
        self.room_tokens[room_name] = [token]
        TCPServer.room_passwords[room_name] = TCPServer.client_data[token][4]
        TCPServer.client_data[token][1] = room_name

    def join_room(self, conn, token):
        conn.sendall(str(list(self.room_tokens)).encode())

        _, _, _, _, requested_room, payload = self.decode_message(conn.recv())
        password = json.loads(payload).get("password", "")
        TCPServer.client_data[token][4] = password

        if requested_room not in self.room_tokens:
            conn.sendall(b"InvalidRoom")
            return

        stored_password = self.room_passwords.get(requested_room, "")
        if stored_password and stored_password != password:
            conn.sendall(b"InvalidPassword")
            return

        self.room_tokens[requested_room].append(token)
        TCPServer.client_data[token][1] = requested_room
        conn.sendall(token)


# ──── UDP サーバ ───────────────────────────────────────
class UDPServer:
    def __init__(self, server_address, server_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((server_address, server_port))
        self.room_tokens        = TCPServer.room_tokens
        self.room_passwords     = TCPServer.room_passwords
        self.client_data        = TCPServer.client_data
        self.encryption_objects = TCPServer.encryption_objects

    def start_udp_server(self):
        threading.Thread(target=self.handle_messages, daemon=True).start()
        threading.Thread(target=self.remove_inactive_clients, daemon=True).start()

    def handle_messages(self):
        while True:
            data, client_addr = self.sock.recvfrom(4096)
            room, token, msg  = self.decode_message(data)

            self.client_data[token][0] = client_addr
            self.client_data[token][5] = time.time()
            self.broadcast(room, msg)

    def decode_message(self, data: bytes):
        header   = data[:2]
        body     = data[2:]

        room_len = int.from_bytes(header[:1], "big")
        tok_len  = int.from_bytes(header[1:2], "big")

        room_name = body[:room_len].decode("utf-8")
        token     = body[room_len:room_len + tok_len]
        enc_msg   = body[room_len + tok_len:]

        cipher = self.encryption_objects.get(token)
        msg    = cipher.decrypt(enc_msg).decode("utf-8") if cipher else enc_msg.decode("utf-8")
        return room_name, token, msg

    def broadcast(self, room, message):
        for token in self.room_tokens.get(room, []):
            info = self.client_data.get(token)
            if not info or not info[0]:
                continue

            cipher  = self.encryption_objects.get(token)
            enc_msg = cipher.encrypt(message.encode()) if cipher else message.encode()

            packet = (len(room).to_bytes(1, 'big') + len(token).to_bytes(1, 'big') +
                      room.encode() + token + enc_msg)
            try:
                self.sock.sendto(packet, info[0])
            except Exception:
                pass

    def remove_inactive_clients(self):
        while True:
            cutoff = time.time() - 30
            for token, info in list(self.client_data.items()):
                if info[5] < cutoff:
                    try:
                        self.disconnect(token, info)
                    except Exception:
                        pass
            time.sleep(60)

    def disconnect(self, token, info):
        addr, room, username, is_host = info[:4]
        members = self.room_tokens.get(room, [])
        timeout_msg = b"Timeout!"

        # １）ルーム内への通知
        if is_host:
            self.broadcast(room, f"System: ホストの{username}がタイムアウトしたためルームを終了します")
            self.broadcast(room, "exit!")
            # ルーム情報を消去
            self.room_tokens.pop(room, None)
            self.room_passwords.pop(room, None)
            targets = members[:]   # 参加者全員を削除対象に
        else:
            self.broadcast(room, f"System: {username}がタイムアウトにより退出しました。")
            if token in members:
                members.remove(token)
            targets = [token]      # 自身のみを削除対象に

        # ２）データ構造からのクリーンアップ
        for t in targets:
            self.client_data.pop(t, None)
            self.encryption_objects.pop(t, None)

        # ３）クライアントへのタイムアウト通知（例外は呼び出し元へ伝播）
        self.sock.sendto(timeout_msg, addr)


# ──── メインエントリ ────────────────────────────────
if __name__ == "__main__":
    # サーバーのアドレスとポート番号を設定
    server_address  = '0.0.0.0'
    tcp_server_port = 9001
    udp_server_port = 9002

    # TCP サーバーと UDP サーバーを作成
    tcp_server = TCPServer(server_address, tcp_server_port)
    udp_server = UDPServer(server_address, udp_server_port)

    # 各サーバーを並行して実行するスレッドを作成
    thread_tcp = threading.Thread(target=tcp_server.start_tcp_server)
    thread_udp = threading.Thread(target=udp_server.start_udp_server)

    # スレッドを開始
    thread_tcp.start()
    thread_udp.start()

    # スレッドの終了を待機
    thread_tcp.join()
    thread_udp.join()
