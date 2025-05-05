import socket
import threading
import time
import sys
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# =========================================================
# TCP 通信（ルーム作成、参加、取得など）
# =========================================================
class ChatTCPClient:
    TOKEN_MAX_BYTES = 255
    ROOM_NAME_MAX_BYTES = 2 ** 8

    def __init__(self, server_address: str, server_port: int):
        self.server_address = server_address
        self.server_port = server_port

    def make_packet(self, room_name: str, operation: int, state: int, payload: str) -> bytes:
        rn_size = len(room_name)
        pl_size = len(payload)
        header = (
            rn_size.to_bytes(1, 'big') +
            operation.to_bytes(1, 'big') +
            state.to_bytes(1, 'big') +
            pl_size.to_bytes(32 - 3, 'big')
        )
        return header + room_name.encode('utf-8') + payload.encode('utf-8')

    def parse_room_list(self, data_str: str) -> list[str]:
        try:
            trimmed = data_str.strip()
            inner = trimmed[1:-1]
            rooms = [room.strip().strip("'\"") for room in inner.split(',') if room.strip()]
        except Exception:
            rooms = [data_str]
        return rooms

    def request_create_room(self, username: str, room: str) -> dict[bytes, list[str]]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((self.server_address, self.server_port))
            pkt = self.make_packet(room, 1, 0, username)
            sock.send(pkt)
            token = sock.recv(self.TOKEN_MAX_BYTES)
        return {token: [room, username]}

    def request_room_list(self, username: str) -> list[str]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((self.server_address, self.server_port))
            pkt = self.make_packet("", 2, 0, username)
            sock.send(pkt)
            raw = sock.recv(4096).decode("utf-8")
        return self.parse_room_list(raw)

    def request_join_room(self, username: str, room: str) -> dict[bytes, list[str]]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((self.server_address, self.server_port))
            pkt1 = self.make_packet("", 2, 0, username)
            sock.send(pkt1)
            _ = sock.recv(4096)
            sock.send(room.encode("utf-8"))
            token = sock.recv(self.TOKEN_MAX_BYTES)
        return {token: [room, username]}


# =========================================================
# UDP 通信（チャット送受信）
# =========================================================
class ChatUDPClient:
    def __init__(self, server_address: str, server_port: int, client_info: dict[bytes, list[str]]):
        self.server_address = server_address
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.token, (self.room_name, self.username) = next(iter(client_info.items()))

    def make_packet(self, body: bytes) -> bytes:
        room_bytes = self.room_name.encode('utf-8')
        return (
            len(room_bytes).to_bytes(1, 'big') +
            len(self.token).to_bytes(1, 'big') +
            room_bytes +
            self.token +
            body
        )

    def send_system_message(self) -> None:
        system_msg = f"System: {self.username} が参加しました。".encode('utf-8')
        self.sock.sendto(self.make_packet(system_msg), (self.server_address, self.server_port))

    def send_chat_message(self, message: str) -> None:
        body = f"{self.username}: {message}".encode('utf-8')
        self.sock.sendto(self.make_packet(body), (self.server_address, self.server_port))

    def receive_messages(self, existing: list[str]) -> list[str]:
        self.sock.settimeout(0.1)
        new_msgs = []
        try:
            while True:
                data, _ = self.sock.recvfrom(4096)
                msg = data.decode("utf-8")
                if msg and msg not in ("exit!", "Timeout!") and msg not in existing:
                    new_msgs.append(msg)
        except socket.timeout:
            pass
        return new_msgs


