import socket
import threading
import time
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

TOKEN_MAX_BYTE = 255         # クライアントトークンの最大バイト数
ROOM_NAME_MAX_BYTE = 2 ** 8    # ルーム名の最大バイト数
PAYLOAD_MAX_BYTE = 2 ** 29     # ペイロードの最大バイト数
HEADER_SIZE = 32             # ヘッダーサイズ（バイト）
USER_NAME_MAX_BYTE_SIZE = 255 # ユーザ名の最大バイト数

class TCPClient:
    
    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_info = {}

    # TCP クライアントを開始し、サーバーと通信を行う関数
    def start_tcp_client(self):
        # サーバーに接続
        self.connect_to_server()

        # ユーザー名と操作内容を入力
        username = self.input_user_name()
        operation = self.input_operation()

        # 操作に応じてルームを作成または参加
        if operation == 1:
            room_name, client_token = self.create_room(username)
        else:
            room_name, client_token = self.join_room(username)

        # クライアント情報を保存
        self.client_info = {client_token: [room_name, username]}
        
        # ソケットを閉じる
        self.sock.close()
        
        # クライアント情報を返す
        return self.client_info

    # サーバーに接続を試みる関数
    def connect_to_server(self):
        logging.info("=============================================")
        logging.info("          🚀 クライアント起動")
        logging.info("=============================================")
        logging.info("")
        logging.info(f"📡 {self.server_address}:{self.server_port} に接続を試みています...")
        logging.info("✅ サーバーへの接続に成功しました！")
        logging.info("")
        logging.info("---------------------------------------------")

        try:
            # サーバーへ接続
            self.sock.connect((self.server_address, self.server_port))
            logging.info("")

        except socket.error as err:
            logging.info("サーバーへの接続エラー: " + str(err))


    # ユーザ名 を入力する関数
    def input_user_name(self):
        while True:
            username = input("👤 ユーザー名を入力してください: ")
            if len(username) > PAYLOAD_MAX_BYTE:
                logging.info("2^29バイトを超えています。再度入力してください。")
            elif len(username) == 0:
                logging.info("ユーザー名を入力してください")
            else:
                return username
            
    # operation を入力する関数        
    def input_operation(self):
        while True:
            try:
                operation = int(input("🔹 1または2を入力してください (1: ルーム作成, 2: ルームに参加) -> "))
                if operation not in [1, 2]:
                    logging.info("1または2のみ入力可能です。再度入力してください。")
                else:
                    return operation
            except ValueError:
                logging.info("数字を入力してください。")
                
    # クライアントが新しいルームを作成する関数
    def create_room(self, username):
        # ユーザーにルーム名の入力を求める
        room_name = self.input_room_name(1)
        
        state = 0
        
        # ルーム作成のためのパケットを作成
        packet = self.create_packet(room_name, 1, state, username)
        
        # サーバーにパケットを送信
        self.sock.send(packet)
        
        # サーバーからクライアントトークンを受信
        client_token = self.sock.recv(TOKEN_MAX_BYTE)
        
        # ルーム名とクライアントトークンを返す
        return room_name, client_token

    # ユーザが ルーム名 を入力する関数
    def input_room_name(self, operation):
        while True:
            if operation == 1:
                room_name = input("🏠 作成するルーム名を入力してください -> ")
            else:
                room_name = input("参加したいルーム名を入力してください -> ")
            if len(room_name) > ROOM_NAME_MAX_BYTE:
                logging.info("2^8 バイトを超えています。再度入力してください。")
            elif len(room_name) == 0:
                logging.info("ルーム名を入力してください。")
            else:
                if operation == 1:
                    logging.info("\n---------------------------------------------\n")
                return room_name

    # ルーム名, operation, state, ペイロードを受け取って、パケットを返す関数
    def create_packet(self, room_name, operation, state, payload):
        # ヘッダーをバイト列として作成
        header = self.create_header(room_name, operation, state, payload) 
        
        # ルーム名とペイロードをバイト列としてエンコード
        room_name_bytes = room_name.encode("utf-8") 
        payload_bytes = payload.encode("utf-8") 
        
        # ヘッダーとボディを結合してパケットを作成
        packet = header + room_name_bytes + payload_bytes 
        
        return packet

    # ルーム名, operation, state, ペイロードを受け取って、ヘッダを返す関数
    def create_header(self, room_name, operation, state, payload):
        # ルーム名とペイロードのサイズを取得
        room_name_size = len(room_name) 
        payload_size = len(payload)  

        # ヘッダを作成
        header = (
            room_name_size.to_bytes(1, "big") +
            operation.to_bytes(1, "big") +
            state.to_bytes(1, "big") +
            payload_size.to_bytes(HEADER_SIZE - 3, "big")
        )
        
        return header

    # クライアントが既存のルームに参加する関数
    def join_room(self, username):
        # ルーム参加リクエストのパケットを作成
        packet = self.create_packet("", 2, 0, username)
        
        # サーバーにパケットを送信
        self.sock.send(packet)
        
        # サーバーから利用可能なルーム一覧を受信し、デコード
        room_list = self.sock.recv(4096).decode("utf-8")
        try:
            rooms = room_list.strip()[1:-1].split(',')
            rooms = [room.strip().strip("'").strip('"') for room in rooms if room.strip() != '']
        except:
            rooms = [room_list]
        logging.info("\n📜 利用可能なルーム一覧")
        logging.info("-----------------------------------")
        for idx, room in enumerate(rooms, start=1):
            logging.info(f"🏠 {idx}. {room}")
        logging.info("-----------------------------------\n")
        
        # ユーザーにルーム名の入力を求める
        room_name = self.input_room_name(2)
        
        # 入力されたルーム名をサーバーに送信
        self.sock.send(room_name.encode("utf-8"))
        
        # サーバーからクライアントトークンを受信
        client_token = self.sock.recv(TOKEN_MAX_BYTE)
        
        # ルーム名とクライアントのトークンを返す
        return room_name, client_token


