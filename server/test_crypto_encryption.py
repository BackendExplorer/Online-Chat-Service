"""
test_crypto_encryption.py
=========================

サーバ実装中の暗号化ユーティリティのみを対象としたユニットテスト。
$ pytest -q test_crypto_encryption.py
"""

import secrets
import socket

import pytest
from Crypto.PublicKey import RSA

# テスト対象をインポート（ファイル名が server.py でなければ変更してください）
from server import CryptoUtil, Encryption, EncryptedSocket


# ------------------------------------------------------------
# CryptoUtil : AES / RSA ラウンドトリップ
# ------------------------------------------------------------
def test_aes_encrypt_decrypt_roundtrip():
    key = secrets.token_bytes(16)
    iv  = secrets.token_bytes(16)

    # 16 バイトを超えるデータでも OK か確認
    plaintext = (b"hello-world-" * 50)[:-2]      # 任意長 (≠16 の倍数)

    ciphertext = CryptoUtil.aes_encrypt(plaintext, key, iv)
    decrypted  = CryptoUtil.aes_decrypt(ciphertext, key, iv)

    assert decrypted == plaintext


def test_rsa_encrypt_decrypt_roundtrip():
    priv_key = RSA.generate(2048)
    pub_key  = priv_key.publickey()

    plaintext = secrets.token_bytes(64)

    ciphertext = CryptoUtil.rsa_encrypt(plaintext, pub_key)
    decrypted  = CryptoUtil.rsa_decrypt(ciphertext, priv_key)

    assert decrypted == plaintext


# ------------------------------------------------------------
# Encryption : 対称鍵(32B) 受信処理の検証
# ------------------------------------------------------------
def test_encryption_decrypt_symmetric_key_sets_attributes():
    # キー交換シミュレーション
    server_enc = Encryption()                    # 「受信側」想定
    client_enc = Encryption()                    # 「送信側」想定

    # 公開鍵を交換
    server_enc.load_peer_public_key(client_enc.get_public_key_bytes())
    client_enc.load_peer_public_key(server_enc.get_public_key_bytes())

    # クライアントが生成した AES キー + IV を暗号化してサーバへ送る想定
    aes_key = secrets.token_bytes(16)
    iv      = secrets.token_bytes(16)
    sym     = aes_key + iv                       # 32B

    encrypted_sym = CryptoUtil.rsa_encrypt(sym, server_enc.public_key)

    # サーバ側で復号 → 属性に反映されるか
    server_enc.decrypt_symmetric_key(encrypted_sym)

    assert server_enc.aes_key == aes_key
    assert server_enc.iv      == iv


# ------------------------------------------------------------
# EncryptedSocket : send / recv ラウンドトリップ
# ------------------------------------------------------------
def test_encrypted_socket_send_recv_roundtrip():
    key = secrets.token_bytes(16)
    iv  = secrets.token_bytes(16)

    # OS 依存しない Unix-domain socketpair で接続
    s1, s2 = socket.socketpair()
    try:
        es1 = EncryptedSocket(s1, key, iv)
        es2 = EncryptedSocket(s2, key, iv)

        # 1KiB + 3 バイトのデータ送信
        payload = b"A" * 1024 + b"XYZ"
        es1.sendall(payload)
        received = es2.recv()

        assert received == payload
    finally:
        s1.close()
        s2.close()
