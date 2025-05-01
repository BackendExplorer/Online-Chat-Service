import base64
import socket
import threading
import time
import secrets
import sys


class TCPServer:

    HEADER_MAX_BYTE = 32    # ヘッダーサイズ（バイト）
    TOKEN_MAX_BYTE = 255    # クライアントトークンの最大バイト数

    room_members_map = {}  # {room_name : [token, token, token, ...]}
    clients_map = {}       # {token : [client_address, room_name, payload(username), host(0:guest, 1:host)]}

    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.server_address, self.server_port))
        self.sock.listen()

    # クライアントからの TCP 接続を受け入れ、リクエストを処理するメソッド
    def accept_tcp_connections(self):
        while True:
            try:
                # 新しいクライアント接続を受け入れる
                connection, client_address = self.sock.accept()
                # クライアントのリクエストを処理
                self.handle_client_request(connection, client_address)
                
            except Exception as e:
                pass
            finally:
                connection.close()

    # クライアントからのリクエストを処理するメソッド
    def handle_client_request(self, connection, client_address):
        # パケットの受信
        data = connection.recv(4096)
        # ヘッダとボディを解析
        room_name_size, operation, state, payload_size, room_name, payload = self.decode_message(data)
        # トークンの作成
        token = secrets.token_bytes(self.TOKEN_MAX_BYTE)
        # クライアント情報を登録
        self.register_client(token, client_address, room_name, payload, operation)

        if operation == 1:
            # 新しいルームを作成
            self.create_room(connection, room_name, payload, token)
        elif operation == 2:
            # 既存のルームに参加
            self.join_room(connection, room_name, payload, token)

    # TCP用メッセージを解析して必要な情報をまとめて返すメソッド
    def decode_message(self, data):
        header = data[:self.HEADER_MAX_BYTE]

        # ヘッダから各フィールドを抽出
        room_name_size = int.from_bytes(header[:1], "big")
        operation = int.from_bytes(header[1:2], "big")
        state = int.from_bytes(header[2:3], "big")
        payload_size = int.from_bytes(header[3:self.HEADER_MAX_BYTE], "big")

        # ボディを解析
        body = data[self.HEADER_MAX_BYTE:]
        room_name = body[:room_name_size].decode("utf-8")
        payload = body[room_name_size:room_name_size + payload_size].decode("utf-8")

        return room_name_size, operation, state, payload_size, room_name, payload

    # クライアント情報を登録するメソッド
    def register_client(self, token, client_address, room_name, payload, operation):
        # クライアント登録時に最終アクティブ時刻を現在時刻で初期化
        # [client_address, room_name, payload, is_host, last_active_time]
        self.clients_map[token] = [
            client_address,
            room_name,
            payload,
            1 if operation == 1 else 0,
            time.time(),
        ]

    # 新しいルームを作成し、ホストとしてクライアントを登録するメソッド
    def create_room(self, connection, room_name, payload, token):
        connection.send(token)
        self.room_members_map[room_name] = [token]

    # クライアントを既存のルームに参加させる関数
    def join_room(self, connection, room_name, payload, token):
        # 利用可能なルーム一覧を送信
        connection.send(str(list(self.room_members_map.keys())).encode("utf-8"))
        # クライアントからルーム名を受信
        room_name = connection.recv(4096).decode("utf-8")

        # ルームが存在するか確認し、適切に処理
        if room_name in self.room_members_map:
            # クライアントのトークンをルームに追加
            self.room_members_map[room_name].append(token)
            # clients_map に正しいルーム名を書き戻す
            self.clients_map[token][1] = room_name
            # トークンを返す
            connection.send(token)
        else:
            connection.send(b"ERROR: Room does not exist")


