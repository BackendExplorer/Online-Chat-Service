# ============================================================
#  client.py  ――  AES + RSA 暗号付きリアルタイムチャット
#                     ＋ 4 画面構成 Streamlit GUI
# ============================================================

import socket
import secrets
import json
from pathlib import Path
from Crypto.PublicKey import RSA
from Crypto.Cipher    import PKCS1_OAEP, AES

TOKEN_MAX_BYTE          = 255

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components



# ============================================================
# 暗号ユーティリティ
# ============================================================
class CryptoUtil:
    @staticmethod
    def aes_encrypt(data, key, iv):
        return AES.new(key, AES.MODE_CFB, iv=iv, segment_size=128).encrypt(data)

    @staticmethod
    def aes_decrypt(data, key, iv):
        return AES.new(key, AES.MODE_CFB, iv=iv, segment_size=128).decrypt(data)

    @staticmethod
    def rsa_encrypt(data, pub_key):
        return PKCS1_OAEP.new(pub_key).encrypt(data)

# ============================================================
# 鍵管理／暗号化ソケット
# ============================================================
class Encryption:
    def __init__(self):
        self.aes_key = self.iv = None

    def wrap_socket(self, sock):
        return EncryptedSocket(sock, self.aes_key, self.iv)


class EncryptedSocket:
    """AES-CFB で透過暗号化するソケット"""
    def __init__(self, sock, key, iv):
        self.sock, self.key, self.iv = sock, key, iv

    def _recvn(self, n):
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        return data

    def sendall(self, data):
        ct = CryptoUtil.aes_encrypt(data, self.key, self.iv)
        self.sock.sendall(len(ct).to_bytes(4, 'big') + ct)

    def recv(self, bufsize=4096):
        lb = self._recvn(4)
        if not lb:
            return b''
        enc_payload = self._recvn(int.from_bytes(lb, 'big'))
        return CryptoUtil.aes_decrypt(enc_payload, self.key, self.iv)

    def close(self):
        self.sock.close()


# ============================================================
# TCP クライアント
# ============================================================
class TCPClient:
    def __init__(self, server_address, server_port):
        self.server_address, self.server_port = server_address, server_port
        self.enc = Encryption()
        self.sock = None

    def _connect_and_handshake(self):
        """
        新プロトコル
          ① サーバ公開鍵 (len + key) を受信
          ② AES鍵+IV を生成しサーバ公開鍵で暗号化して送信
          ③ 暗号化ソケットへ切り替え
        """
        base = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        base.connect((self.server_address, self.server_port))

        # ① サーバ公開鍵
        s_pub_len = int.from_bytes(base.recv(4), 'big')
        server_pub_key = RSA.import_key(base.recv(s_pub_len))

        # ② AES鍵 + IV をサーバへ
        self.enc.aes_key, self.enc.iv = secrets.token_bytes(16), secrets.token_bytes(16)
        enc_sym = CryptoUtil.rsa_encrypt(self.enc.aes_key + self.enc.iv, server_pub_key)
        base.sendall(len(enc_sym).to_bytes(4, 'big') + enc_sym)

        # ③ 暗号化ソケット
        self.sock = self.enc.wrap_socket(base)

    def _make_packet(self, room, op, payload):
        payload_bin = json.dumps(payload).encode()
        header = (
            len(room.encode()).to_bytes(1, 'big') +
            op.to_bytes(1, 'big') +
            (0).to_bytes(1, 'big') +
            len(payload_bin).to_bytes(29, 'big')
        )
        return header + room.encode() + payload_bin

    def create_room(self, username, room, pwd):
        self._connect_and_handshake()
        self.sock.send(self._make_packet(room, 1, {"username": username, "password": pwd}))
        token = self.sock.recv(TOKEN_MAX_BYTE)
        self.sock.close()
        return {token: [room, username]}

    def get_room_list(self, username):
        self._connect_and_handshake()
        self.sock.send(self._make_packet("", 2, {"username": username, "password": ""}))
        raw = self.sock.recv(4096).decode()
        self.sock.close()
        try:
            inner = raw.strip()[1:-1]
            return [r.strip().strip("'\"") for r in inner.split(',') if r.strip()]
        except Exception:
            return [raw]

    def join_room(self, username, room, pwd):
        self._connect_and_handshake()
        self.sock.send(self._make_packet("", 2, {"username": username, "password": ""}))
        _ = self.sock.recv(4096)
        self.sock.send(self._make_packet(room, 2, {"username": username, "password": pwd}))
        resp = self.sock.recv(TOKEN_MAX_BYTE)
        self.sock.close()
        if resp.startswith(b"InvalidPassword"):
            raise ValueError("パスワードが違います。")
        if resp.startswith(b"InvalidRoom"):
            raise ValueError("ルームが存在しません。")
        return {resp: [room, username]}


