import socket
import json
from crypto import RSAKeyExchange, AESCipherCFB, SecureSocket
from Crypto.PublicKey import RSA    # ← この行を追加




class TCPClient:
    HEADER_ROOM_LEN    = 1
    HEADER_OP_LEN      = 1
    HEADER_STATE_LEN   = 1
    HEADER_PAYLOAD_LEN = 29   

    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port    = server_port
        self.cipher = None   
        self.sock   = None

    def connect_and_handshake(self):
        # TCP ソケットを作成し、サーバに接続
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((self.server_address, self.server_port))

        # サーバの公開鍵を受信してインポート
        pubkey_length = int.from_bytes(tcp_socket.recv(4), 'big')
        server_public_key = RSA.import_key(tcp_socket.recv(pubkey_length))

        # AES 鍵と IV を生成し、公開鍵で暗号化して送信
        key_exchanger = RSAKeyExchange()
        encrypted_secret = key_exchanger.encrypted_shared_secret(server_public_key)
        tcp_socket.sendall(len(encrypted_secret).to_bytes(4, 'big') + encrypted_secret)

        # 暗号化通信のための SecureSocket を確立
        self.cipher = AESCipherCFB(key_exchanger.aes_key, key_exchanger.iv)
        self.sock   = SecureSocket(tcp_socket, self.cipher)

    def make_header(self, room_bytes, op, state, payload_bytes):
        room_size    = len(room_bytes).to_bytes(self.HEADER_ROOM_LEN, 'big')
        op_code      = op.to_bytes(self.HEADER_OP_LEN, 'big')
        state_code   = state.to_bytes(self.HEADER_STATE_LEN, 'big')
        payload_size = len(payload_bytes).to_bytes(self.HEADER_PAYLOAD_LEN, 'big')
    
        return room_size + op_code + state_code + payload_size


    def make_packet(self, room, op, payload):
        payload_bytes = json.dumps(payload).encode("utf-8")
        room_bytes = room.encode("utf-8")
        header = self.make_header(room_bytes, op, 0, payload_bytes)
        return header + room_bytes + payload_bytes

    # クライアントが新しいルームを作成する関数
    def create_room(self, username, room, password):
        # サーバーに接続して鍵交換を行う
        self.connect_and_handshake()

        # 状態コード（今回は 0 で固定）
        state = 0
        op_code = 1  # 操作コード：1 = ルーム作成

        # ルーム作成用のパケットを作成
        payload = {"username": username, "password": password}
        packet = self.make_packet(room, op_code, payload)

        # パケットを送信
        self.sock.sendall(packet)

        # サーバーからトークンを受信
        token = self.sock.recv()

        # 接続を閉じる
        self.sock.close()

        # トークンとルーム情報を返す
        return {token: [room, username]}

    # サーバーからルーム一覧を取得する関数
    def get_room_list(self, username):
        # サーバーと接続して鍵交換を行う
        self.connect_and_handshake()

        # 操作コード：2 = ルーム一覧取得
        op_code = 2
        state = 0
        payload = {"username": username, "password": ""}
        packet = self.make_packet("", op_code, payload)

        # パケットを送信
        self.sock.sendall(packet)

        # サーバーからの応答を受信・復号
        response = self.sock.recv().decode()

        # 接続を閉じる
        self.sock.close()

        # 応答文字列をリスト形式に整形して返す
        try:
            raw_list = response.strip()[1:-1]  # 例: "['room1', 'room2']"
            room_list = [
                room.strip().strip("'\"") 
                for room in raw_list.split(',') 
                if room.strip()
            ]
            return room_list
        except Exception:
            # パース失敗時はそのまま文字列をリストで返す
            return [response]

    # クライアントが既存のルームに参加する関数
    def join_room(self, username, room, password):
        # サーバーに接続して鍵交換を行う
        self.connect_and_handshake()

        # 操作コード：2 = ルーム操作（一覧取得・参加リクエスト）
        op_code = 2
        state = 0

        # --- ルーム一覧取得フェーズ ---
        payload_list = {"username": username, "password": ""}
        list_packet = self.make_packet("", op_code, payload_list)
        self.sock.sendall(list_packet)
        _ = self.sock.recv()  # ルーム一覧はここでは使わない

        # --- ルーム参加リクエスト送信 ---
        payload_join = {"username": username, "password": password}
        join_packet = self.make_packet(room, op_code, payload_join)
        self.sock.sendall(join_packet)

        # サーバーからの応答を受信
        resp = self.sock.recv()

        # 接続を閉じる
        self.sock.close()

        # エラー判定
        if resp.startswith(b"InvalidPassword"):
            raise ValueError("パスワードが違います。")
        if resp.startswith(b"InvalidRoom"):
            raise ValueError("ルームが存在しません。")

        # 正常応答：トークンを辞書で返す
        return {resp: [room, username]}


class UDPClient:
    def __init__(self, server_addr, server_port, info, cipher):
        self.server_addr = server_addr
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.cipher = cipher

        # トークン、ルーム名、ユーザー名の抽出
        self.token, (self.room, self.username) = next(iter(info.items()))

        # 参加メッセージを送信
        self.send_system_message(f"{self.username} が参加しました。")

    def make_packet(self, body=b""):
        # メッセージ本体を暗号化
        encrypted_body = self.cipher.encrypt(body)
    
        room_name_size  = len(self.room).to_bytes(1, 'big')   # ルーム名のサイズ
        token_size      = len(self.token).to_bytes(1, 'big')  # トークンのサイズ
        room_name_bytes = self.room.encode()                  # ルーム名
        token_bytes     = self.token                          # トークン
    
        # パケットを構築して返す
        return room_name_size + token_size + room_name_bytes + token_bytes + encrypted_body

    # システムメッセージを送信
    def send_system_message(self, text):
        message = f"System: {text}".encode()
        self.sock.sendto(self.make_packet(message), (self.server_addr, self.server_port))

    # チャットメッセージを送信
    def send_chat_message(self, text):
        message = f"{self.username}: {text}".encode()
        self.sock.sendto(self.make_packet(message), (self.server_addr, self.server_port))

    # 新しいメッセージを受信して返す
    def fetch_messages(self, already):
        self.sock.settimeout(0.05)
        new_messages = []

        try:
            while True:
                packet, _ = self.sock.recvfrom(4096)

                # ヘッダーからルーム名とトークンの長さを抽出
                room_len = packet[0]
                token_len = packet[1]

                # 暗号化メッセージ部分を切り出し、復号
                encrypted_msg = packet[2 + room_len + token_len:]
                message = self.cipher.decrypt(encrypted_msg).decode()

                # 終了通知メッセージはスキップ
                if message in {"exit!", "Timeout!"}:
                    continue

                 # 既読・重複を除き、新規メッセージとして追加
                if message not in already and message not in new_messages:
                    new_messages.append(message)

        except socket.timeout:
            pass

        return new_messages
