# ============================================================
# test_crypto_encryption.py
#   CryptoUtil / Encryption / EncryptedSocket のユニットテスト
#   pytest で実行することを想定
#   $ pytest -q test_crypto_encryption.py
# ============================================================
import socket
import secrets

import pytest
from Crypto.PublicKey import RSA

import client  # テスト対象のモジュール（client.py）

CryptoUtil = client.CryptoUtil
Encryption = client.Encryption
EncryptedSocket = client.EncryptedSocket


# ------------------------------------------------------------
# AES 関連テスト
# ------------------------------------------------------------

def test_aes_roundtrip():
    """同じ key / iv で暗号化 → 復号化すれば元に戻る。"""
    key = secrets.token_bytes(16)
    iv  = secrets.token_bytes(16)
    data = b"Hello, AES!"

    ct = CryptoUtil.aes_encrypt(data, key, iv)
    assert ct != data, "暗号文が平文と異なること"

    pt = CryptoUtil.aes_decrypt(ct, key, iv)
    assert pt == data


def test_aes_iv_variation():
    """IV が違えば同じ入力でも暗号文が変わる。"""
    key = secrets.token_bytes(16)
    data = b"Identical input"

    iv1 = secrets.token_bytes(16)
    iv2 = secrets.token_bytes(16)

    ct1 = CryptoUtil.aes_encrypt(data, key, iv1)
    ct2 = CryptoUtil.aes_encrypt(data, key, iv2)

    assert ct1 != ct2  # CFB モードでは IV が異なれば暗号文も異なる


# ------------------------------------------------------------
# RSA 関連テスト
# ------------------------------------------------------------

def test_rsa_roundtrip():
    """RSA で暗号化 → 復号化すれば元データに戻る。"""
    priv = RSA.generate(2048)
    pub  = priv.publickey()
    data = b"Hello, RSA!"

    ct = CryptoUtil.rsa_encrypt(data, pub)
    pt = CryptoUtil.rsa_decrypt(ct, priv)

    assert pt == data


# ------------------------------------------------------------
# Encryption クラス / 対向鍵交換テスト
# ------------------------------------------------------------

def test_encrypt_symmetric_key_roundtrip():
    """encrypt_symmetric_key で包んだ AES key+iv が対向側で復号できる。"""
    alice = Encryption()
    bob   = Encryption()

    # Alice が Bob の公開鍵で暗号化して送る想定
    alice.load_peer_public_key(bob.get_public_key_bytes())

    aes_key = secrets.token_bytes(16)
    iv      = secrets.token_bytes(16)

    wrapped = alice.encrypt_symmetric_key(aes_key, iv)
    unwrapped = CryptoUtil.rsa_decrypt(wrapped, bob.private_key)

    assert unwrapped == aes_key + iv


# ------------------------------------------------------------
# EncryptedSocket テスト
# ------------------------------------------------------------

def test_encrypted_socket_send_recv():
    """EncryptedSocket 経由で送ったメッセージが対向で復号できる。"""
    parent_sock, child_sock = socket.socketpair()

    key = secrets.token_bytes(16)
    iv  = secrets.token_bytes(16)

    sender   = EncryptedSocket(parent_sock, key, iv)
    receiver = EncryptedSocket(child_sock, key, iv)

    plaintext = b"Secret message over local socket"

    sender.sendall(plaintext)
    received = receiver.recv()

    assert received == plaintext

    sender.close()
    receiver.close()