class UDPServer:

    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.room_members_map = TCPServer.room_members_map
        self.clients_map = TCPServer.clients_map
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.server_address, self.server_port))

    # UDPサーバーを起動し、メッセージの処理とクライアントの監視を行うメソッド
    def start_udp_server(self):
        # メッセージ処理スレッドと非アクティブクライアント監視スレッドを作成
        thread_main = threading.Thread(target=self.handle_messages)
        thread_tracking = threading.Thread(target=self.remove_inactive_clients)

        # スレッドを開始
        thread_main.start()
        thread_tracking.start()

        # スレッドの終了を待機
        thread_main.join()
        thread_tracking.join()

    # UDPメッセージを受信して処理するメソッド
    def handle_messages(self):
        while True:
            data, client_address = self.sock.recvfrom(4096)
            room_name, token, message = self.decode_message(data)
            self.update_client_activity(token, client_address)
            self.broadcast_message(room_name, message)

    # UDPメッセージをデコードして、ルーム名、トークン、メッセージを返すメソッド
    def decode_message(self, data):
        header = data[:2]
        room_name_size = int.from_bytes(header[:1], "big")
        token_size = int.from_bytes(header[1:2], "big")
        body = data[2:]
        room_name = body[:room_name_size].decode("utf-8")
        token = body[room_name_size:room_name_size + token_size]
        message = body[room_name_size + token_size:].decode("utf-8")
        return room_name, token, message

    # クライアントの最終アクティブ時刻とアドレスを更新するメソッド
    def update_client_activity(self, token, address):
        # メッセージ受信時に最終アクティブ時刻とアドレスを更新
        self.clients_map[token][0] = address
        self.clients_map[token][-1] = time.time()

    # 指定されたルームのメンバーにメッセージをブロードキャストするメソッド
    def broadcast_message(self, room_name, message):
        self.broadcast_list(self.room_members_map.get(room_name, []), message)

    # トークンのリストを使ってメッセージを送信する内部メソッド
    def broadcast_list(self, members, message):
        for member_token in members:
            if member_token not in self.clients_map:
                continue
            addr = self.clients_map[member_token][0]
            if addr:
                try:
                    self.sock.sendto(message.encode(), addr)
                except Exception:
                    pass

    # 非アクティブなクライアントを定期的に監視し、切断するメソッド
    def remove_inactive_clients(self):
        while True:
            current_time = time.time()
            for client_token, client_info in list(self.clients_map.items()):
                is_host = client_info[3]
                last_active_time = client_info[-1]
                
                if self.is_client_inactive(last_active_time, current_time):
                    try:
                        self.disconnect_inactive_client(client_token, client_info)
                    except Exception:
                        pass
            time.sleep(60)

    # クライアントが非アクティブかどうかを判定するメソッド
    def is_client_inactive(self, last_active_time, current_time):
        return (last_active_time is not None and
                (current_time - last_active_time) > 100)

    # 非アクティブなクライアントを切断するメソッド
    def disconnect_inactive_client(self, client_token, client_info):
        client_address, room_id, username, is_host = client_info[:4]
        members = self.room_members_map.get(room_id)
        if not members:
            return

        members_snapshot = list(members)
        try:
            if is_host == 1:
                self.handle_host_disconnect(room_id, username, members_snapshot)
            else:
                self.handle_guest_disconnect(client_token, client_address, room_id, username, members_snapshot)
        except Exception:
            pass

    # ホストが切断された場合、ルームを終了し、全メンバーに通知を送信するメソッド
    def handle_host_disconnect(self, room_id, username, members_snapshot):
        self.broadcast_list(members_snapshot, f"System: ホストの{username}がルームを退出したので、ルームは終了します")
        self.broadcast_list(members_snapshot, "exit!")
        del self.room_members_map[room_id]

    # ゲストが非アクティブとなり切断された場合、ルームから除外し通知を送信するメソッド
    def handle_guest_disconnect(self, client_token, client_address, room_id, username, members_snapshot):
        self.broadcast_list(members_snapshot, f"System: {username}がタイムアウトにより退出しました。")
        self.sock.sendto("Timeout!".encode(), client_address)
        self.room_members_map[room_id].remove(client_token)
        if not self.room_members_map[room_id]:
            del self.room_members_map[room_id]
        del self.clients_map[client_token]


if __name__ == "__main__":

    # サーバーのアドレスとポート番号を設定
    server_address = '0.0.0.0'
    tcp_server_port = 9001
    udp_server_port = 9002

    # TCP サーバーと UDP サーバーを作成
    tcp_server = TCPServer(server_address, tcp_server_port)
    udp_server = UDPServer(server_address, udp_server_port)

    # 各サーバーを並行して実行するスレッドを作成
    thread_tcp = threading.Thread(target=tcp_server.accept_tcp_connections)
    thread_udp = threading.Thread(target=udp_server.start_udp_server)

    # スレッドを開始
    thread_tcp.start()
    thread_udp.start()

    # スレッドの終了を待機
    thread_tcp.join()
    thread_udp.join()
