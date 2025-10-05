import socket
import secrets
import json
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP, AES



class RSAKeyExchange:
    
    def __init__(self):
        # ランダムな AES 鍵と IV（初期化ベクトル）を生成して保持
        self.aes_key = secrets.token_bytes(16)
        self.iv = secrets.token_bytes(16)

    def encrypted_shared_secret(self, server_pub_key):
        # AES 鍵と IV を連結して共有秘密情報を作成
        shared = self.aes_key + self.iv
        # サーバの公開鍵を使って共有秘密情報を RSA で暗号化
        return PKCS1_OAEP.new(server_pub_key).encrypt(shared)


class AESCipherCFB:
    
    def __init__(self, key, iv):
        # AES 共通鍵と初期化ベクトル（IV）を保存
        self.key = key
        self.iv = iv

    def encrypt(self, data):
        # AES CFBモードで与えられたデータを暗号化して返す
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).encrypt(data)

    def decrypt(self, data):
        # AES CFBモードで与えられたデータを復号して返す
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).decrypt(data)


class SecureSocket:
    
    def __init__(self, raw_sock, cipher):
        # 生のソケットと暗号化用の AES オブジェクトを保持
        self.raw_sock = raw_sock
        self.cipher = cipher

    # 指定されたバイト数を受信するまで繰り返す
    def recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            part = self.raw_sock.recv(n - len(buf))
            if not part:
                break
            buf.extend(part)
        return bytes(buf)

    def sendall(self, plaintext):
        # 平文を暗号化して長さ付きで送信
        ciphertext = self.cipher.encrypt(plaintext)
        self.raw_sock.sendall(len(ciphertext).to_bytes(4, 'big') + ciphertext)

    def recv(self):
        # 最初の 4 バイトで暗号化データの長さを取得し、その長さ分を受信して復号
        length_bytes = self.recv_exact(4)
        ciphertext = self.recv_exact(int.from_bytes(length_bytes, 'big'))
        return self.cipher.decrypt(ciphertext)

    def close(self):
        self.raw_sock.close()


