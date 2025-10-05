import socket
import threading
import time
import secrets
import json
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES
from sqlite_logger import SQLiteLogger


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
        iv = decrypted_bytes[16:]
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
        # 指定バイト数のデータを受信し、復号して返す
        ciphertext = self.recv_exact(int.from_bytes(length, 'big'))
        return self.cipher.decrypt(ciphertext)


class TCPServer:
    
    room_tokens = {}        # {room: [token, ...]}
    room_passwords = {}     # {room: password}
    client_data = {}        # {token: [addr, room, user, is_host, pw, last]}
    encryption_objects = {} # {token: AESCipherCFB}
    lock = threading.Lock() # 共有リソースへのアクセスを制御するロック

    def __init__(self, server_address, server_port, logger):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((server_address, server_port))
        self.sock.listen()
        self.logger = logger

    def start_tcp_server(self):
        while True:
            connection, client_address = self.sock.accept()
            client_thread = threading.Thread(target=self.handle_client_request, args=(connection, client_address))
            client_thread.daemon = True
            client_thread.start()

    def handle_client_request(self, connection, client_address):
        try:
            # 鍵交換を実行
            secure_socket, symmetric_cipher = self.perform_key_exchange(connection)

            # クライアントから初回リクエスト(State: 0)を受信
            request_data = secure_socket.recv()

            # ヘッダーとボディを解析
            _, operation, state, _, room_name, payload = self.decode_message(request_data)

            # ルーム作成フロー
            if operation == 1: 
                self.handle_create_request(secure_socket, client_address, room_name, payload, symmetric_cipher)
                
            # ルーム参加フロー
            elif operation == 2: 
                self.handle_join_request(secure_socket, client_address, room_name, payload, symmetric_cipher)
            
             # ルーム一覧取得フロー
            elif operation == 3:
                self.handle_list_rooms(secure_socket)

        except json.JSONDecodeError as e:
            self.logger.log('ERROR', details=f"JSON Decode Error: {e}", client_ip=client_address)
        except Exception as e:
            self.logger.log('ERROR', details=f"TCP Handle Request Error: {e}", client_ip=client_address)
        finally:
            connection.close()

    def handle_create_request(self, secure_socket, client_address, room_name, payload, symmetric_cipher):
        # State: 1 (準拠) の応答を送信
        ack_payload = json.dumps({"status": "OK"}).encode('utf-8')
        ack_packet = self.make_packet(room_name, 1, 1, ack_payload)
        secure_socket.sendall(ack_packet)

        with self.lock:
            # トークンを生成し、クライアント情報を登録
            token = self.register_client(client_address, room_name, payload, 1) # operation=1 for create
            username = TCPServer.client_data[token][2]
            self.logger.log('USER_CONNECT', username=username, client_ip=client_address)
            TCPServer.encryption_objects[token] = symmetric_cipher
            
            # サーバー内部でルームを作成
            self.register_room(room_name, token)

        # State: 2 (完了) の応答としてトークンを送信
        complete_packet = self.make_packet(room_name, 1, 2, token)
        secure_socket.sendall(complete_packet)

    def handle_join_request(self, secure_socket, client_address, room_name, payload, symmetric_cipher):
        username = json.loads(payload).get("username", "")
        password = json.loads(payload).get("password", "")

        with self.lock:
            # ルーム存在チェック
            if room_name not in self.room_tokens:
                self.logger.log('JOIN_FAIL', username=username, details=f"Invalid room: {room_name}", client_ip=client_address)
                err_payload = b"InvalidRoom"
                err_packet = self.make_packet(room_name, 2, 255, err_payload) # State 255 for error
                secure_socket.sendall(err_packet)
                return

            # パスワードチェック
            stored_password = self.room_passwords.get(room_name, "")
            if stored_password and stored_password != password:
                self.logger.log('JOIN_FAIL', username=username, room_name=room_name, details="Invalid password", client_ip=client_address)
                err_payload = b"InvalidPassword"
                err_packet = self.make_packet(room_name, 2, 255, err_payload) # State 255 for error
                secure_socket.sendall(err_packet)
                return
            
            # State: 1 (準拠) の応答を送信
            ack_payload = json.dumps({"status": "OK"}).encode('utf-8')
            ack_packet = self.make_packet(room_name, 2, 1, ack_payload)
            secure_socket.sendall(ack_packet)

            # トークンを生成し、クライアント情報を登録
            token = self.register_client(client_address, room_name, payload, 2) # operation=2 for join
            self.logger.log('USER_CONNECT', username=username, client_ip=client_address)
            TCPServer.encryption_objects[token] = symmetric_cipher
            
            # サーバー内部でルームに参加
            self.register_user(room_name, token)

            # State: 2 (完了) の応答としてトークンを送信
            complete_packet = self.make_packet(room_name, 2, 2, token)
            secure_socket.sendall(complete_packet)

    def handle_list_rooms(self, secure_socket):
        # 現在のルーム一覧をクライアントに送信 (単純なリクエスト/レスポンス)
        self.logger.log('LIST_ROOMS', details=f"Room list requested by {secure_socket.sock.getpeername()}")
        with self.lock:
            room_list_payload = str(list(self.room_tokens)).encode()
        response_packet = self.make_packet("", 4, 1, room_list_payload)
        secure_socket.sendall(response_packet)

    # RSA-AES 鍵交換
    def perform_key_exchange(self, conn):
        # RSA 鍵ペアを生成
        key_manager = RSAKeyExchange()

        # 公開鍵をクライアントに送信
        public_key_bytes = key_manager.public_key_bytes()
        conn.sendall(len(public_key_bytes).to_bytes(4, 'big') + public_key_bytes)
        
        # クライアントから暗号化された AES鍵＋IV を受信
        encrypted_key_size = int.from_bytes(self.recvn(conn, 4), 'big')
        encrypted_key_iv = self.recvn(conn, encrypted_key_size)
        # 秘密鍵で復号し、AES鍵と IV を取得
        aes_key, aes_iv = key_manager.decrypt_symmetric_key(encrypted_key_iv)

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

    def make_packet(self, room_name, operation, state, payload_bytes):
        # ヘッダー作成
        room_name_bytes = room_name.encode('utf-8')
        header = (
            len(room_name_bytes).to_bytes(1, 'big') +
            operation.to_bytes(1, 'big') +
            state.to_bytes(1, 'big') +
            len(payload_bytes).to_bytes(29, 'big')
        )
        return header + room_name_bytes + payload_bytes

    def decode_message(self, data):
        # ヘッダー と ボディ を切り出す
        header = data[:32]
        body = data[32:]

        # ヘッダから各フィールドを抽出
        room_name_size = int.from_bytes(header[:1], "big")
        operation      = int.from_bytes(header[1:2], "big")
        state          = int.from_bytes(header[2:3], "big")
        payload_size   = int.from_bytes(header[3:32], "big")

        # ボディから各フィールドを抽出
        room_name = body[:room_name_size].decode("utf-8")
        payload = body[room_name_size:room_name_size + payload_size].decode("utf-8")
        
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
        info = json.loads(payload) if payload else {}

        # クライアント識別用のトークンを生成
        token = secrets.token_bytes(255)

        # ユーザー名・パスワードを抽出（無い場合は空文字）
        username = info.get("username", "")
        password = info.get("password", "")

        # 操作がルーム作成ならホストとみなす（1: 作成）
        is_host = int(operation == 1)

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

    def register_room(self, room_name, token):
        # ルームにホストとしてトークンを登録
        self.room_tokens[room_name] = [token]
        # クライアントが送信したパスワードをルームに紐づけて保存
        TCPServer.room_passwords[room_name] = TCPServer.client_data[token][4]
        # クライアントの所属ルーム情報を更新
        TCPServer.client_data[token][1] = room_name

        # ログ記録 (ROOM_CREATED)
        username = TCPServer.client_data[token][2]
        client_ip = TCPServer.client_data[token][0]
        self.logger.log('ROOM_CREATED', username=username, room_name=room_name, client_ip=client_ip)

    def register_user(self, room_name, token):
        # ルームにクライアントを追加し、所属ルームを更新
        self.room_tokens[room_name].append(token)
        TCPServer.client_data[token][1] = room_name

        # ログ記録 (USER_JOINED)
        username = TCPServer.client_data[token][2]
        client_ip = TCPServer.client_data[token][0]
        self.logger.log('USER_JOINED', username=username, room_name=room_name, client_ip=client_ip)


