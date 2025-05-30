import socket
import secrets
import json
import time
from pathlib import Path
from Crypto.PublicKey import RSA
from Crypto.Cipher    import PKCS1_OAEP, AES

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components



class RSAKeyExchange:
    def __init__(self):
        self.aes_key = secrets.token_bytes(16)
        self.iv      = secrets.token_bytes(16)

    def encrypted_shared_secret(self, server_pub_key):
        shared = self.aes_key + self.iv
        return PKCS1_OAEP.new(server_pub_key).encrypt(shared)


class AESCipherCFB:
    def __init__(self, key, iv):
        self.key = key
        self.iv  = iv

    def encrypt(self, data):
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).encrypt(data)

    def decrypt(self, data):
        return AES.new(self.key, AES.MODE_CFB, iv=self.iv, segment_size=128).decrypt(data)


class SecureSocket:
    def __init__(self, raw_sock, cipher):
        self.raw_sock = raw_sock
        self.cipher   = cipher

    def recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            part = self.raw_sock.recv(n - len(buf))
            if not part:
                break
            buf.extend(part)
        return bytes(buf)

    def sendall(self, plaintext):
        ciphertext = self.cipher.encrypt(plaintext)
        self.raw_sock.sendall(len(ciphertext).to_bytes(4, 'big') + ciphertext)

    def recv(self):
        length_bytes = self.recv_exact(4)
        if not length_bytes:
            return b''
        ciphertext = self.recv_exact(int.from_bytes(length_bytes, 'big'))
        return self.cipher.decrypt(ciphertext)

    def close(self):
        self.raw_sock.close()


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
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((self.server_address, self.server_port))

        # ① サーバ公開鍵を受信
        pubkey_length = int.from_bytes(tcp_socket.recv(4), 'big')
        server_public_key = RSA.import_key(tcp_socket.recv(pubkey_length))

        # ② 共有鍵(AES鍵 + IV) を暗号化して送信
        key_exchanger = RSAKeyExchange()
        encrypted_secret = key_exchanger.encrypted_shared_secret(server_public_key)
        tcp_socket.sendall(len(encrypted_secret).to_bytes(4, 'big') + encrypted_secret)

        # ③ 暗号化ソケット確立
        self.cipher = AESCipherCFB(key_exchanger.aes_key, key_exchanger.iv)
        self.sock   = SecureSocket(tcp_socket, self.cipher)

    def make_header(self, room_bytes, op, state, payload_bytes):
        return (
            len(room_bytes).to_bytes(self.HEADER_ROOM_LEN, 'big') +
            op.to_bytes(self.HEADER_OP_LEN, 'big') +
            state.to_bytes(self.HEADER_STATE_LEN, 'big') +
            len(payload_bytes).to_bytes(self.HEADER_PAYLOAD_LEN, 'big')
        )

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

    # パケットを作成する内部メソッド
    def make_packet(self, body=b""):
        encrypted_body = self.cipher.encrypt(body)

        return (
            len(self.room).to_bytes(1, 'big') +                # ルーム名の長さ
            len(self.token).to_bytes(1, 'big') +               # トークンの長さ
            self.room.encode() +                               # ルーム名本体
            self.token +                                       # トークン本体
            encrypted_body                                     # 暗号化済みメッセージ
        )

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

                room_len = packet[0]
                token_len = packet[1]

                encrypted_msg = packet[2 + room_len + token_len:]
                message = self.cipher.decrypt(encrypted_msg).decode()

                if message in {"exit!", "Timeout!"}:
                    continue

                if message not in already and message not in new_messages:
                    new_messages.append(message)

        except socket.timeout:
            pass

        return new_messages


