import streamlit as st
from streamlit_autorefresh import st_autorefresh
from client import TCPClient, UDPClient
import streamlit.components.v1 as components
import sys

# =====================
# アプリコントローラ
# =====================
class ChatAppController:
    def __init__(self):
        self.server = "0.0.0.0"
        self.tcp_port = 9001
        self.udp_port = 9002
        self.state = st.session_state
        self._init_session()

    def _init_session(self):
        defaults = {
            "page": "home",
            "tcp": None,
            "udp": None,
            "client_info": None,
            "username": "",
            "room_name": "",
            "messages": [],
            "rooms": [],
        }
        for key, val in defaults.items():
            if key not in self.state:
                self.state[key] = val

    def switch_page(self, to):
        self.state.page = to
        st.rerun()

    def connect_tcp(self):
        self.state.tcp = TCPClient(self.server, self.tcp_port)

    def connect_udp(self):
        self.state.udp = UDPClient(self.server, self.udp_port, self.state.client_info)
        self.state.udp.send_username()

    def save_client_info(self, info, user, room):
        self.state.client_info = info
        self.state.username = user
        self.state.room_name = room

# =====================
# UI レンダラー
# =====================
class ChatPageRenderer:
    def __init__(self, controller):
        self.ctrl = controller
        self.state = controller.state

    
    def render_home(self):
        # ⚙️ スタイルと中央寄せ用のラッパーを注入
        st.markdown(
            """
            <style>
            /* ────────────────────────────────
            メイン領域を画面いっぱいに広げて
            子要素を縦横センターに並べる
            ──────────────────────────────── */
            div.block-container {
                display: flex;
                flex-direction: column;   /* 垂直方向に並べる */
                justify-content: center;  /* ↕ 縦方向の中央寄せ */
                align-items: center;      /* ↔ 横方向の中央寄せ */
                min-height: 100vh;        /* ビューポート全高 */
            }

            /* ボタンの装飾 */
            div.stButton > button {
                background-color: #1E90FF !important;
                color: white !important;
                padding: 0.75em 2em !important;
                font-size: 16px !important;
                border: none !important;
                border-radius: 8px !important;
                transition: background-color 0.3s ease !important;
            }
            div.stButton > button:hover {
                background-color: #0f75d1 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # ボタンを横並びに配置
        col1, col2 = st.columns(2, gap="large")
        with col1:
            if st.button("ルームを作成"):
                self.ctrl.switch_page("create")
        with col2:
            if st.button("ルームに参加"):
                self.ctrl.switch_page("join")

                
    def render_create(self):
    # ── 1) CSS で中央寄せ＆カード化＋スタイル ─────────────────────────
        st.markdown(
            """
            <style>
            /* 画面中央寄せ */
            div.block-container{
                display:flex;justify-content:center;align-items:center;min-height:100vh;
            }

            /* st.form をカード化 */
            div.stForm{
                background:#fff;padding:2.5rem 3rem;border-radius:14px;
                box-shadow:0 6px 24px rgba(0,0,0,.08);width:100%;max-width:480px;
            }

            /* 見出し */
            div.stForm h2{margin:0 0 1.5rem;font-size:1.8rem;}

            /* ───────── 入力欄 ───────── */
            div[data-baseweb="input"]{
                border:1px solid #e6e6e6 !important;border-radius:8px !important;
                transition:border .2s ease,box-shadow .2s ease;box-shadow:none !important;
            }
            div[data-baseweb="input"] input{
                padding:.75rem 1rem;font-size:1rem;border:none;outline:none !important;
            }
            div[data-baseweb="input"]:hover{
                border:1px solid #1E90FF !important;
                box-shadow:0 0 0 2px rgba(30,144,255,.15) !important;
            }
            div[data-baseweb="input"]:focus-within{
                border:1px solid #1E90FF !important;
                box-shadow:0 0 0 2px rgba(30,144,255,.30) !important;
            }

            /* ───────── ボタン共通 ───────── */
            div.button-row button{
                width:100% !important;
                padding:.75rem 0 !important;
                font-size:1rem !important;
                border-radius:8px !important;
                transition:background .25s ease,box-shadow .25s ease;
                outline:none !important;        /* 赤いフォーカスリング除去 */
            }

            /* ★ 押下時（active / focus）には一切エフェクトを付けない ★ */
            div.button-row button:focus,
            div.button-row button:focus-visible,
            div.button-row button:active{
                box-shadow:none !important;
            }

            /* ── プライマリ（作成） ── */
            div.button-row button:first-of-type{
                background:#1E90FF !important;
                color:#fff !important;
                border:none !important;
            }
            div.button-row button:first-of-type:hover:enabled{
                background:#0f75d1 !important;
                box-shadow:0 0 0 2px rgba(30,144,255,.30) !important;
            }
            div.button-row button:first-of-type:disabled{
                background:#c4d9f5 !important;
                color:#f5f5f5 !important;
            }

            /* ── アウトライン（← 戻る） ── */
            div.button-row button:last-of-type{
                background:transparent !important;
                color:#1E90FF !important;
                border:2px solid #1E90FF !important;
            }
            div.button-row button:last-of-type:hover:enabled{
                background:#1E90FF14 !important;
                box-shadow:0 0 0 2px rgba(30,144,255,.30) !important;
            }

            /* ボタン行：横並び＆等幅 */
            div.button-row{
                display:flex;
                gap:1rem;
            }
            
                    /* ───────── 「Press Enter to submit form」を非表示 ───────── */
            div[data-testid="InputInstructions"]{display:none !important;}

            </style>
            """,
            unsafe_allow_html=True,
        )

        # ── 2) カード内フォーム ─────────────────────────────────────
        with st.form("create_room_form"):
            st.markdown("## 🔨 ルーム作成")
            user = st.text_input("", key="create_user", placeholder="ユーザー名を入力")
            room = st.text_input("", key="create_room", placeholder="ルーム名を入力")

            # ── ボタン行を横並びで配置 ──
            st.markdown('<div class="button-row">', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                create_clicked = st.form_submit_button("作成")
            with col2:
                back_clicked = st.form_submit_button("← 戻る")
            st.markdown('</div>', unsafe_allow_html=True)

        # ── 3) フォーム送信後の処理 ─────────────────────────────────
        if create_clicked:
            if not user or not room:
                st.warning("ユーザー名とルーム名の両方を入力してください。")
                st.stop()
            try:
                self.ctrl.connect_tcp()
                info = self.state.tcp.quick_create_room(user, room)
            except Exception as e:
                st.error(f"接続失敗: {e}")
                st.stop()
            self.ctrl.save_client_info(info, user, room)
            self.ctrl.connect_udp()
            self.ctrl.switch_page("chat")

        if back_clicked:
            self.ctrl.switch_page("home")

    
    def render_join(self):
        st.title("🚪 ルーム参加")
        user = st.text_input("👤 ユーザー名", key="join_user")
        if st.button("ルーム一覧取得", disabled=not user):
            try:
                self.ctrl.connect_tcp()
                rooms = self.state.tcp.list_rooms(user)
                self.state.rooms = rooms
            except Exception as e:
                st.error(f"取得失敗: {e}")
        if self.state.rooms:
            sel = st.selectbox("参加するルーム", self.state.rooms)
            if st.button("参加", disabled=not user or not sel):
                try:
                    info = self.state.tcp.register_room(user, sel)
                except Exception as e:
                    st.error(f"参加失敗: {e}")
                    return
                self.ctrl.save_client_info(info, user, sel)
                self.ctrl.connect_udp()
                self.ctrl.switch_page("chat")
        if st.button("← 戻る"):
            self.ctrl.switch_page("home")


    def render_chat(self):
        st_autorefresh(interval=2000, key="chat-refresh")
        st.markdown("""
        <style>
        /* チャットページでは通常フローに戻す -------------------------*/
        div.block-container {
            display: block !important;           /* flex を解除 */
            justify-content: flex-start !important;
            align-items: stretch !important;
            min-height: auto !important;         /* 100vh を元に戻す */
            /* デフォルトに近いパディングを復活 */
            padding: 1rem 2rem 1rem 2rem !important;
        }
        </style>
        """, unsafe_allow_html=True)

        udp = self.state.udp
        new = udp.fetch_messages()
        current_user = self.state.username

        for m in new:
            if not m.strip():
                continue
            if m == "exit!":
                # msg = "System: ⚠ ホストが退出しました。ルームは終了しました"
                # if msg not in self.state.messages:
                #     self.state.messages.append(msg)
                continue
            if m == "Timeout!":
                # タイムアウト通知は表示しない
                continue
            if m not in self.state.messages:
                self.state.messages.append(m)

        self.render_chat_ui(current_user)

        with st.form(key="chat-form", clear_on_submit=True):
            msg = st.text_input("", key="chat-input", placeholder="メッセージを入力")
            submitted = st.form_submit_button("送信")
            if submitted and msg:
                try:
                    udp.send(msg)
                except Exception as e:
                    st.error(f"送信失敗: {e}")

    def render_chat_ui(self, current_user):
        #-------------------------------------------------------------
        # カスタム CSS   （入力欄／ボタン／チャットレイアウトすべて）
        #-------------------------------------------------------------
        st.markdown("""
        <style>
        
        .room-header {
            font-size: 1.3rem;
            font-weight: 600;
            padding: 0.8rem 1.6rem;
            text-align: center;
            background: linear-gradient(135deg, #f7fbff, #eaf4ff);
            border-radius: 14px 14px 0 0;
            color: #334155;
            border-bottom: 1px solid #dbe5ef;
            margin: 0 auto 1rem auto;
            width: fit-content;
            box-shadow: 0 2px 6px rgba(0,0,0,0.04);
        }
        /*-----------------------------------------------------------
        ページ背景
        -----------------------------------------------------------*/
        body { background-color: #f0f8ff; }  /* AliceBlue */

        /*-----------------------------------------------------------
        テキスト入力欄
        -----------------------------------------------------------*/
        input[type="text"]{
            background: linear-gradient(to right,#f9fbfd,#f0f6ff);
            border: 2px solid #8ecae6;
            border-radius: 16px;
            padding: .75rem 1.2rem;
            font-size: 1.05rem;
            font-weight: 500;
            color:#333;
            box-shadow:0 3px 8px rgba(0,0,0,.06);
            transition:all .3s ease;
            outline:none !important;
        }
        input[type="text"]::placeholder{color:#9ab0c4;font-weight:400;}

        /* Hover / Focus */
        input[type="text"]:hover,
        input[type="text"]:focus,
        input[type="text"]:active{
            border:2px solid #219ebc !important;
            box-shadow:0 0 0 4px rgba(33,158,188,.25) !important;
            outline:none !important;
        }

        /*-----------------------------------------------------------
        ▼▼ ここが “赤い線” 完全除去ポイント ▼▼
        -----------------------------------------------------------*/
        /* ① Streamlit (Base Web) ラッパーに付く赤ボーダーを殺す */
        [data-baseweb="input"][aria-invalid="true"],
        [data-baseweb="input"][aria-invalid="true"]:hover,
        [data-baseweb="input"][aria-invalid="true"]:focus-within{
            border:2px solid #8ecae6 !important;
            box-shadow:none !important;
        }

        /* ② HTML5 バリデーションの :invalid もすべて殺す */
        input[type="text"]:required:invalid,
        input[type="text"]:invalid,
        input[type="text"]:focus:invalid{
            border:2px solid #8ecae6 !important;
            box-shadow:none !important;
            outline:none !important;
        }

        /* 自動補完の黄背景・赤線を除去 */
        input:-webkit-autofill,
        input:-webkit-autofill:focus,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:active{
            box-shadow:0 0 0 1000px #f9fbfd inset !important;
            border:2px solid #8ecae6 !important;
            -webkit-text-fill-color:#333 !important;
            transition:background-color 9999s ease-out,color 9999s ease-out;
        }

        /*-----------------------------------------------------------
        送信ボタン
        -----------------------------------------------------------*/
        button[kind="primary"]{
            background-color:#219ebc;
            color:#fff;
            border:none;
            border-radius:10px;
            padding:.55rem 1.4rem;
            font-size:1rem;
            font-weight:600;
            box-shadow:0 2px 5px rgba(0,0,0,.1);
            transition:background-color .3s ease,transform .1s ease;
        }
        button[kind="primary"]:hover{background-color:#197b9b;transform:translateY(-1px);}
        button[kind="primary"]:active{transform:scale(.98);}
        
        
        div[data-baseweb="input"],
        div[data-baseweb="input"]:hover,
        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="input"][aria-invalid="true"],
        div[data-baseweb="input"][aria-invalid="true"]:hover,
        div[data-baseweb="input"][aria-invalid="true"]:focus-within {
        box-shadow: none !important;
        border-color: transparent !important; /* border-colorも消去する */
        }
        </style>
        """, unsafe_allow_html=True)

        #-------------------------------------------------------------
        #  チャット UI の HTML / CSS
        #-------------------------------------------------------------
        chat_html = """
        <style>
        :root{
        --bg-page:#e0e0e0;
        --bubble-me-start:#a0d8f1;
        --bubble-me-end:#c9eafc;
        --bubble-other-start:#adebb4;
        --bubble-other-end:#d4f8dd;
        --bubble-system-start:#ffeab6;
        --bubble-system-end:#fff6d3;
        --text-primary:#1e2a38;
        --scrollbar-track:#e3e7eb;
        --scrollbar-thumb:#a4b0be;
        }
        /*-----------------------------------------------------------
        チャットラッパー  ※最大幅を設けて中央寄せ・白背景に
        -----------------------------------------------------------*/
        .chat-wrapper{
        width:100%;
        max-width:650px;
        height:750px;
        max-height:100%;
        overflow:hidden;
        display:flex;
        flex-direction:column;
        border-radius:20px;
        box-shadow:0 6px 24px rgba(0,0,0,.05);
        background:#fff;
        margin:0 auto;               /* ←中央寄せ */
        }
        .chat-box{
        flex:1;
        overflow-y:auto;
        padding:2em;
        display:flex;
        flex-direction:column;
        gap:1em;
        }
        .chat-box::-webkit-scrollbar{width:8px;}
        .chat-box::-webkit-scrollbar-track{background:var(--scrollbar-track);border-radius:4px;}
        .chat-box::-webkit-scrollbar-thumb{background:var(--scrollbar-thumb);border-radius:4px;}

        .wrap{display:flex;flex-direction:column;}
        .wrap.mine{align-items:flex-end;}
        .wrap.other{align-items:flex-start;}
        .wrap.system{align-items:center;}

        .name{
        font-size:.75em;font-weight:600;margin-bottom:.3em;color:var(--text-primary);
        }
        .msg{
        position:relative;padding:1em 1.5em;border-radius:18px;max-width:65%;
        color:var(--text-primary);font-size:1rem;line-height:1.5;
        box-shadow:0 3px 12px rgba(0,0,0,.05);
        animation:fadeIn .3s ease;word-break:break-word;
        }
        .wrap.mine .msg{
        background:linear-gradient(135deg,var(--bubble-me-start),var(--bubble-me-end));
        border-bottom-right-radius:4px;
        }
        .wrap.other .msg{
        background:linear-gradient(135deg,var(--bubble-other-start),var(--bubble-other-end));
        border-bottom-left-radius:4px;
        }
        .wrap.mine .msg::after{
        content:'';position:absolute;bottom:0;right:-6px;
        border-top:6px solid var(--bubble-me-end);border-left:6px solid transparent;
        }
        .wrap.other .msg::before{
        content:'';position:absolute;bottom:0;left:-6px;
        border-top:6px solid var(--bubble-other-end);border-right:6px solid transparent;
        content:none !important;   /* ← 疑似要素を無効化 */
        display:none !important;   /* ← 念のため描画自体も抑制 */
        }
        .wrap.system .msg{
        display:inline-flex;align-items:center;justify-content:center;gap:.5em;
        padding:.8em 1.4em;background:linear-gradient(135deg,var(--bubble-system-start),var(--bubble-system-end));
        color:#5a381e;border-radius:14px;font-weight:500;
        box-shadow:0 3px 14px rgba(0,0,0,.08);animation:popIn .4s ease-out;font-size:.95rem;
        }
        .wrap.system .msg::before{content:'🔔';font-size:1.2em;}

        @keyframes fadeIn{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:translateY(0);}}
        @keyframes popIn{0%{transform:scale(.7);opacity:0;}60%{transform:scale(1.05);opacity:1;}100%{transform:scale(1);}}

        /* mine 吹き出しの矢印を削除する例（不要ならコメントアウト可） */
        .wrap.mine .msg::after{
        content:none !important;
        display:none !important;
        }
        </style>

        <div class="chat-wrapper">
        <div class="chat-box" id="chat-box">
        """

        # ---------------- メッセージ描画 ----------------
        for msg in self.state.messages[-300:]:
            if ":" in msg:
                sender, content = msg.split(":", 1)
                sender, content = sender.strip(), content.strip()
                if sender == "System":
                    chat_html += f"""
            <div class="wrap system"><div class="msg">{content}</div></div>
                    """
                else:
                    cls = "mine" if sender == current_user else "other"
                    chat_html += f"""
            <div class="wrap {cls}">
            <div class="name">{sender}</div>
            <div class="msg">{content}</div>
            </div>
                    """
            elif msg.strip():
                chat_html += f"""
            <div class="wrap system"><div class="msg">{msg}</div></div>
                """

        chat_html += """
            <div id="bottom-anchor"></div>
        </div> <!-- /.chat-box -->
        </div>   <!-- /.chat-wrapper -->

        <script>
        const chatBox = document.getElementById('chat-box');
        const anchor  = document.getElementById('bottom-anchor');
        
        /* ❶ 1 フレーム待ってから最下部へ */
        requestAnimationFrame(() => {
          anchor.scrollIntoView({block:'end'});   // ← container 内だけがスクロールされる
          /* あるいは chatBox.scrollTop = chatBox.scrollHeight; でも OK */
        });
        
        /* ❷ 初回ロードだけスクロールさせたくない場合 */
        if (sessionStorage.getItem('firstLoadDone')) {
          anchor.scrollIntoView({block:'end'});
        } else {
          sessionStorage.setItem('firstLoadDone', '1');
        }
        </script>
        
        """

        #  余白を含めて見やすいサイズに
        components.html(chat_html, height=780, scrolling=False)


# =====================
# 起動処理
# =====================
ctrl = ChatAppController()
ui = ChatPageRenderer(ctrl)

pages = {
    "home": ui.render_home,
    "create": ui.render_create,
    "join": ui.render_join,
    "chat": ui.render_chat,
}

pages.get(ctrl.state.page, ui.render_home)()