class UDPServer:
    
    def __init__(self, server_address, server_port, logger):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((server_address, server_port))
        self.room_tokens        = TCPServer.room_tokens
        self.room_passwords     = TCPServer.room_passwords
        self.client_data        = TCPServer.client_data
        self.encryption_objects = TCPServer.encryption_objects
        self.logger = logger
        self.lock = TCPServer.lock

    def start_udp_server(self):
        threading.Thread(target=self.handle_messages, daemon=True).start()
        threading.Thread(target=self.remove_inactive_clients, daemon=True).start()

    def handle_messages(self):
        while True:
            try:
                # クライアントからのUDPメッセージを受信
                data, client_addr = self.sock.recvfrom(4096)

                # メッセージからルーム名・トークン・本文を抽出
                room, token, msg  = self.decode_message(data)

                with self.lock:
                    if token in self.client_data:
                        # クライアントのIPアドレスと最終通信時刻を更新
                        self.client_data[token][0] = client_addr
                        self.client_data[token][5] = time.time()
                        
                        # ログ記録 (MESSAGE_SENT)
                        username = self.client_data[token][2]
                        self.logger.log('MESSAGE_SENT', username=username, room_name=room, details=msg, client_ip=client_addr)

                        # ルーム内の全メンバーにメッセージをブロードキャスト
                        self.broadcast(room, msg)
                    else:
                        self.logger.log('INVALID_TOKEN', details=f"Received UDP from unknown token", client_ip=client_addr)

            except Exception as e:
                self.logger.log('ERROR', details=f"UDP Handle Messages Error: {e}")
                
    def decode_message(self, data):
        # ヘッダとボディを切り出す
        header = data[:2]
        body = data[2:]

        # ヘッダから各フィールドを抽出
        room_name_size = int.from_bytes(header[:1], "big")
        token_size = int.from_bytes(header[1:2], "big")

        # ボディから各フィールドを抽出
        room_name         = body[:room_name_size].decode("utf-8")
        token             = body[room_name_size:room_name_size + token_size]
        encrypted_message = body[room_name_size + token_size:]

        # トークンに対応する暗号オブジェクトを使ってメッセージを復号
        with self.lock:
            cipher  = self.encryption_objects.get(token)
        message = cipher.decrypt(encrypted_message).decode("utf-8") if cipher else encrypted_message.decode("utf-8")
        
        return room_name, token, message

    def broadcast(self, room_name, message):
        # 指定されたルームの全参加者に対してループ
        if room_name not in self.room_tokens:
            return

        for token in self.room_tokens.get(room_name, []):
            client_info = self.client_data.get(token)
            if not client_info or not client_info[0]:
                continue # 無効なクライアントはスキップ

            # 対応する暗号オブジェクトでメッセージを暗号化
            cipher = self.encryption_objects.get(token)
            if not cipher:
                continue

            encrypted_message = cipher.encrypt(message.encode())
            
            try:
                # 暗号化したメッセージ本体だけをクライアントに送信
                self.sock.sendto(encrypted_message, client_info[0])
            except Exception as e:
                self.logger.log('ERROR', details=f"UDP Broadcast Error to {client_info[0]}: {e}")
                pass

    def remove_inactive_clients(self):
        while True:
            # 60秒ごとにチェックを繰り返す
            time.sleep(60)

            inactivity_threshold = time.time() - 60
            
            inactive_clients = []
            with self.lock:
                # 全クライアントを走査して、非アクティブなクライアントを検出
                for token, client_info in self.client_data.items():
                    last_active_time = client_info[5]
                    if last_active_time < inactivity_threshold:
                        inactive_clients.append((token, client_info))
            
            # ロックの外でdisconnectを呼び出すことで、ロックの保持時間を短くする
            for token, client_info in inactive_clients:
                try:
                    # 非アクティブなクライアントを切断
                    with self.lock:
                        self.disconnect(token, client_info)
                except Exception as e:
                    self.logger.log('ERROR', details=f"Disconnect Error for {client_info[2]}: {e}")
                    pass

    def disconnect(self, token, info):
        addr, room, username, is_host = info[:4]
        members = self.room_tokens.get(room, [])
        timeout_msg = b"Timeout!"

        # ログ記録 (USER_TIMEOUT)
        self.logger.log('USER_TIMEOUT', username=username, room_name=room, client_ip=addr)

        # ① ルーム内への通知
        if room and room in self.room_tokens:
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
        else:
             targets = [token]

        # ② クライアントデータと暗号オブジェクトを削除
        for t in targets:
            self.client_data.pop(t, None)
            self.encryption_objects.pop(t, None)

        # ③ クライアントにタイムアウト通知を送信（失敗時の例外は呼び出し元で処理）
        try:
            self.sock.sendto(timeout_msg, addr)
        except Exception as e:
             self.logger.log('ERROR', details=f"Timeout notification send failed to {addr}: {e}")



if __name__ == "__main__":
    
    # サーバーの IPアドレス と ポート番号 を設定
    server_address = '0.0.0.0'
    tcp_server_port = 9001
    udp_server_port = 9002

    # loggerインスタンスを生成
    logger = SQLiteLogger('/app/logs/logs.db')
    logger.log('SERVER_START', details='Server process started.')

    # TCPサーバー と UDPサーバー を作成
    tcp_server = TCPServer(server_address, tcp_server_port, logger)
    udp_server = UDPServer(server_address, udp_server_port, logger)

    # 各サーバーを並行して実行するスレッドを作成
    tcp_thread = threading.Thread(target=tcp_server.start_tcp_server)
    udp_thread = threading.Thread(target=udp_server.start_udp_server)
    
    # スレッドを開始
    tcp_thread.start()
    udp_thread.start()
    
    # スレッドの終了を待機
    tcp_thread.join()
    udp_thread.join()