# =========================================================
# Streamlit による UI 描画
# =========================================================
class ChatUIManager:
    CSS_FILE = "style.css"

    def __init__(self, controller: "ChatAppController", tcp_client: ChatTCPClient):
        self.ctrl = controller
        self.tcp = tcp_client

    def setup_page(self) -> None:
        st.set_page_config(
            page_title="💬 リアルタイムチャット",
            page_icon="💬",
            layout="wide",
        )
        self._load_local_css()
        st.markdown("<div class='app-scale'>", unsafe_allow_html=True)

    def _load_local_css(self) -> None:
        css_path = Path(self.CSS_FILE)
        if css_path.exists():
            st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

    def render(self) -> None:
        page = self.ctrl.state.page
        if page == "home":
            self._render_home()
        elif page == "create":
            self._render_create()
        elif page == "join":
            self._render_join()
        elif page == "chat" and self.ctrl.state.client_info:
            if "udp_client" not in self.ctrl.state:
                self.ctrl.connect_udp()
            self._render_chat()
        st.markdown("</div>", unsafe_allow_html=True)

    def _render_home(self) -> None:
        st.markdown(
            """
            <div class="home-card">
              <h1>💬 リアルタイムチャット</h1>
            """,
            unsafe_allow_html=True,
        )
        st.button("ルームを作成", on_click=lambda: self.ctrl.switch_page("create"))
        st.button("ルームに参加", on_click=lambda: self.ctrl.switch_page("join"))
        st.markdown("</div>", unsafe_allow_html=True)

    def _render_create(self) -> None:
        state = self.ctrl.state
        st.markdown('<div class="form-card">', unsafe_allow_html=True)
        with st.form("create_room_form"):
            st.markdown("### ルーム作成", unsafe_allow_html=True)
            user = st.text_input("", key="create_user", placeholder="ユーザー名を入力")
            room = st.text_input("", key="create_room", placeholder="ルーム名を入力")
            col1, col2 = st.columns(2)
            with col1:
                create_clicked = st.form_submit_button("作成", type="primary", use_container_width=True)
            with col2:
                back_clicked = st.form_submit_button("← 戻る", type="secondary", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        if create_clicked:
            if not user or not room:
                st.warning("ユーザー名とルーム名を入力してください。")
                st.stop()
            try:
                info = self.tcp.request_create_room(user, room)
            except Exception as e:
                st.error(f"接続失敗: {e}")
                st.stop()
            state.client_info = info
            state.username = user
            state.room_name = room
            self.ctrl.connect_udp()
            self.ctrl.switch_page("chat")

        if back_clicked:
            self.ctrl.switch_page("home")

    def _render_join(self) -> None:
        state = self.ctrl.state
        st.markdown('<div class="join-card">', unsafe_allow_html=True)
        st.markdown("### ルーム参加", unsafe_allow_html=True)
        user = st.text_input("", key="join_user", placeholder="ユーザー名を入力")

        if st.button("ルーム一覧取得", disabled=not user):
            try:
                state.rooms = self.tcp.request_room_list(user)
            except Exception as e:
                st.error(f"取得失敗: {e}")

        if state.rooms:
            sel = st.selectbox("参加するルーム", state.rooms)
            if st.button("参加", disabled=not user or not sel):
                try:
                    info = self.tcp.request_join_room(user, sel)
                except Exception as e:
                    st.error(f"参加失敗: {e}")
                    st.stop()
                state.client_info = info
                state.username = user
                state.room_name = sel
                self.ctrl.connect_udp()
                self.ctrl.switch_page("chat")

        if st.button("← 戻る"):
            self.ctrl.switch_page("home")
        st.markdown("</div>", unsafe_allow_html=True)

    def _render_chat(self) -> None:
        state = self.ctrl.state
        udp: ChatUDPClient = state.udp_client

        # 自動リロード
        st_autorefresh(interval=2000, key="chat-refresh")

        # 新着メッセージ受信
        new_msgs = udp.receive_messages(state.messages)
        state.messages.extend(new_msgs)

        # チャット表示
        css = f"<style>{Path(self.CSS_FILE).read_text()}</style>"
        html = (
            f'<div class="chat-wrapper">'
            f'<div class="room-header">🏠 {state.room_name}</div>'
            f'<div class="chat-box" id="chat-box">'
        )
        for m in state.messages[-300:]:
            if ":" in m:
                sender, content = (s.strip() for s in m.split(":", 1))
                if sender == "System":
                    html += f'<div class="wrap system"><div class="msg">{content}</div></div>'
                else:
                    cls = "mine" if sender == state.username else "other"
                    html += (
                        f'<div class="wrap {cls}">'
                        f'<div class="name">{sender}</div>'
                        f'<div class="msg">{content}</div>'
                        f'</div>'
                    )
            elif m.strip():
                html += f'<div class="wrap system"><div class="msg">{m}</div></div>'
        html += """
                  <div id="bottom-anchor"></div>
                </div></div>
                <script>
                  const anchor=document.getElementById('bottom-anchor');
                  requestAnimationFrame(()=>anchor.scrollIntoView({block:'end'}));
                </script>
            """
        components.html(css + html, height=780, scrolling=False)

        # エンター送信用コールバック
        def _on_enter():
            msg = st.session_state.chat_input
            if msg:
                try:
                    udp.send_chat_message(msg)
                except Exception as e:
                    st.error(f"送信失敗: {e}")
                state.messages.append(f"{state.username}: {msg}")
            st.session_state.chat_input = ""

        # メッセージ入力（Enterで送信）
        st.text_input(
            "",
            key="chat_input",
            placeholder="メッセージを入力して Enter",
            on_change=_on_enter,
            label_visibility="collapsed",
        )


# =========================================================
# 状態管理、ページ遷移、UDP 起動
# =========================================================
class ChatAppController:
    def __init__(self) -> None:
        self.server = "127.0.0.1"
        self.tcp_port = 9001
        self.udp_port = 9002
        self.state = st.session_state
        self._init_session()

    def _init_session(self) -> None:
        defaults = {
            "page": "home",
            "client_info": None,
            "username": "",
            "room_name": "",
            "messages": [],
            "rooms": [],
            "udp_client": None,
            # chat_input キーも初期化
            "chat_input": "",
        }
        for k, v in defaults.items():
            if k not in self.state:
                self.state[k] = v

    def switch_page(self, page: str) -> None:
        self.state.page = page
        st.rerun()

    def connect_udp(self) -> None:
        self.state.udp_client = ChatUDPClient(
            self.server, self.udp_port, self.state.client_info
        )
        self.state.udp_client.send_system_message()


# =========================================================
# エントリーポイント
# =========================================================
if __name__ == '__main__':
    ctrl = ChatAppController()
    tcp_client = ChatTCPClient(ctrl.server, ctrl.tcp_port)
    ui_manager = ChatUIManager(ctrl, tcp_client)

    ui_manager.setup_page()
    ui_manager.render()
