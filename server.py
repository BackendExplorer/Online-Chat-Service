import base64
import socket
import threading
import time
import secrets
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

class TCPServer:
    HEADER_MAX_BYTE = 32     # ヘッダーサイズ（バイト）
    TOKEN_MAX_BYTE = 255     # クライアントトークンの最大バイト数

    room_members_map = {}  # {room_name : [token, token, token, ...]}
    clients_map = {}       # {token : [client_address, room_name, payload(username), host(0:guest, 1:host)]}

    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.server_address, self.server_port))
    
    def start_tcp_server(self):
        self.sock.listen()
        
        logging.info("    🔹 サーバーが接続を待機しています...")
        logging.info("=============================================\n")
        
        self.accept_tcp_connections()

    # クライアントからの TCP 接続を受け入れ、リクエストを処理する関数
    def accept_tcp_connections(self):
        while True:
            try:
                # 新しいクライアント接続を受け入れる
                connection, client_address = self.sock.accept()
                logging.info("🟢 新しいクライアント接続: %s", client_address)
                
                # クライアントのリクエストを処理
                self.handle_client_request(connection, client_address)
                
            except Exception as e:
                # 例外が発生した場合はエラーログを記録
                logging.info("Error: " + str(e))
            finally:
                # 接続をクローズ
                connection.close()

    # クライアントからのリクエストを処理する関数
    def handle_client_request(self, connection, client_address):
        # パケットの受信
        data = connection.recv(4096)  # 直接データを受信
        
        # ヘッダとボディを解析
        room_name_size, operation, state, payload_size, room_name, payload = self.decode_message(data)
        
        # トークンの作成
        token = secrets.token_bytes(self.TOKEN_MAX_BYTE)
        # クライアント情報を登録
        self.register_client(token, client_address, room_name, payload, operation)
        
        # operation (1 or 2) を処理
        if operation == 1:
            # 新しいルームを作成
            self.create_room(connection, room_name, payload, token)
        elif operation == 2:
            # 既存のルームに参加
            self.join_room(connection, room_name, payload, token)
        
        
    # TCP用メッセージを解析して必要な情報をまとめて返す関数
    def decode_message(self, data):
        # ヘッダー部分を切り出し
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

    # クライアント情報を登録する関数
    def register_client(self, token, client_address, room_name, payload, operation):
        # クライアント情報をマッピングし、操作コードに応じたフラグを設定
        self.clients_map[token] = [client_address, room_name, payload, 1 if operation == 1 else 0, None]

    # 新しいルームを作成し、ホストとしてクライアントを登録する関数
    def create_room(self, connection, room_name, payload, token):
        # クライアントにトークンを送信
        connection.send(token)
        
        # ルームを作成し、最初のメンバーとしてクライアントのトークンを登録
        self.room_members_map[room_name] = [token]
        logging.info(f"🔸 ルーム「{room_name}」を作成しました (Host: {payload})\n")

    # クライアントを既存のルームに参加させる関数
    def join_room(self, connection, room_name, payload, token):
        # 利用可能なルーム一覧を送信
        connection.send(str(list(self.room_members_map.keys())).encode("utf-8"))
        
        # クライアントからルーム名を受信
        room_name = connection.recv(4096).decode("utf-8")
        logging.info(f"🔹 クライアントが参加したいルーム名を受け取りました -> {room_name}")

        # ルームが存在するか確認し、適切に処理
        if room_name in self.room_members_map:
            # クライアントのトークンをルームに追加
            self.room_members_map[room_name].append(token)
            connection.send(token)
            logging.info(f"ルーム「{room_name}」に {payload} が参加しました\n")
        else:
            # ルームが存在しない場合、エラーメッセージを送信
            connection.send(b"ERROR: Room does not exist")
            logging.warning("クライアントが存在しないルーム (%s) に参加しようとしました", room_name)


