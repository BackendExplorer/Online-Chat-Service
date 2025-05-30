from pathlib import Path
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

from client import TCPClient, UDPClient


class GUIManager:
    CSS_FILE = "style.css"

    def __init__(self, controller):
        self.controller = controller
        self.tcp_client  = controller.tcp_client

    # アプリ全体に適用する共通設定（タイトル・レイアウト・CSSなど）
    def setup(self):
        st.set_page_config("💬 Online Chat Service", "💬", layout="centered")
        
        # CSSファイルが存在する場合は読み込んで反映
        css_path = Path(self.CSS_FILE)
        if css_path.exists():
            st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)

        
        st.markdown('<div class="app-scale">', unsafe_allow_html=True)

    # 現在のページに応じて適切な画面描画関数を呼び出す
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

        # レイアウト用DIVを閉じる
        st.markdown('</div>', unsafe_allow_html=True)

    # ホーム画面（ルート画面）を表示
    def page_home(self):
        # タイトルカードの表示
        st.markdown(
            """
            <div class="home-card">
              <h1>💬 Online Chat Service</h1>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 間隔をあけるためのスペース
        st.markdown("<div style='height: 3rem;'></div>", unsafe_allow_html=True)

        # ボタン配置（中央に「作成」と「参加」ボタンを並べる）
        left_spacer, col_left, col_right, right_spacer = st.columns([2, 3, 3, 2])
        with col_left:
            create_clicked = st.button("ルームを作成", use_container_width=True)
        with col_right:
            join_clicked = st.button("ルームに参加", use_container_width=True)

        # ボタンのクリックに応じてページ遷移
        if create_clicked:
            self.controller.switch_page("create")
        if join_clicked:
            self.controller.switch_page("join")

    # ルーム作成画面の描画処理
    def page_create(self):
        # 画面タイトルの表示
        st.markdown("### ルームを作成", unsafe_allow_html=True)

        # ルーム作成フォームの構築
        with st.form("create_form"):
            # 入力フィールド（ユーザー名、ルーム名、パスワード）
            username   = st.text_input("ユーザー名", key="create_username")
            room_name  = st.text_input("ルーム名", key="create_room_name")
            password   = st.text_input("パスワード（任意）", type="password", key="create_password")

            # ボタンのレイアウト（左: 作成 / 右: 戻る）
            col_left, col_right = st.columns(2)
            create = col_left.form_submit_button("作成", type="primary", use_container_width=True)
            back   = col_right.form_submit_button("← 戻る", use_container_width=True)

        # 戻るボタンが押された場合はホーム画面へ戻る
        if back:
            self.controller.switch_page("home")

        # 作成ボタンが押された場合の処理
        if create:
            # 入力チェック（ユーザー名・ルーム名が必須）
            if not username or not room_name:
                st.warning("ユーザー名とルーム名を入力してください。")
                st.stop()
            try:
                # サーバーへルーム作成要求を送信し、接続情報を受信
                connection_info = self.tcp_client.create_room(username, room_name, password)
            except Exception as e:
                st.error(f"作成失敗: {e}")
                st.stop()

            # 接続情報を保存し、チャット画面へ遷移
            self.controller.set_connection_info(connection_info, username, room_name)
            self.controller.switch_page("chat")

    # ルーム参加画面の描画処理
    def page_join(self):
        session = self.controller.session

        # タイトル表示
        st.markdown("### ルームに参加", unsafe_allow_html=True)

        # ユーザー名の入力欄
        username = st.text_input("ユーザー名", key="join_username")

        # ボタンのレイアウト（左: ルーム一覧取得 / 右: 戻る）
        col_left, col_right = st.columns(2)
        fetch = col_left.button("ルーム一覧取得", disabled=not username, use_container_width=True)
        if col_right.button("← 戻る", use_container_width=True):
            self.controller.switch_page("home")

        # 一覧取得ボタンが押された場合の処理
        if fetch:
            try:
                # サーバーからルーム一覧を取得し、セッションに保存
                room_list = self.tcp_client.get_room_list(username)
                session.room_list.clear()
                session.room_list.extend(room_list)
            except Exception as e:
                st.error(f"取得失敗: {e}")

        # ルーム一覧が存在する場合、セレクトボックスを表示
        if session.room_list:
            selected_room = st.selectbox("参加するルーム", session.room_list)

            # パスワードの入力欄（必要に応じて）
            password = st.text_input("パスワード（必要な場合）", type="password", key="join_password")
            
            # 参加ボタンが押された場合の処理
            if st.button("参加", disabled=not selected_room or not username, use_container_width=True):
                try:
                    # サーバーにルーム参加リクエストを送信
                    connection_info = self.tcp_client.join_room(username, selected_room, password)
                except Exception as e:
                    st.error(f"参加失敗: {e}")
                    st.stop()

                # 接続情報を保存してチャット画面に遷移
                self.controller.set_connection_info(connection_info, username, selected_room)
                self.controller.switch_page("chat")

    # チャット画面の描画処理
    def page_chat(self):
        # 一定間隔（2秒）で自動リフレッシュ
        st_autorefresh(interval=2000, key="chat-refresh")
        
        session = self.controller.session
        udp   = session.udp_client

        # 新着メッセージを取得してセッションに追加
        session.messages.extend(udp.fetch_messages(session.messages))

        # チャット画面のスタイルとヘッダーHTMLを生成
        css  = f"<style>{Path(self.CSS_FILE).read_text()}</style>"
        html = (
        f'<div class="chat-wrapper">'
        f'<div class="room-header">🏠 {session.room_name}</div>'
        f'<div class="chat-box" id="chat-box">'
        )
        
        # 最大300件のメッセージを順にHTML形式で描画
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

        # チャット画面の最下部へのスクロールスクリプトを追加
        html += """
            <div id="bottom-anchor"></div></div></div>
            <script>
              const a=document.getElementById('bottom-anchor');
              requestAnimationFrame(()=>a.scrollIntoView({block:'end'}));
            </script>
        """

        # HTMLを描画
        components.html(css + html, height=780, scrolling=False)

        # メッセージ送信時の処理（Enterで発火）
        def on_enter():
            message_text = st.session_state.chat_input
            if message_text:
                try:
                    udp.send_chat_message(message_text)
                except Exception as e:
                    st.error(f"送信失敗: {e}")
            st.session_state.chat_input = ""

        # メッセージ入力フィールド
        st.text_input(
            "",
            key="chat_input",
            placeholder="メッセージを入力して Enter",
            on_change=on_enter,
            label_visibility="collapsed"
        )


class AppController:
    def __init__(self, server="server", tcp_port=9001, udp_port=9002):
        # サーバーアドレスとポート番号を設定
        self.server     = server
        self.tcp_port   = tcp_port
        self.udp_port   = udp_port

         # Streamlitのセッションステートを取得
        self.session      = st.session_state
        
        # セッション状態の初期化
        self.init_session()
        
        # TCPクライアントを生成
        self.tcp_client = TCPClient(self.server, self.tcp_port)

    def init_session(self):
        # セッションステートの初期値を設定
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

        # セッションにキーが無い場合は初期値を設定
        for k, v in defaults.items():
            if k not in self.session:
                self.session[k] = v

    def set_connection_info(self, connection_info, username, room_name):
        # クライアントの接続情報とユーザー情報をセッションに保存
        self.session.client_info = connection_info
        self.session.username    = username
        self.session.room_name   = room_name
        self.session.messages    = []

        # UDPクライアントを初期化
        self.session.udp_client  = UDPClient(
            self.server, self.udp_port, connection_info, self.tcp_client.cipher
        )

    def switch_page(self, page_name):
         # 表示するページを変更し、再描画
        self.session.page_name = page_name
        st.rerun()
