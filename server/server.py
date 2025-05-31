import socket
import threading
import time
import secrets
import json
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES



class RSAKeyExchange:
    
    # RSA鍵ペアを生成（2048ビット）
    def __init__(self):
        self.private_key = RSA.generate(2048)

    # 公開鍵をバイト列として返す（送信用）
    def public_key_bytes(self):
        return self.private_key.publickey().export_key()

    def decrypt_symmetric_key(self, encrypted):
        # クライアントから受信したAES鍵＋IVを復号
        decrypted_bytes = PKCS1_OAEP.new(self.private_key).decrypt(encrypted)

        # 復号結果からAES鍵とIVを分離して返す
        aes_key = decrypted_bytes[:16]
        iv      = decrypted_bytes[16:]
        return aes_key, iv
    

class AESCipherCFB:

    # 対称鍵と初期化ベクトル（IV）を保存
    def __init__(self, key, iv):
        self.key = key
        self.iv = iv

    # AES CFBモードでデータを暗号化して返す
    def encrypt(self, data):
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).encrypt(data)

    # AES CFBモードでデータを復号して返す
    def decrypt(self, data):
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).decrypt(data)


class SecureSocket:

    # ソケット本体と暗号化用の対称暗号オブジェクトを保存
    def __init__(self, sock, cipher):
        self.sock = sock
        self.cipher = cipher

    # 指定されたバイト数を受信するまで繰り返す
    def recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    # 平文を暗号化し、長さ（4バイト）付きで送信
    def sendall(self, plaintext):
        ciphertext = self.cipher.encrypt(plaintext)
        self.sock.sendall(len(ciphertext).to_bytes(4, 'big') + ciphertext)

    def recv(self):
        # 最初の4バイトで受信データの長さを取得
        length = self.recv_exact(4)
        if not length:
            return b''

        # 指定バイト数のデータを受信し、復号して返す
        ciphertext = self.recv_exact(int.from_bytes(length, 'big'))
        return self.cipher.decrypt(ciphertext)