# ============================================================
# UDP クライアント（変更なし）
# ============================================================
class UDPClient:
    def __init__(self, server_addr, server_port, info, enc):
        self.server_addr, self.server_port = server_addr, server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.enc  = enc
        self.token, (self.room, self.username) = next(iter(info.items()))
        self.send_system_message(f"{self.username} が参加しました。")

    def _make_packet(self, body=b""):
        enc_body = CryptoUtil.aes_encrypt(body, self.enc.aes_key, self.enc.iv)
        return (
            len(self.room).to_bytes(1,'big') + len(self.token).to_bytes(1,'big') +
            self.room.encode() + self.token + enc_body
        )

    def send_system_message(self, text):
        self.sock.sendto(self._make_packet(f"System: {text}".encode()),
                         (self.server_addr, self.server_port))

    def send_chat_message(self, text):
        self.sock.sendto(self._make_packet(f"{self.username}: {text}".encode()),
                         (self.server_addr, self.server_port))

    def fetch_messages(self, already):
        self.sock.settimeout(0.05)
        new = []
        try:
            while True:
                pkt,_ = self.sock.recvfrom(4096)
                rl,tl = pkt[:2]
                msg = CryptoUtil.aes_decrypt(pkt[2+rl+tl:], self.enc.aes_key, self.enc.iv).decode()
                if msg not in {"exit!", "Timeout!"} and msg not in already and msg not in new:
                    new.append(msg)
        except socket.timeout:
            pass
        return new
    
    