class TCPClient:
    
    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.cipher = None    
        self.sock = None

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
        self.sock = SecureSocket(tcp_socket, self.cipher)

    def make_header(self, room_bytes, op, state, payload_bytes):
        room_size    = len(room_bytes).to_bytes(1, 'big')
        op_code      = op.to_bytes(1, 'big')
        state_code   = state.to_bytes(1, 'big')
        payload_size = len(payload_bytes).to_bytes(29, 'big')
    
        return room_size + op_code + state_code + payload_size

    def make_packet(self, room, op, state, payload):
        payload_obj = payload if payload is not None else {}
        payload_bytes = json.dumps(payload_obj).encode("utf-8")
        room_bytes = room.encode("utf-8")
        header = self.make_header(room_bytes, op, state, payload_bytes)
        return header + room_bytes + payload_bytes
    
    def decode_server_response(self, data):
        # サーバーからのレスポンスパケットをデコードする
        header = data[:32]
        body = data[32:]
        
        room_name_size = header[0]
        operation = header[1]
        state = header[2]
        payload_size = int.from_bytes(header[3:], 'big')
        
        room_name = body[:room_name_size].decode('utf-8')
        payload = body[room_name_size:room_name_size+payload_size] # payloadはJSONかもしれないし、ただのバイト列かもしれない
        
        return room_name, operation, state, payload

    # クライアントが新しいルームを作成する関数
    def create_room(self, username, room, password):
        try:
            # サーバーに接続して鍵交換を行う
            self.connect_and_handshake()

            # 操作コード：1 = ルーム作成, 状態: 0 = リクエスト
            op_code = 1
            state = 0
            payload = {"username": username, "password": password}
            packet = self.make_packet(room, op_code, state, payload)

            # State: 0 のパケットを送信
            self.sock.sendall(packet)

            # State: 1 (準拠) の応答を待つ
            ack_response = self.sock.recv()
            _, _, ack_state, _ = self.decode_server_response(ack_response)
            if ack_state != 1:
                raise ConnectionAbortedError("サーバーからのACKが不正です。")

            # State: 2 (完了) の応答（トークン）を待つ
            complete_response = self.sock.recv()
            _, _, token_state, token = self.decode_server_response(complete_response)
            if token_state != 2:
                raise ConnectionAbortedError("サーバからトークンを受信できませんでした。")

            # トークンとルーム情報を返す
            return {token: [room, username]}
        finally:
            if self.sock:
                self.sock.close()

    # サーバーからルーム一覧を取得する関数
    def get_room_list(self):
        try:
            # サーバーと接続して鍵交換を行う
            self.connect_and_handshake()

            # 操作コード：4 = ルーム一覧取得, 状態: 0 = リクエスト
            op_code = 3
            state = 0
            packet = self.make_packet("", op_code, state, {})

            # パケットを送信
            self.sock.sendall(packet)

            # サーバーからの応答を受信・復号
            response_data = self.sock.recv()
            _, _, resp_state, payload_bytes = self.decode_server_response(response_data)
            
            if resp_state != 1:
                raise ConnectionAbortedError("ルーム一覧の取得に失敗しました。")

            response = payload_bytes.decode()

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
        finally:
            if self.sock:
                self.sock.close()

    # クライアントが既存のルームに参加する関数
    def join_room(self, username, room, password):
        try:
            # サーバーに接続して鍵交換を行う
            self.connect_and_handshake()

            # 操作コード：2 = ルーム参加, 状態: 0 = リクエスト
            op_code = 2
            state = 0
            payload = {"username": username, "password": password}
            packet = self.make_packet(room, op_code, state, payload)

            # パケットを送信
            self.sock.sendall(packet)

            # State: 1 (準拠) または State: 255 (エラー) の応答を待つ
            ack_response = self.sock.recv()
            _, _, ack_state, ack_payload = self.decode_server_response(ack_response)
            
            # エラー処理
            if ack_state == 255:
                error_msg = ack_payload.decode()
                if "InvalidPassword" in error_msg:
                    raise ValueError("パスワードが違います。")
                if "InvalidRoom" in error_msg:
                    raise ValueError("ルームが存在しません。")
                raise ConnectionAbortedError(f"参加エラー: {error_msg}")
            
            if ack_state != 1:
                raise ConnectionAbortedError("サーバーからのACKが不正です。")

            # State: 2 (完了) の応答（トークン）を待つ
            complete_response = self.sock.recv()
            _, _, token_state, token = self.decode_server_response(complete_response)
            if token_state != 2:
                raise ConnectionAbortedError("サーバからトークンを受信できませんでした。")

            # 正常応答：トークンを辞書で返す
            return {token: [room, username]}
        finally:
            if self.sock:
                self.sock.close()


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
    
        room_name_size  = len(self.room).to_bytes(1, 'big')    # ルーム名のサイズ
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