class UDPClient:

    def __init__(self, server_address, server_port, my_info):
        self.server_address = server_address
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.my_info = my_info

        for token in self.my_info:
            self.my_token = token
            self.room_name = self.my_info[token][0]

    # UDPチャットを開始する関数
    def start_udp_chat(self):
        # ユーザー名をサーバーに送信
        self.send_username()
        logging.info(f"🔍 クライアントソケット情報: {self.sock.getsockname()}")
        logging.info("")
        logging.info("************ 💬 チャット開始 ************\n")
        
        # メッセージ送信用スレッドと受信用スレッドを作成
        thread_send = threading.Thread(target=self.send_message)
        thread_receive = threading.Thread(target=self.receive_message)
        
        # スレッドを開始
        thread_send.start()
        thread_receive.start()
        
        # スレッドの終了を待機
        thread_send.join()
        thread_receive.join()

    # ユーザー名をサーバーに送信する関数
    def send_username(self):
        # ユーザー情報を含むパケットを作成
        data = self.create_packet()
        
        # サーバーにパケットを送信
        self.sock.sendto(data, (self.server_address, self.server_port))
        logging.info(f"🔗 ルームに接続しました: {self.room_name}")

    # メッセージを送信する関数
    def send_message(self):
        while True:
            message = input("")
            print("\033[1A\033[1A")
            message_with_name = self.my_info[self.my_token][1] + ": " + message

            data = self.create_packet(message_with_name.encode())
            self.sock.sendto(data, (self.server_address, self.server_port))
            time.sleep(0.1)

    # メッセージを受信する関数
    def receive_message(self):
        while True:
            received_data = self.sock.recvfrom(4096)[0].decode("utf-8")

            if received_data in ["Timeout!", "exit!"]:
                logging.info(received_data)
                logging.info("*****************************************")
                self.sock.close()
                sys.exit()
            else:
                logging.info(received_data)

    # パケットを作成し、メッセージと必要な情報を含める関数
    def create_packet(self, message=b""):
        room_name_size = len(self.room_name).to_bytes(1, "big")
        token_size = len(self.my_token).to_bytes(1, "big")
        
        header = room_name_size + token_size
        
        return header + self.room_name.encode("utf-8") + self.my_token + message


if __name__ == "__main__":
    
    # サーバーのアドレスとポート番号を設定
    server_address = '0.0.0.0'
    tcp_server_port = 9001
    udp_server_port = 9002

    # TCP クライアント を作成
    tcp_client = TCPClient(server_address, tcp_server_port)
    my_info = tcp_client.start_tcp_client()

    # UDP クライアント を作成
    udp_client = UDPClient(server_address, udp_server_port, my_info)
    udp_client.start_udp_chat()
