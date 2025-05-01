import socket
import threading
import time
import sys

TOKEN_MAX_BYTE = 255
ROOM_NAME_MAX_BYTE = 2 ** 8
PAYLOAD_MAX_BYTE = 2 ** 29
HEADER_SIZE = 32
USER_NAME_MAX_BYTE_SIZE = 255


class TCPClient:
    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_info = {}

    # サーバーに接続し、ルーム一覧を取得するメソッド
    def list_rooms(self, username):
        self.connect_to_server()
        packet = self.create_packet("", 2, 0, username)
        self.sock.send(packet)
        room_list = self.sock.recv(4096).decode("utf-8")
        try:
            rooms = room_list.strip()[1:-1].split(',')
            rooms = [r.strip().strip("'").strip('"') for r in rooms if r.strip()]
        except Exception:
            rooms = [room_list]
        return rooms

    # サーバーに接続し、ルームを新規作成してトークンを取得するメソッド
    def quick_create_room(self, username, room_name):
        self.connect_to_server()
        packet = self.create_packet(room_name, 1, 0, username)
        self.sock.send(packet)
        token = self.sock.recv(TOKEN_MAX_BYTE)
        self.client_info = {token: [room_name, username]}
        return self.client_info

    # 既存ルームに参加後、トークンを取得して情報を登録するメソッド
    def register_room(self, username, room_name):
        self.sock.send(room_name.encode("utf-8"))
        token = self.sock.recv(TOKEN_MAX_BYTE)
        self.client_info = {token: [room_name, username]}
        return self.client_info

    # サーバーへTCP接続を確立するメソッド
    def connect_to_server(self):
        try:
            self.sock.connect((self.server_address, self.server_port))
        except socket.error as e:
            raise

    # ユーザー入力に基づき、ルーム作成または参加の処理を行うメソッド
    def start_tcp_client(self):
        self.connect_to_server()
        username = self.input_user_name()
        op = self.input_operation()
        if op == 1:
            room, token = self.create_room(username)
        else:
            room, token = self.join_room(username)
        self.client_info = {token: [room, username]}
        self.sock.close()
        return self.client_info

    # ユーザー名を入力させ、バリデーションを行うメソッド
    def input_user_name(self):
        while True:
            u = input("\U0001F464 ユーザー名: ")
            if not u:
                print("ユーザー名を入力してください")
            elif len(u) > PAYLOAD_MAX_BYTE:
                print("長すぎます。再度入力してください。")
            else:
                return u

    # 操作選択（ルーム作成 or 参加）の入力を受け付けるメソッド
    def input_operation(self):
        while True:
            try:
                o = int(input("1: ルーム作成  2: ルーム参加 -> "))
                if o in (1, 2):
                    return o
            except ValueError:
                pass
            print("1または2 を入力してください。")

    # ユーザーからルーム名を入力させ、作成処理を行うメソッド
    def create_room(self, username):
        rn = self.input_room_name(1)
        pkt = self.create_packet(rn, 1, 0, username)
        self.sock.send(pkt)
        token = self.sock.recv(TOKEN_MAX_BYTE)
        return rn, token

    # ユーザーからルーム参加を選択し、リストを受け取って参加処理を行うメソッド
    def join_room(self, username):
        pkt = self.create_packet("", 2, 0, username)
        self.sock.send(pkt)
        rl = self.sock.recv(4096).decode("utf-8")
        try:
            rooms = rl.strip()[1:-1].split(',')
            rooms = [r.strip().strip("'").strip('"') for r in rooms if r.strip()]
        except:
            rooms = [rl]
        print("\U0001F4DC 利用可能なルーム:")
        for i, r in enumerate(rooms, start=1):
            print(f"{i}. {r}")
        rn = self.input_room_name(2)
        self.sock.send(rn.encode("utf-8"))
        token = self.sock.recv(TOKEN_MAX_BYTE)
        return rn, token

    # ルーム名の入力を求め、バリデーションを行うメソッド
    def input_room_name(self, op):
        while True:
            prompt = "ルーム名作成 -> " if op == 1 else "参加するルーム名 -> "
            rn = input(prompt)
            if not rn:
                print("空です。再入力してください。")
            elif len(rn) > ROOM_NAME_MAX_BYTE:
                print("長すぎます。再入力してください。")
            else:
                return rn

    # TCPパケットを組み立てるメソッド
    def create_packet(self, room_name, operation, state, payload):
        header = self.create_header(room_name, operation, state, payload)
        return header + room_name.encode("utf-8") + payload.encode("utf-8")

    # TCPヘッダーを組み立てるメソッド
    def create_header(self, room_name, operation, state, payload):
        rn_size = len(room_name)
        pl_size = len(payload)
        return (
            rn_size.to_bytes(1, "big") +
            operation.to_bytes(1, "big") +
            state.to_bytes(1, "big") +
            pl_size.to_bytes(HEADER_SIZE - 3, "big")
        )


class UDPClient:
    def __init__(self, server_address, server_port, my_info):
        # UDP通信に必要なソケットとクライアント情報を初期化するメソッド
        self.server_address = server_address
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.my_info = my_info
        for t in my_info:
            self.token = t
            self.room_name = my_info[t][0]

    # 参加時にユーザー名をシステムメッセージとして送信するメソッド
    def send_username(self):
        username = self.my_info[self.token][1]
        init_msg = f"System: {username} が参加しました。"
        data = self._make_packet(init_msg.encode("utf-8"))
        self.sock.sendto(data, (self.server_address, self.server_port))

    # 通常メッセージを送信するメソッド
    def send(self, message):
        nm = f"{self.my_info[self.token][1]}: {message}"
        data = self._make_packet(nm.encode("utf-8"))
        self.sock.sendto(data, (self.server_address, self.server_port))

    # 非同期に受信可能なバッファからすべてのメッセージを取得するメソッド
    def fetch_messages(self):
        msgs = []
        self.sock.setblocking(False)
        while True:
            try:
                data = self.sock.recvfrom(4096)[0].decode("utf-8")
                msgs.append(data)
            except (BlockingIOError, OSError):
                break
        self.sock.setblocking(True)
        return msgs

    # ルーム名とトークンを付与してUDPパケットを作成する内部メソッド
    def _make_packet(self, body):
        rn_size = len(self.room_name).to_bytes(1, "big")
        tk_size = len(self.token).to_bytes(1, "big")
        return rn_size + tk_size + self.room_name.encode("utf-8") + self.token + body

    # CUIでチャットを開始し、送受信のスレッドを管理するメソッド
    def start_udp_chat(self):
        self.send_username()
        threading.Thread(target=self._cui_receive, daemon=True).start()
        while True:
            msg = input()
            self.send(msg)

    # CUIで受信メッセージを継続的に表示するメソッド
    def _cui_receive(self):
        while True:
            data = self.sock.recvfrom(4096)[0].decode("utf-8")
            print(data)
