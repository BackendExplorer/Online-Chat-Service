import socket
import secrets
from Crypto.PublicKey import RSA
from Crypto.Cipher    import PKCS1_OAEP, AES


class RSAKeyExchange:
    def __init__(self):
        # ランダムな AES 鍵と IV（初期化ベクトル）を生成して保持
        self.aes_key = secrets.token_bytes(16)
        self.iv      = secrets.token_bytes(16)

    def encrypted_shared_secret(self, server_pub_key):
        # AES 鍵と IV を連結して共有秘密情報を作成
        shared = self.aes_key + self.iv
        # サーバの公開鍵を使って共有秘密情報を RSA で暗号化
        return PKCS1_OAEP.new(server_pub_key).encrypt(shared)


class AESCipherCFB:
    def __init__(self, key, iv):
        # AES 共通鍵と初期化ベクトル（IV）を保存
        self.key = key
        self.iv  = iv

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
        self.cipher   = cipher

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
        if not length_bytes:
            return b''
        ciphertext = self.recv_exact(int.from_bytes(length_bytes, 'big'))
        return self.cipher.decrypt(ciphertext)

    def close(self):
        self.raw_sock.close()