class GUIManager:
    CSS_FILE = "style.css"

    def __init__(self, controller):
        self.controller = controller
        self.tcp_client  = controller.tcp_client

    # ---------- 共通セットアップ ----------
    def setup(self):
        st.set_page_config("💬 Online Chat Service", "💬", layout="centered")
        css_path = Path(self.CSS_FILE)
        if css_path.exists():
            st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)
        st.markdown('<div class="app-scale">', unsafe_allow_html=True)

    # ---------- ルーティング ----------
    def render(self):
        page_name = self.controller.session.page_name
        if page_name == "home":
            self.page_home()
        elif page_name == "create":
            self.page_create()
        elif page_name == "join":
            self.page_join()
        elif page_name == "chat":
            self.page_chat()
        st.markdown('</div>', unsafe_allow_html=True)

    # --------------------- Home ------------------------------
    def page_home(self):
        st.markdown(
            """
            <div class="home-card">
              <h1>💬 Online Chat Service</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height: 3rem;'></div>", unsafe_allow_html=True)

        left_spacer, col_left, col_right, right_spacer = st.columns([2, 3, 3, 2])
        with col_left:
            create_clicked = st.button("ルームを作成", use_container_width=True)
        with col_right:
            join_clicked = st.button("ルームに参加", use_container_width=True)

        if create_clicked:
            self.controller.switch_page("create")
        if join_clicked:
            self.controller.switch_page("join")

    # --------------------- Create ----------------------------
    def page_create(self):
        st.markdown("### ルームを作成", unsafe_allow_html=True)
        with st.form("create_form"):
            username   = st.text_input("ユーザー名", key="create_username")
            room_name  = st.text_input("ルーム名", key="create_room_name")
            password   = st.text_input("パスワード（任意）", type="password", key="create_password")
            col_left, col_right = st.columns(2)
            create = col_left.form_submit_button("作成", type="primary", use_container_width=True)
            back   = col_right.form_submit_button("← 戻る", use_container_width=True)

        if back:
            self.controller.switch_page("home")
        if create:
            if not username or not room_name:
                st.warning("ユーザー名とルーム名を入力してください。")
                st.stop()
            try:
                connection_info = self.tcp_client.create_room(username, room_name, password)
            except Exception as e:
                st.error(f"作成失敗: {e}")
                st.stop()
            self.controller.set_connection_info(connection_info, username, room_name)
            self.controller.switch_page("chat")

    # --------------------- Join ------------------------------
    def page_join(self):
        session = self.controller.session
        st.markdown("### ルームに参加", unsafe_allow_html=True)
        username = st.text_input("ユーザー名", key="join_username")
        col_left, col_right = st.columns(2)
        fetch = col_left.button("ルーム一覧取得", disabled=not username, use_container_width=True)
        if col_right.button("← 戻る", use_container_width=True):
            self.controller.switch_page("home")

        if fetch:
            try:
                room_list = self.tcp_client.get_room_list(username)
                session.room_list.clear()
                session.room_list.extend(room_list)
            except Exception as e:
                st.error(f"取得失敗: {e}")

        if session.room_list:
            selected_room = st.selectbox("参加するルーム", session.room_list)
            password = st.text_input("パスワード（必要な場合）", type="password", key="join_password")
            if st.button("参加", disabled=not selected_room or not username, use_container_width=True):
                try:
                    connection_info = self.tcp_client.join_room(username, selected_room, password)
                except Exception as e:
                    st.error(f"参加失敗: {e}")
                    st.stop()
                self.controller.set_connection_info(connection_info, username, selected_room)
                self.controller.switch_page("chat")

    # --------------------- Chat ------------------------------
    def page_chat(self):
        st_autorefresh(interval=2000, key="chat-refresh")
        session = self.controller.session
        udp   = session.udp_client
        session.messages.extend(udp.fetch_messages(session.messages))

        css  = f"<style>{Path(self.CSS_FILE).read_text()}</style>"
        html = (f'<div class="chat-wrapper"><div class="room-header">🏠 {session.room_name}</div>'
                f'<div class="chat-box" id="chat-box">')
        for m in session.messages[-300:]:
            if ":" in m:
                sender, content = (s.strip() for s in m.split(":", 1))
                if sender == "System":
                    html += f'<div class="wrap system"><div class="msg">{content}</div></div>'
                else:
                    cls = "mine" if sender == session.username else "other"
                    html += (f'<div class="wrap {cls}"><div class="name">{sender}</div>'
                             f'<div class="msg">{content}</div></div>')
            elif m.strip():
                html += f'<div class="wrap system"><div class="msg">{m}</div></div>'
        html += """
            <div id="bottom-anchor"></div></div></div>
            <script>
              const a=document.getElementById('bottom-anchor');
              requestAnimationFrame(()=>a.scrollIntoView({block:'end'}));
            </script>
        """
        components.html(css + html, height=780, scrolling=False)

        def on_enter():
            message_text = st.session_state.chat_input
            if message_text:
                try:
                    udp.send_chat_message(message_text)
                except Exception as e:
                    st.error(f"送信失敗: {e}")
            st.session_state.chat_input = ""

        st.text_input(
            "",
            key="chat_input",
            placeholder="メッセージを入力して Enter",
            on_change=on_enter,
            label_visibility="collapsed"
        )


class AppController:
    def __init__(self, server="server", tcp_port=9001, udp_port=9002):
        self.server     = server
        self.tcp_port   = tcp_port
        self.udp_port   = udp_port
        self.session      = st.session_state
        self.init_session()
        self.tcp_client = TCPClient(self.server, self.tcp_port)

    def init_session(self):
        defaults = {
            "page_name":       "home",
            "room_list":      [],
            "client_info": None,
            "username":   "",
            "room_name":  "",
            "udp_client": None,
            "messages":   [],
            "chat_input": ""
        }
        for k, v in defaults.items():
            if k not in self.session:
                self.session[k] = v

    def set_connection_info(self, connection_info, username, room_name):
        self.session.client_info = connection_info
        self.session.username    = username
        self.session.room_name   = room_name
        self.session.messages    = []

        # --- UDP クライアント作成
        self.session.udp_client  = UDPClient(
            self.server, self.udp_port, connection_info, self.tcp_client.cipher
        )

    def switch_page(self, page_name):
        self.session.page_name = page_name
        st.rerun()


if __name__ == "__main__":
    controller = AppController()
    gui  = GUIManager(controller)
    gui.setup()
    gui.render()