class UDPServer:
    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.room_members_map = TCPServer.room_members_map
        self.clients_map = TCPServer.clients_map
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.server_address, self.server_port))
        logging.info("\n=============================================")
        logging.info("         📡  サーバが起動しました")
        
    # UDPサーバーを起動し、メッセージの処理とクライアントの監視を行う関数
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

    # UDPメッセージを処理する関数
    def handle_messages(self):
        while True:
            # クライアントからのメッセージを受信
            data, client_address = self.sock.recvfrom(4096)
            # デコード
            room_name, token, message = self.decode_message(data)
            
            # クライアントのアドレスを検証し、更新
            if self.clients_map[token][0] != client_address:
                self.clients_map[token][0] = client_address
                # logging.info("ルーム「%s」に %s が参加しました", self.clients_map[token][1], self.clients_map[token][2])  # ★ 修正
            else:
                # 最終アクティブ時間を更新し、メッセージをログに記録
                self.clients_map[token][-1] = time.time()
                logging.info("\n.............................................")
                logging.info("           💬   メッセージログ  ")
                logging.info(".............................................")
                # 以下、各メッセージ出力:
                logging.info(f"💬 ルーム: {room_name} | 👤 ユーザー: {self.clients_map[token][2]} | 📝 メッセージ: {message}")
                # メッセージをルーム内の他のクライアントにブロードキャスト
                self.broadcast_message(room_name, message)

    # UDPメッセージをデコードして、ルーム名, トークン, メッセージを返す関数
    def decode_message(self, data):
        # ヘッダを解析
        header = data[:2]
        room_name_size = int.from_bytes(header[:1], "big")
        token_size = int.from_bytes(header[1:2], "big")
        
        # ボディを解析
        body = data[2:]
        room_name = body[:room_name_size].decode("utf-8")
        token = body[room_name_size:room_name_size + token_size]
        message = body[room_name_size + token_size:].decode("utf-8")
        
        return room_name, token, message

    # 指定したルーム内のメンバーにメッセージをブロードキャストする関数
    def broadcast_message(self, room_name, message):
        # 指定したルームのメンバー一覧を取得
        members = self.room_members_map.get(room_name, [])
        
        # 各メンバーにメッセージを送信
        for member_token in members:
            member_address = self.clients_map[member_token][0]
            self.sock.sendto(message.encode(), member_address)

    # 非アクティブなクライアントを定期的に削除する関数
    def remove_inactive_clients(self):
        while True:
            try:
                current_time = time.time()
                # クライアント一覧を取得して非アクティブなものをチェック
                for client_token, client_info in list(self.clients_map.items()):
                    last_active_time = client_info[-1]
                    if last_active_time and (current_time - last_active_time > 100):
                        self.disconnect_inactive_client(client_token, client_info)
            except Exception as e:
                logging.info(f"Error monitoring clients: {e}")
            
            # 次のチェックまでスリープ
            time.sleep(60)

    # 指定したクライアントを切断し、関連データを削除する関数
    def disconnect_inactive_client(self, client_token, client_info):
        # クライアント情報を取得
        client_address, room_id, username, is_host = client_info[:4]

        try:
            if is_host == 1:
                # ルームがまだ存在する場合のみ処理
                if room_id in self.room_members_map:
                    self.broadcast_message(room_id, f"ホストの{username}がルームを退出しました．")
                    self.broadcast_message(room_id, "exit!")
                    del self.room_members_map[room_id]  # ルーム削除

                # ルームが削除された後は何もしない
                return

            else:
                # ルームがまだ存在し、トークンが登録されている場合のみ削除処理を実施
                if room_id in self.room_members_map and client_token in self.room_members_map[room_id]:
                    self.sock.sendto("Timeout!".encode(), client_address)
                    self.room_members_map[room_id].remove(client_token)

                # クライアントの削除
                if client_token in self.clients_map:
                    del self.clients_map[client_token]

        except KeyError:
            # ルームやクライアントが削除された場合、ログ出力を抑制する
            pass
        except Exception as e:
            # ルーム削除後はログを記録しない
            if room_id in self.room_members_map:
                client_token = base64.b64encode(client_token).decode('utf-8')  # Base64 に変換
                logging.info(f"Error handling timeout for {client_token}: {e}")



if __name__ == "__main__":
    # サーバーのアドレスとポート番号を設定
    server_address = '0.0.0.0'
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