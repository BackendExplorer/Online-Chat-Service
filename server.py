import secrets
import socket
import threading
import time



class TCPServer:

    HEADER_MAX_BYTE = 32    # ヘッダーサイズ（バイト）
    TOKEN_MAX_BYTE = 255    # クライアントトークンの最大バイト数

    room_tokens = {}  # {room_name : [token, token, ...]}
    client_data = {}       # {token : [client_address, room_name, username, is_host, last_active_time]}

    def __init__(self, server_address, server_port):
        self.server_address = server_address
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.server_address, self.server_port))
        self.sock.listen()

    def accept_tcp_connections(self):
        while True:
            conn, addr = self.sock.accept()
            try:
                self.handle_client_request(conn, addr)
            except Exception:
                pass

    def handle_client_request(self, connection, client_address):
        data = connection.recv(4096)
        room_name_size, operation, state, payload_size, room_name, payload = self.decode_message(data)
        token = self.register_client(client_address, room_name, payload, operation)

        if operation == 1:
            self.create_room(connection, room_name, token)    
        elif operation == 2:
            self.join_room(connection, token)

    def decode_message(self, data):
        header = data[:self.HEADER_MAX_BYTE]
        room_name_size, operation, state = header[:3]
        payload_size = int.from_bytes(header[3:], "big")

        body = data[self.HEADER_MAX_BYTE:]
        room_name = body[:room_name_size].decode()
        payload   = body[room_name_size:room_name_size + payload_size].decode()
        
        return room_name_size, operation, state, payload_size, room_name, payload

    def register_client(self, client_address, room_name, payload, operation):
        token = secrets.token_bytes(self.TOKEN_MAX_BYTE)
        self.client_data[token] = [
            client_address,
            room_name,
            payload,
            1 if operation == 1 else 0,
            time.time(),
        ]
        return token

    def create_room(self, connection, room_name, token):
        connection.send(token)
        self.room_tokens[room_name] = [token]

    def join_room(self, connection, token):
        connection.send(str(list(self.room_tokens.keys())).encode())
        room_name = connection.recv(4096).decode()
        self.room_tokens[room_name].append(token)
        self.client_data[token][1] = room_name
        connection.send(token)



class UDPServer:

    def __init__(self, server_address, server_port):
        self.server_address    = server_address
        self.server_port       = server_port
        self.room_tokens  = TCPServer.room_tokens
        self.client_data       = TCPServer.client_data
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.server_address, self.server_port))

    def start_udp_server(self):
        thread_main     = threading.Thread(target=self.handle_messages)
        thread_tracking = threading.Thread(target=self.remove_inactive_clients)
        
        thread_main.start()
        thread_tracking.start()
        
        thread_main.join()
        thread_tracking.join()

    def handle_messages(self):
        while True:
            data, client_address = self.sock.recvfrom(4096)
            room_name, token, message = self.decode_message(data)
            
            self.client_data[token][0]  = client_address
            self.client_data[token][-1] = time.time()
            
            self.broadcast_to_room(room_name, message)

    def decode_message(self, data):
        header = data[:2]
        room_name_size, token_size = header[:2]
        
        body = data[2:]
        room_name = body[:room_name_size].decode("utf-8")
        token     = body[room_name_size:room_name_size + token_size]
        message   = body[room_name_size + token_size:].decode("utf-8")
        
        return room_name, token, message

    def broadcast_to_room(self, room_name, message):
        encoded_message = message.encode()

        for token in self.room_tokens.get(room_name, []):
            client_info = self.client_data.get(token)
            if client_info and client_info[0]:
                try:
                    self.sock.sendto(encoded_message, client_info[0])
                except Exception:
                    pass
            
    def remove_inactive_clients(self):
        while True:
            cutoff = time.time() - 100
            for token, info in list(self.client_data.items()):
                if info[-1] < cutoff:
                    try:
                        self.disconnect_inactive_client(token, info)
                    except Exception:
                        pass
            time.sleep(60)
    
    def disconnect_inactive_client(self, client_token, client_info):
        client_address, room_id, username, is_host = client_info[:4]
        members = self.room_tokens[room_id]
        
        if is_host == 1:
            self.broadcast_to_room(room_id, f"System: ホストの{username}がルームを退出したので、ルームは終了します")
            self.broadcast_to_room(room_id, "exit!")
            del self.room_tokens[room_id]
        
        else:
            self.broadcast_to_room(room_id, f"System: {username}がタイムアウトにより退出しました。")
            self.sock.sendto("Timeout!".encode(), client_address)
            members.remove(client_token)
            del self.client_data[client_token]
    

if __name__ == "__main__":

    server_address  = '0.0.0.0'
    tcp_server_port = 9001
    udp_server_port = 9002

    tcp_server = TCPServer(server_address, tcp_server_port)
    udp_server = UDPServer(server_address, udp_server_port)

    thread_tcp = threading.Thread(target=tcp_server.accept_tcp_connections)
    thread_udp = threading.Thread(target=udp_server.start_udp_server)

    thread_tcp.start()
    thread_udp.start()

    thread_tcp.join()
    thread_udp.join()