class GUIManager:
    CSS_FILE = "style.css"
    def __init__(self, controller):
        self.ctrl = controller
        self.tcp  = controller.tcp_client

    # ---------- 共通セットアップ ----------
    def setup(self):
        st.set_page_config("💬 セキュアチャット","💬",layout="centered")
        css_path = Path(self.CSS_FILE)
        if css_path.exists():
            st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)
        st.markdown('<div class="app-scale">', unsafe_allow_html=True)

    # ---------- ルーティング ----------
    def render(self):
        pg = self.ctrl.state.page
        if pg=="home":     self.page_home()
        elif pg=="create": self.page_create()
        elif pg=="join":   self.page_join()
        elif pg=="chat":   self.page_chat()
        st.markdown('</div>', unsafe_allow_html=True)

    # ---------- Home ----------
    def page_home(self):
        # タイトルカード
        st.markdown(
            """
            <div class="home-card">
              <h1>💬 Online Chat Service</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # タイトルとボタン列の間に余白を追加
        st.markdown("<div style='height: 3rem;'></div>", unsafe_allow_html=True)

        # 画面中央に 2 つのボタンを並べる
        left_spacer, col1, col2, right_spacer = st.columns([2, 3, 3, 2])

        with col1:
            create_clicked = st.button("ルームを作成", use_container_width=True)
        with col2:
            join_clicked = st.button("ルームに参加", use_container_width=True)

        # ボタン押下時の遷移
        if create_clicked:
            self.ctrl.switch_page("create")
        if join_clicked:
            self.ctrl.switch_page("join")

    # ---------- Create ----------
    def page_create(self):
        st.markdown("### ルームを作成",unsafe_allow_html=True)
        with st.form("create_form"):
            user = st.text_input("ユーザー名", key="create_user")
            room = st.text_input("ルーム名", key="create_room")
            pwd  = st.text_input("パスワード（任意）", type="password", key="create_pwd")
            c1,c2 = st.columns(2)
            create = c1.form_submit_button("作成", type="primary", use_container_width=True)
            back   = c2.form_submit_button("← 戻る", use_container_width=True)

        if back:
            self.ctrl.switch_page("home")
        if create:
            if not user or not room:
                st.warning("ユーザー名とルーム名を入力してください。")
                st.stop()
            try:
                info = self.tcp.create_room(user, room, pwd)
            except Exception as e:
                st.error(f"作成失敗: {e}")
                st.stop()
            self.ctrl.set_connection_info(info, user, room)
            self.ctrl.switch_page("chat")

    # ---------- Join ----------
    def page_join(self):
        state = self.ctrl.state
        st.markdown("### ルームに参加", unsafe_allow_html=True)
        user = st.text_input("ユーザー名", key="join_user")
        c1,c2 = st.columns(2)
        fetch = c1.button("ルーム一覧取得", disabled=not user, use_container_width=True)
        if c2.button("← 戻る", use_container_width=True):
            self.ctrl.switch_page("home")

        if fetch:
            try:
                rooms = self.tcp.get_room_list(user)
                state.rooms.clear()
                state.rooms.extend(rooms)
            except Exception as e:
                st.error(f"取得失敗: {e}")

        if state.rooms:
            sel = st.selectbox("参加するルーム", state.rooms)
            pwd = st.text_input("パスワード（必要な場合）",type="password", key="join_pwd")
            if st.button("参加", disabled=not sel or not user, use_container_width=True):
                try:
                    info = self.tcp.join_room(user, sel, pwd)
                except Exception as e:
                    st.error(f"参加失敗: {e}")
                    st.stop()
                self.ctrl.set_connection_info(info, user, sel)
                self.ctrl.switch_page("chat")

    # ---------- Chat ----------
    def page_chat(self):
        st_autorefresh(interval=2000, key="chat-refresh")
        state = self.ctrl.state
        udp = state.udp_client
        state.messages.extend(udp.fetch_messages(state.messages))

        css = f"<style>{Path(self.CSS_FILE).read_text()}</style>"
        html = (f'<div class="chat-wrapper"><div class="room-header">🏠 {state.room_name}</div>'
                f'<div class="chat-box" id="chat-box">')
        for m in state.messages[-300:]:
            if ":" in m:
                sender, content = (s.strip() for s in m.split(":",1))
                if sender=="System":
                    html += f'<div class="wrap system"><div class="msg">{content}</div></div>'
                else:
                    cls = "mine" if sender==state.username else "other"
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
        components.html(css+html, height=780, scrolling=False)

        def _on_enter():
            msg = st.session_state.chat_input
            if msg:
                try:
                    udp.send_chat_message(msg)
                except Exception as e:
                    st.error(f"送信失敗: {e}")
            st.session_state.chat_input = ""

        st.text_input(
            "",
            key="chat_input",
            placeholder="メッセージを入力して Enter",
            on_change=_on_enter,
            label_visibility="collapsed"
        )

# ============================================================
# Controller
# ============================================================
class AppController:
    def __init__(self, server = "server" , tcp_port=9001, udp_port=9002):
        self.server, self.tcp_port, self.udp_port = server, tcp_port, udp_port
        self.state = st.session_state
        self._init_state()
        self.tcp_client = TCPClient(self.server, self.tcp_port)

    def _init_state(self):
        defaults = {
            "page": "home",          # 今表示している画面（ホームが初期値）
            "rooms": [],             # 取得したルーム一覧
            "client_info": None,     # サーバから受け取ったユーザー接続情報
            "username": "",          # ユーザー名
            "room_name": "",         # 入っているチャットルーム名
            "udp_client": None,      # チャット通信を担当するUDPクライアント
            "messages": [],          # 受け取ったメッセージ一覧
            "chat_input": ""         # 入力中のチャットメッセージ
        }

        for k,v in defaults.items():
            if k not in self.state:
                self.state[k]=v

    def set_connection_info(self, info, user, room):
        self.state.client_info = info
        self.state.username    = user
        self.state.room_name   = room
        self.state.messages    = []
        self.state.udp_client  = UDPClient(self.server, self.udp_port, info, self.tcp_client.enc)

    def switch_page(self, page):
        self.state.page = page
        st.rerun()

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    ctrl = AppController()
    gui  = GUIManager(ctrl)
    gui.setup()
    gui.render()