class TCPServer:
    
    HEADER_MAX_BYTE = 32
    TOKEN_MAX_BYTE = 255

    room_tokens        = {}  # {room : [token, ...]}
    room_passwords     = {}  # {room : password}
    client_data        = {}  # {token: [addr, room, user, is_host, pw, last]}
    encryption_objects = {}  # {token: AESCipherCFB}
    
    def __init__(self, server_address, server_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((server_address, server_port))
        self.sock.listen()

    def start_tcp_server(self):
        while True:
            connection, client_address = self.sock.accept()
            try:
                self.handle_client_request(connection, client_address)
            except Exception:
                connection.close()

    def handle_client_request(self, connection, client_address):
        # 鍵交換を実行
        secure_socket, symmetric_cipher = self.perform_key_exchange(connection)

        # クライアントから初回リクエストを受信
        request_data = secure_socket.recv()

        # ヘッダーとボディを解析
        _, operation, _, _, room_name, payload = self.decode_message(request_data)

        # トークンを生成し、クライアント情報を登録
        token = self.register_client(client_address, room_name, payload, operation)

        # 対称暗号オブジェクトをトークンに対応付けて保存
        TCPServer.encryption_objects[token] = symmetric_cipher

        # 操作コードに応じて処理を分岐（1: 作成 / 2: 参加）
        if operation == 1:
            # 新しいルームを作成
            self.create_room(secure_socket, room_name, token)
        elif operation == 2:
            # 既存のルームに参加
            self.join_room(secure_socket, token)

    # RSA-AES 鍵交換
    def perform_key_exchange(self, conn):
        # RSA 鍵ペアを生成
        key_manager = RSAKeyExchange()

        # 公開鍵をクライアントに送信
        public_key_bytes = key_manager.public_key_bytes()
        conn.sendall(len(public_key_bytes).to_bytes(4, 'big') + public_key_bytes)
        
        # クライアントから暗号化された AES鍵＋IV を受信
        encrypted_key_size = int.from_bytes(self.recvn(conn, 4), 'big')
        encrypted_key_iv   = self.recvn(conn, encrypted_key_size)
        # 秘密鍵で復号し、AES鍵と IV を取得
        aes_key, aes_iv    = key_manager.decrypt_symmetric_key(encrypted_key_iv)

        # 対称暗号用のオブジェクトを作成
        symmetric_cipher = AESCipherCFB(aes_key, aes_iv)
        secure_socket = SecureSocket(conn, symmetric_cipher)

        # 暗号化通信を行うためのソケットを作成して返す
        return secure_socket, symmetric_cipher

    # 指定されたバイト数を受信するまで繰り返す
    @staticmethod
    def recvn(conn, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
        return bytes(buf)

    def decode_message(self, data):
        # ヘッダー と ボディ を切り出す
        header = data[:self.HEADER_MAX_BYTE]
        body   = data[self.HEADER_MAX_BYTE:]

        # ヘッダから各フィールドを抽出
        room_name_size = int.from_bytes(header[:1], "big")
        operation      = int.from_bytes(header[1:2], "big")
        state          = int.from_bytes(header[2:3], "big")
        payload_size   = int.from_bytes(header[3:self.HEADER_MAX_BYTE], "big")

        # ボディから各フィールドを抽出
        room_name = body[:room_name_size].decode("utf-8")
        payload   = body[room_name_size:room_name_size + payload_size].decode("utf-8")
        
        return (
            room_name_size,  # ルーム名のサイズ
            operation,       # 操作コード
            state,           # 状態コード
            payload_size,    # ペイロードのサイズ
            room_name,       # ルーム名
            payload          # 本文
        )

    def register_client(self, addr, room_name, payload, operation):
        # ペイロードをパースしてユーザー情報を取得
        info     = json.loads(payload) if payload else {}

        # クライアント識別用のトークンを生成
        token    = secrets.token_bytes(self.TOKEN_MAX_BYTE)

        # ユーザー名・パスワードを抽出（無い場合は空文字）
        username = info.get("username", "")
        password = info.get("password", "")

        # 操作がルーム作成ならホストとみなす（1: 作成, 2: 参加）
        is_host  = int(operation == 1)

        # 初期状態では未参加ルーム、最後のアクティブ時間を記録
        joined_room = ""
        last_active = time.time()

        # クライアント情報をトークンに紐づけて保存
        TCPServer.client_data[token] = [
            addr,          # クライアントのアドレス
            joined_room,   # 所属ルーム
            username,      # ユーザー名
            is_host,       # ホストかどうか
            password,      # パスワード
            last_active    # 最終アクティブ時刻
        ]
        
        return token

    def create_room(self, conn, room_name, token):
        # トークンをクライアントに送信
        conn.sendall(token)
        # ルームにホストとしてトークンを登録
        self.room_tokens[room_name] = [token]
        # クライアントが送信したパスワードをルームに紐づけて保存
        TCPServer.room_passwords[room_name] = TCPServer.client_data[token][4]
        # クライアントの所属ルーム情報を更新
        TCPServer.client_data[token][1] = room_name

    def join_room(self, conn, token):
        # 現在のルーム一覧をクライアントに送信
        conn.sendall(str(list(self.room_tokens)).encode())
        
        # クライアントから参加希望ルームとパスワードを受信
        _, _, _, _, requested_room, payload = self.decode_message(conn.recv())
        password = json.loads(payload).get("password", "")

        # クライアント情報にパスワードを記録
        TCPServer.client_data[token][4] = password

         # 指定されたルームが存在しない場合はエラーを返す
        if requested_room not in self.room_tokens:
            conn.sendall(b"InvalidRoom")
            return

        # パスワードが設定されており、不一致ならエラーを返す
        stored_password = self.room_passwords.get(requested_room, "")
        if stored_password and stored_password != password:
            conn.sendall(b"InvalidPassword")
            return

        # ルームにクライアントを追加し、所属ルームを更新
        self.room_tokens[requested_room].append(token)
        TCPServer.client_data[token][1] = requested_room

        # トークンをクライアントに返す（参加完了通知）
        conn.sendall(token)


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
            # クライアントからのUDPメッセージを受信
            data, client_addr = self.sock.recvfrom(4096)

             # メッセージからルーム名・トークン・本文を抽出
            room, token, msg  = self.decode_message(data)

            # クライアントのIPアドレスと最終通信時刻を更新
            self.client_data[token][0] = client_addr
            self.client_data[token][5] = time.time()
            
            # ルーム内の全メンバーにメッセージをブロードキャスト
            self.broadcast(room, msg)

    def decode_message(self, data):
        # ヘッダとボディを切り出す
        header = data[:2]
        body   = data[2:]

        # ヘッダから各フィールドを抽出
        room_name_size = int.from_bytes(header[:1], "big")
        token_size     = int.from_bytes(header[1:2], "big")

        # ボディから各フィールドを抽出
        room_name         = body[:room_name_size].decode("utf-8")
        token             = body[room_name_size:room_name_size + token_size]
        encrypted_message = body[room_name_size + token_size:]

        # トークンに対応する暗号オブジェクトを使ってメッセージを復号
        cipher  = self.encryption_objects.get(token)
        message = cipher.decrypt(encrypted_message).decode("utf-8") if cipher else encrypted_message.decode("utf-8")
        
        return room_name, token, message

    def broadcast(self, room_name, message):
        # 指定されたルームの全参加者に対してループ
        for token in self.room_tokens.get(room_name, []):
            client_info = self.client_data.get(token)
            if not client_info or not client_info[0]:
                continue    # 無効なクライアントはスキップ

            # 対応する暗号オブジェクトでメッセージを暗号化
            cipher = self.encryption_objects.get(token)
            encrypted_message = cipher.encrypt(message.encode()) if cipher else message.encode()

            # パケットを構築（ルーム名長 + トークン長 + ルーム名 + トークン + メッセージ）
            packet = (
                len(room_name).to_bytes(1, 'big') +
                len(token).to_bytes(1, 'big')     +
                room_name.encode()                +
                token                             +
                encrypted_message
            )

            try:
                # クライアントにメッセージを送信
                self.sock.sendto(packet, client_info[0])
            except Exception:
                pass

    def remove_inactive_clients(self):
        while True:
            # タイムアウトの閾値（30秒間アクティビティがない場合）
            inactivity_threshold = time.time() - 30
             
            # 全クライアントを走査して、非アクティブなクライアントを検出
            for token, client_info in list(self.client_data.items()):
                last_active_time = client_info[5]
                if last_active_time < inactivity_threshold:
                    try:
                        # 非アクティブなクライアントを切断
                        self.disconnect(token, client_info)
                    except Exception:
                        pass

            # 60秒ごとにチェックを繰り返す
            time.sleep(60)

    def disconnect(self, token, info):
        addr, room, username, is_host = info[:4]
        members     = self.room_tokens.get(room, [])
        timeout_msg = b"Timeout!"

        # ① ルーム内への通知
        if is_host:
            # ホストがタイムアウトした場合は、ルームの終了を通知
            self.broadcast(room, f"System: ホストの{username}がタイムアウトしたためルームを終了します")
            self.broadcast(room, "exit!")
            
            # ルームのデータを削除
            self.room_tokens.pop(room, None)
            self.room_passwords.pop(room, None)

            # 全参加者を削除対象とする
            targets = members[:]   
        else:
            # 一般ユーザーがタイムアウトした場合の通知
            self.broadcast(room, f"System: {username}がタイムアウトにより退出しました。")

            # ルームから該当トークンを削除
            if token in members:
                members.remove(token)

            # 該当ユーザーのみを削除対象とする
            targets = [token]      

        # ② クライアントデータと暗号オブジェクトを削除
        for token in targets:
            self.client_data.pop(token, None)
            self.encryption_objects.pop(token, None)

        # ③ クライアントにタイムアウト通知を送信（失敗時の例外は呼び出し元で処理）
        self.sock.sendto(timeout_msg, addr)



if __name__ == "__main__":
    # サーバーの IPアドレス と ポート番号 を設定
    server_address  = '0.0.0.0'
    tcp_server_port = 9001
    udp_server_port = 9002

    # TCPサーバー と UDPサーバー を作成
    tcp_server = TCPServer(server_address, tcp_server_port)
    udp_server = UDPServer(server_address, udp_server_port)

    # 各サーバーを並行して実行するスレッドを作成
    tcp_thread = threading.Thread(target=tcp_server.start_tcp_server)
    udp_thread = threading.Thread(target=udp_server.start_udp_server)
    
    # スレッドを開始
    tcp_thread.start()
    udp_thread.start()
    
    # スレッドの終了を待機
    tcp_thread.join()
    udp_thread.join()