class GUIManager:
    
    def __init__(self, controller):
        self.controller = controller
        self.tcp_client = controller.tcp_client

    # アプリの基本設定（ページタイトルやレイアウト）
    def setup(self):
        st.set_page_config("💬 Online Chat Service", "💬", layout="centered")

    # 現在のページ状態に応じて適切な描画関数を呼び出す
    def render(self):
        page_name = self.controller.session.page_name
        page_function = getattr(self, f"page_{page_name}", self.page_home)
        page_function()

    # ホーム画面（ルーム作成・参加の選択）を表示
    def page_home(self):
        st.title("💬 Online Chat Service")
        st.write("ルームを作成するか、既存のルームに参加してください。")

        col1, col2 = st.columns(2)
        if col1.button("ルームを作成", use_container_width=True):
            self.controller.switch_page("create")
        if col2.button("ルームに参加", use_container_width=True):
            self.controller.switch_page("join")

    # ルーム作成画面を表示
    def page_create(self):
        st.header("ルームを作成")
        with st.form("create_form"):
            username = st.text_input("ユーザー名", key="create_username")
            room_name = st.text_input("ルーム名", key="create_room_name")
            password = st.text_input("パスワード（任意）", type="password", key="create_password")

            c1, c2 = st.columns(2)
            create_clicked = c1.form_submit_button("作成", use_container_width=True, type="primary")
            back_clicked = c2.form_submit_button("← 戻る", use_container_width=True)

        if back_clicked:
            self.controller.switch_page("home")

        if create_clicked:
            if not username or not room_name:
                st.warning("ユーザー名とルーム名を入力してください。")
            else:
                try:
                    connection_info = self.tcp_client.create_room(username, room_name, password)
                    self.controller.set_connection_info(connection_info, username, room_name)
                    self.controller.switch_page("chat")
                except Exception as e:
                    st.error(f"作成失敗: {e}")

    # ルーム参加画面を表示
    def page_join(self):
        session = self.controller.session
        st.header("ルームに参加")

        username = st.text_input("ユーザー名", key="join_username")

        c1, c2 = st.columns(2)
        fetch_clicked = c1.button("ルーム一覧取得", disabled=not username, use_container_width=True)
        if c2.button("← 戻る", use_container_width=True):
            self.controller.switch_page("home")

        if fetch_clicked:
            try:
                session.room_list = self.tcp_client.get_room_list()
            except Exception as e:
                st.error(f"取得失敗: {e}")
                session.room_list = []

        if session.get("room_list"):
            selected_room = st.selectbox("参加するルーム", session.room_list)
            password = st.text_input("パスワード（必要な場合）", type="password", key="join_password")
            
            if st.button("参加", disabled=(not selected_room or not username), use_container_width=True):
                try:
                    connection_info = self.tcp_client.join_room(username, selected_room, password)
                    self.controller.set_connection_info(connection_info, username, selected_room)
                    self.controller.switch_page("chat")
                except Exception as e:
                    st.error(f"参加失敗: {e}")

    # チャット画面を表示
    def page_chat(self):
        st_autorefresh(interval=2000, key="chat-refresh")
        
        session = self.controller.session
        if not session.get("udp_client"):
            st.error("接続情報がありません。ホーム画面に戻ります。")
            if st.button("ホームへ戻る"):
                self.controller.switch_page("home")
            return

        udp = session.udp_client
        session.messages.extend(udp.fetch_messages(session.messages))

        st.header(f"ルーム: {session.room_name}")

        # メッセージをコンテナ内に表示してスクロール可能にする
        with st.container(height=500):
            for msg in session.messages:
                st.text(msg)

        # メッセージ送信時のコールバック関数
        def send_message():
            message_text = st.session_state.chat_input
            if message_text:
                try:
                    udp.send_chat_message(message_text)
                    st.session_state.chat_input = ""  # 送信後にテキストボックスを空にする
                except Exception as e:
                    st.error(f"送信失敗: {e}")
        
        st.text_input(
            "メッセージを入力",
            key="chat_input",
            on_change=send_message,
            placeholder="メッセージを入力してEnterキーを押してください",
            label_visibility="collapsed"
        )


class AppController:
    
    def __init__(self, server_address, tcp_port, udp_port):
        self.server_address = server_address
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.session = st.session_state
        self.init_session()
        self.tcp_client = TCPClient(self.server_address, self.tcp_port)

    # セッションが初期化されていない場合にデフォルト値を設定
    def init_session(self):
        defaults = {
            "page_name": "home",
            "room_list": [],
            "client_info": None,
            "username": "",
            "room_name": "",
            "udp_client": None,
            "messages": [],
            "chat_input": ""
        }
        for key, value in defaults.items():
            if key not in self.session:
                self.session[key] = value

    # サーバー接続後の情報をセッションに保存し、UDPクライアントを初期化
    def set_connection_info(self, connection_info, username, room_name):
        self.session.client_info = connection_info
        self.session.username = username
        self.session.room_name = room_name
        self.session.messages = []
        self.session.udp_client = UDPClient(
            self.server_address, self.udp_port, connection_info, self.tcp_client.cipher
        )

    # 指定されたページに遷移し、画面を再描画
    def switch_page(self, page_name):
        self.session.page_name = page_name
        st.rerun()



if __name__ == "__main__":
    
    # サーバーの IPアドレス と ポート番号 を設定
    server_address = '54.91.145.226'
    tcp_server_port = 9001
    udp_server_port = 9002
    controller = AppController(server_address, tcp_server_port, udp_server_port)

    gui = GUIManager(controller)
    gui.setup()
    gui.render()