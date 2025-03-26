# 🌐 オンラインチャットサービス 💬  

**ユーザがルームを作成または参加して、グループチャットができるサービス**



## 🖥 デモ









## **📎 概要**
- [概要](#概要)
- [セットアップ](#セットアップ)
- [利用方法](#利用方法)

---

## **🛠 技術関連**
- [使用技術](#使用技術)
- [機能一覧](#機能一覧)
- [クラス図](#クラス図)
- [処理フロー (フローチャート)](#処理フロー)

---

## **📍開発のポイント**
- [こだわりのポイント](#こだわりのポイント)
- [苦労した点](#苦労した点)
- [さらに追加したい機能](#さらに追加したい機能)

---

## **📄 参考情報**
- [参考文献](#参考文献)

---

## 🖥 シミュレーション

## ▶️ 実行方法

## 🛠 使用技術

| カテゴリ | 技術スタック |
|----------|------------|
| 開発言語 | Python 3.13.2 |
| インフラ | Docker |
| その他 | Git, GitHub |


## ⚙ 機能一覧




```mermaid
flowchart TD
    Start([スタート])
    入力[ユーザー名を入力]
    選択[作成または参加を選択]

    作成1[「作成」を選択]
    ルーム名入力[ルーム名を入力]

    参加2[「参加」を選択]
    ルーム一覧[ルーム名を選択]

    チャット中[チャット中]
    End([終了])

    Start --> 入力 --> 選択

    選択 --> 作成1 --> ルーム名入力 --> チャット中
    選択 --> 参加2 --> ルーム一覧 --> チャット中

    チャット中 --> End

```





<div style="font-size:120%; line-height:1.6;">

## 🔀処理フロー

```mermaid
graph TD

%% スタイル定義
classDef server fill:#e3f2fd,stroke:#1e88e5,stroke-width:2px
classDef client fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
classDef messaging fill:#ede7f6,stroke:#6a1b9a,stroke-width:2px
classDef warning fill:#ffebee,stroke:#c62828,stroke-width:2px

%% サーバー起動
subgraph サーバー起動[サーバー起動処理]
    A1(メインスレッド)
    A2(TCPサーバースレッド)
    A3(UDPサーバースレッド)
    A4(クライアント接続受理)
    A5(クライアント登録)
    A6(メッセージスレッド)
    A7(監視スレッド)

    A1 -->|TCPサーバーを開始| A2
    A1 -->|UDPサーバーを開始| A3
    A2 -->|クライアント待機| A4
    A4 -->|ルーム作成/参加| A5
    A3 -->|メッセージ処理開始| A6
    A3 -->|非アクティブ監視開始| A7

    class A1,A2,A3,A4,A5,A6,A7 server
end

%% クライアント起動
subgraph クライアント起動[クライアント起動処理]
    B1(クライアント実行)
    B2(TCPクライアント開始)
    B3(接続成功)
    B4(ユーザー名入力)
    B5(ルーム作成または参加)
    B6(ルーム作成処理)
    B7(トークン受信)
    B8(ルーム参加処理)
    B9(トークン受信)
    B10(UDPクライアント開始)
    B11(チャット開始)

    B1 --> B2
    B2 --> B3
    B3 --> B4
    B4 --> B5
    B5 -->|ルーム作成| B6 --> B7
    B5 -->|ルーム参加| B8 --> B9
    B2 --> B10
    B10 --> B11

    class B1,B2,B3,B4,B5,B6,B7,B8,B9,B10,B11 client
end

%% サーバーメッセージ処理
subgraph サーバーメッセージ処理[メッセージ処理＆監視]
    C1(UDPサーバー)
    C2(クライアントからメッセージ受信)
    C3(ルームへブロードキャスト)
    C4(非アクティブチェック)
    C5(キック＆ルーム管理)

    C1 --> C2 --> C3
    C1 --> C4 -->|タイムアウト| C5

    class C1,C2,C3,C4,C5 messaging
end

%% クライアント終了
subgraph クライアント終了[クライアント終了処理]
    D1(クライアント)
    D2(UDPで'exit!'送信)
    D3(ソケットを閉じる)
    D4(タイムアウト通知受信)
    D5(ルーム削除または通知)

    D1 -->|ユーザーがexitと入力| D2 --> D3
    D1 -->|サーバーから通知| D4 --> D5

    class D1,D2,D3,D4,D5 warning
end

%% 流れ接続（全体の連携）
A1 --> B1
B1 --> C1
C1 --> D1
```

---

### 🖥️ サーバー起動処理


#### 🔹 1. メインスレッド

- TCPサーバーとUDPサーバーをそれぞれ別スレッドで起動します。
- 各サーバーの処理は独立しており、並行して動作します。

#### 🔹 2. TCPサーバースレッド

- `TCPServer` を起動し、クライアントからの接続を待ち受けます。
- クライアントは以下のどちらかの操作を選択：
  - `1️⃣ ルーム作成`
  - `2️⃣ 既存ルームに参加`
- 処理後、クライアントには **認証トークン** を発行します。

#### 🔹 3. UDPサーバースレッド

- `UDPServer` を起動し、以下の2つのスレッドを開始します：
  - 💬 **チャットメッセージの処理**
  - ⏱️ **非アクティブクライアントの監視**

---

### 🧑‍💻 クライアント起動処理

#### 🔹 1. TCPクライアント起動

- `TCPClient` を実行してサーバーへ接続。
- ユーザー名と操作（作成 or 参加）を入力します。

##### ✅ ルーム作成（操作コード: 1）
- ユーザーがルーム名を入力。
- サーバーがルームを作成し、トークンを返します。

##### ✅ ルーム参加（操作コード: 2）
- サーバーから利用可能なルーム一覧を取得。
- ユーザーがルーム名を指定して参加し、トークンを受け取ります。

#### 🔹 2. UDPクライアント起動

- `UDPClient` を使用して、UDP通信によるチャットを開始。
- メッセージの送受信をスレッドで並行処理します。

---

### 🔁 メッセージ処理 & クライアント監視（UDP）

#### 💬 メッセージ受信とブロードキャスト

- クライアントから受信したメッセージを解析：
  - ルーム名
  - クライアントトークン
  - メッセージ本文
- 同じルームの他クライアントに一斉送信（ブロードキャスト）。

#### ⏱️ 非アクティブクライアントの検出

- 最終アクティブ時刻を定期チェック（100秒未活動でキック）。
- ホストがタイムアウトした場合、ルームを削除し通知を送信。

---

### ❌ クライアント終了処理

#### 🔔 サーバーからの通知で切断

- タイムアウトにより「Timeout!」を受信。
- クライアントは「exit!」を受信し、自動で切断されます。

#### 👤 ユーザーによる手動退出

- ユーザーが `exit` を入力することで、UDP経由で退出を通知。
- サーバーは以下を実施：
  - ホスト ➡️ ルーム削除
  - ゲスト ➡️ ルームから除外

</div>

---



## 📦 クラス図と構成


このプロジェクトは、**TCP/UDP通信を用いたチャットシステム** を構成するクラス群で成り立っています。サーバーとクライアントでそれぞれの役割を持ち、以下のように分類されます。





### 📍 server.py のクラス図
```mermaid
%%{init: {'themeVariables': {'scale': 0.3}}}%%
classDiagram
direction LR

TCPServer -- UDPServer

class TCPServer {
    - HEADER_MAX_BYTE: int
    - TOKEN_MAX_BYTE: int
    - server_address: str
    - server_port: int
    - sock: socket
    - room_members_map: dict
    - clients_map: dict
    + __init__(server_address: str, server_port: int)
    + start_tcp_server(): None
    - accept_tcp_connections(): None
    - handle_client_request(connection: socket, client_address: tuple): None
    - decode_message(data: bytes): tuple
    - register_client(token: bytes, client_address: tuple, room_name: str, payload: str, operation: int): None
    - create_room(connection: socket, room_name: str, payload: str, token: bytes): None
    - join_room(connection: socket, room_name: str, payload: str, token: bytes): None
}

class UDPServer {
    - server_address: str
    - server_port: int
    - room_members_map: dict
    - clients_map: dict
    - sock: socket
    + __init__(server_address: str, server_port: int)
    + start_udp_server(): None
    - handle_messages(): None
    - decode_message(data: bytes): tuple
    - broadcast_message(room_name: str, message: str): None
    - remove_inactive_clients(): None
    - disconnect_inactive_client(client_token: bytes, client_info: list): None
}
```

### 📍 client.py のクラス図
```mermaid
%%{init: {'themeVariables': {'scale': 0.05}}}%%
classDiagram
direction LR

TCPClient -- UDPClient

class TCPClient {
    - server_address: str
    - server_port: int
    - sock: socket
    - client_info: dict
    + __init__(server_address: str, server_port: int)
    + start_tcp_client(): dict
    - connect_to_server(): None
    - input_user_name(): str
    - input_operation(): int
    - create_room(username: str): tuple
    - input_room_name(operation: int): str
    - create_packet(room_name: str, operation: int, state: int, payload: str): bytes
    - create_header(room_name: str, operation: int, state: int, payload: str): bytes
    - join_room(username: str): tuple
}

class UDPClient {
    - server_address: str
    - server_port: int
    - sock: socket
    - my_info: dict
    - my_token: bytes
    - room_name: str
    + __init__(server_address: str, server_port: int, my_info: dict)
    + start_udp_chat(): None
    - send_username(): None
    - send_message(): None
    - receive_message(): None
    - create_packet(message: bytes = b"" ): bytes
}
```

---



### 🖥 サーバープログラム
サーバー側のクラスは、**クライアントの接続管理、リクエスト処理、ルーム管理** などを担当します。

#### 🔹 TCPServer

TCP通信を介してクライアントからのリクエストを受け取り、適切な処理を実行します。

| 機能 | 説明 |
|------|------|
| クライアントからの接続受付 | `start_tcp_server()` |
| リクエスト処理 | `handle_client_request()` |
| クライアント情報の登録 | `register_client()` |
| ルームの作成 | `create_room()` |
| ルームへの参加 | `join_room()` |
| メッセージの解析 | `decode_message()` |

#### 🔹 UDPServer

UDP通信を介してメッセージを受信し、リレーまたは適切な処理を行います。

| 機能 | 説明 |
|------|------|
| クライアントからのメッセージ受信 | `handle_messages()` |
| メッセージの処理 | `decode_message()` |
| ルーム内のメンバーにメッセージをブロードキャスト | `broadcast_message()` |
| 非アクティブクライアントの削除 | `remove_inactive_clients()` |

---

### 💻 クライアントプログラム
クライアント側のクラスは、**サーバーとの通信、メッセージ送受信、ユーザーインターフェース** を担当します。

#### 🔹 TCPClient

TCP通信を介してサーバーにリクエストを送信し、レスポンスを受信します。

| 機能 | 説明 |
|------|------|
| サーバー接続 | `connect_to_server()` |
| ルームの作成 | `create_room()` |
| ルームへの参加 | `join_room()` |
| ルーム一覧の取得 | `input_room_name()` |
| パケット作成 | `create_packet()` |

#### 🔹 UDPClient

UDP通信を介してメッセージを送受信します。

| 機能 | 説明 |
|------|------|
| ユーザー名の送信 | `send_username()` |
| メッセージの送信 | `send_message()` |
| メッセージの受信 | `receive_message()` |
| パケット作成 | `create_packet()` |

---






## ✨ こだわりのポイント


<p align="center">
  <img width="274" alt="スクリーンショット 2025-03-27 0 59 06" src="https://github.com/user-attachments/assets/3eecddd4-3c9d-4f3b-9191-acda8daf3f55" />
  <img width="326" alt="スクリーンショット 2025-03-27 0 59 11" src="https://github.com/user-attachments/assets/5ddab0b9-26cb-4d54-bd45-42874e07c6c4" />
</p>


<img width="459" alt="スクリーンショット 2025-03-26 22 34 26" src="https://github.com/user-attachments/assets/cf3ca451-9e77-49a0-a9b6-f07ba7c1e4af" />




<img width="308" alt="スクリーンショット 2025-03-26 19 28 12" src="https://github.com/user-attachments/assets/d5aa2c4f-c502-404b-b373-96ff84ebea96" />


## ⚠️ 苦労した点

## 💡 さらに追加したい機能

## 📄 参考文献
<p align="center">
  <img src="https://github.com/user-attachments/assets/43766c52-7a68-4d7e-852d-18bf48755f78" width="100%">
</p>




