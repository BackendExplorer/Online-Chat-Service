# 🌐 Online Chat Service 💬  

<br>

### 独自プロトコル・暗号通信・マルチスレッド・ソケット通信によるグループチャットアプリ

### システム設計から実装、GitHub Actions × Docker による自動デプロイ、Qittaでの発信まで

<br>

## 🖥 デモ

<br>

### 2人のユーザーが、ルームを作成してチャットをするデモ動画

<br>

https://github.com/user-attachments/assets/d55b6c0e-ad3e-4e3b-8296-aea1a0623e5c
  
<br>


## **📝 サービス紹介と導入ガイド**



- [サービスの特徴・開発の目的](#サービスの特徴・開発の目的)

- [セットアップ手順](#セットアップ手順)

- [基本的な使い方](#基本的な使い方)

<br>

## **🛠️ 技術構成**



- [システム全体の構成図](#システム全体の構成図)

- [使用技術](#使用技術)

- [クラス構成 と モジュール設計](#クラス構成とモジュール設計)



<br>

## **💡 開発の振り返りと展望**



- [設計上のこだわり](#設計上のこだわり)

- [苦労した点](#苦労した点)

- [追加予定の機能](#追加予定の機能)

<br>

## **📚 参考情報・ライセンス**



- [Qiitaでの発信 : 開発ストーリー](#qiita-seisaku-katei-no-kaisetsu-ki)

- [参考文献](#参考文献)

- [ライセンス情報](#ライセンス情報)

<br>

---

## <a id="サービスの特徴・開発の目的"></a> 📝 サービスの特徴・開発の目的

<br>

###  サービスの全体像

- このプロジェクトは、**グループチャットができるサービス**です。

- ホストユーザがチャットルームを作成し、ゲストユーザが入室することでグループチャットができます。


<br>

###  できること

<div style="height:8px;"></div>

- **ルーム作成・参加**  

  ホストが新規ルームを作成、ゲストは既存ルームに参加

- **同時接続**
  
  マルチスレッドによって、複数のルームで複数のユーザが同時にチャット可能

- **自動退出**  

  5分間操作がないユーザーは自動的にルームから退出


<br>


###  作成のきっかけ

<div style="height:8px;"></div>

1. **課題意識**

     ライブラリに頼らずに、ネットワーク通信や暗号技術を自力で実装することで理解を深めるため

2. **解決アプローチ**

     `TCP/UDP通信`、`RSA＋AES暗号`、`独自プロトコル`、`マルチスレッド`によってチャット機能を自力で構築

3. **得られた学び**

      通信・暗号・並列処理を含むシステム設計と実装や、`GitHub Actions`と`Docker`による自動デプロイの経験

<br>

---

## <a id="セットアップ手順"></a> 🚀 セットアップ手順

<br>

### 1. 前提条件

以下を事前にインストールしてください

- [Python 3.8以上](https://www.python.org/downloads/)

- [Git](https://git-scm.com/)

- [PyCryptodome](https://www.pycryptodome.org/)
  
<br>

### 2. リポジトリのクローン

以下のコマンドをターミナルで実行します

```bash
git clone https://github.com/yourusername/your-repo-name.git
```
```bash
cd your-repo-name
```

<br>

---

## <a id="基本的な使い方"></a>🧑‍💻 基本的な使い方

<br>

### 1. サーバー起動

ターミナルを開いて、以下のコマンドでサーバを起動します。

```bash
python3 server.py
```
<img width="618" alt="スクリーンショット 2025-05-06 13 04 39" src="https://github.com/user-attachments/assets/1c9462cc-662c-4196-ad89-158c1c2f0ebc" />


<br><br>


### 2. クライアント起動

別のターミナルを開き、以下のコマンドでクライアントを起動します。

```bash
python3 client.py
```
以下のように複数のクライアントを起動することで、ユーザー同士がチャットのやり取りができます

<br>

| ホスト | ゲスト |
|:-------:|:--------:|
|<br><img src="https://github.com/user-attachments/assets/d97033da-9315-41dc-996e-1c487b4581de" width="100%" /> |<br><img src="https://github.com/user-attachments/assets/523790f8-1813-44ea-a0e9-0a5922b1bc91" width="100%" /> |

<br>


### 3. ユーザーの操作手順

```mermaid
flowchart TD
%%─── ノード定義 ───
Start([スタート])
選択["ユーザー名を入力"]
ルーム名入力[ルーム名を入力]
パスワード設定[パスワードを設定]
ルーム一覧[ルーム一覧から選択]
パスワード入力[パスワードを入力]
チャット中[チャット中]
自動退出[自動退出]
End([終了])

%%─── フロー定義 ───
Start --> 選択
選択 -- 作成 --> ルーム名入力 --> パスワード設定 --> チャット中
選択 -- 参加 --> ルーム一覧 --> パスワード入力 --> チャット中
チャット中 -->|5分間無操作| 自動退出 --> End
```

<br>

---


<div style="font-size:120%; line-height:1.6;">
  
## <a id="システム全体の構成図"></a>🔄 システム全体の構成図

```mermaid
sequenceDiagram
    autonumber
    participant Dev  as 開発者（Dev）
    participant GH   as CI/CD（GitHub Actions）
    participant EC2  as サーバー（EC2・Docker）
    participant CLI  as クライアント（ローカル）

    Dev ->> GH: コードを push
    GH ->> GH: ビルド・テスト (CI)
    GH ->> EC2: デプロイ（SSH + Docker Compose）
    EC2 ->> EC2: サーバ起動（ポート 9001 / 9002）

    CLI ->> CLI: Streamlit クライアント起動
    CLI ->> EC2: TCP 接続
    EC2 -->> CLI: トークン & ルーム応答
    CLI ->> EC2: UDP 通信開始
    EC2 -->> CLI: メッセージブロードキャスト

    note right of EC2: Docker上で常時稼働（ルーム管理・タイムアウト監視）
    note right of GH: GitHubリポジトリ更新時に自動CI/CD

```
<img width="792" alt="スクリーンショット 2025-05-01 2 00 56" src="https://github.com/user-attachments/assets/932fc12d-0a3c-42d2-8afa-e66f6eb2328e" />
<br>

---


## <a id="使用技術"></a>🧰 使用技術

<br>

### 1. 技術選定の理由

- **`Python`**

  豊富な標準ライブラリと高い可読性によって、複雑なシステムを効率的に実装するため

- **`TCPソケット`**

  ルーム参加・ユーザー認証など、確実なデータ転送が必要な処理に利用するため

- **`UDPソケット`**

  チャットメッセージ送信などリアルタイム性を重視する通信に利用するため

- **`ハイブリッド暗号方式`**

  大量のクライアントがサーバに接続したとき、安全性を確保しつつ通信効率を維持するため

- **`マルチスレッド`**

  クライアントごとの並行処理を軽量に行うため

- **`Streamlit`**

  Pythonのみで手軽にWeb UIを構築できるため、開発効率を重視して採用


<br>

### 2.  技術スタックと 開発環境 の全体像

<br>

| カテゴリ       | 採用技術 と 使用ツール                                                                                     　　|
|----------------|----------------------------------------------------------------------------------------------------------------------|
| 開発言語       | ![Python](https://img.shields.io/badge/Python-3.13.2-blue) <br>標準ライブラリ使用：`socket`, `threading`, `logging`, `time`, `sys` |
| 通信技術       | ![TCP](https://img.shields.io/badge/Protocol-TCP-blue) ![UDP](https://img.shields.io/badge/Protocol-UDP-blue) <br>独自プロトコルTCRP（Talk Chat Room Protocol）を用いた通信設計 |
| 暗号技術       | ![PyCryptodome](https://img.shields.io/badge/Encryption-PyCryptodome-blue) <br>ハイブリッド暗号方式 (RSA＋AES) で通信
| 並列処理       | ![Threading](https://img.shields.io/badge/Concurrency-Threading-yellow) <br>マルチスレッドによる並列処理                      |
| UIフレームワーク | ![Streamlit](https://img.shields.io/badge/UI-Streamlit-red) <br>Webベースのインターフェースを簡易に構築 |
| 開発環境       | ![macOS](https://img.shields.io/badge/OS-macOS-lightgrey)&nbsp;&nbsp;&nbsp;&nbsp;![VSCode](https://img.shields.io/badge/Editor-VSCode-blue) |
| バージョン管理 | ![Git](https://img.shields.io/badge/VersionControl-Git-orange)&nbsp;&nbsp;&nbsp;&nbsp;![GitHub](https://img.shields.io/badge/Repo-GitHub-black) |
| 描画ツール     | ![Mermaid](https://img.shields.io/badge/Diagram-Mermaid-green)&nbsp;&nbsp;&nbsp;&nbsp;![LaTeX](https://img.shields.io/badge/Doc-LaTeX-9cf) |


<br>

---

## <a id="クラス構成とモジュール設計"></a>📌 クラス構成 と モジュール設計

<br>

### <a id="server.py のクラス図"></a> [サーバプログラム](https://github.com/BackendExplorer/Online-Chat-Service/blob/main/server.py) のクラス図

<br>

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
<br>


### <a id="client.py のクラス図"></a> [クライアント](https://github.com/BackendExplorer/Online-Chat-Service/blob/main/client.py) のモジュール設計

<br>


```mermaid
graph TD

%% スタイル定義
classDef ui fill:#fff8e1,stroke:#f9a825,stroke-width:2px
classDef application fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
classDef infra fill:#fce4ec,stroke:#c2185b,stroke-width:2px
classDef packet fill:#e3f2fd,stroke:#1976d2,stroke-width:2px

subgraph Entry Point
  main["main.py"]
  class main ui
end

subgraph Application
  app["TCPClient / UDPClient"]
  class app application
end

subgraph Crypto
  enc["Encryption"]
  sock["EncryptedSocket"]
  class enc,sock infra
end

subgraph Input Handling
  handler["InputHandler"]
  class handler packet
end

main --> app
app  --> enc
app  --> sock
app  --> handler



```
 
<br>

---
## <a id="設計上のこだわり"></a>⭐️ 設計上のこだわり

<br>

以下は、チャットルーム接続のために設計された **独自プロトコル TCRP**（Talk Chat Room Protocol） のパケット構造を表します。

<p align="center">
  <img width="413" alt="スクリーンショット 2025-03-27 1 41 43" src="https://github.com/user-attachments/assets/561e0e00-18ed-4df9-86a8-b3b9a0a25eed" />
  <img width="307" alt="スクリーンショット 2025-03-27 1 41 33" src="https://github.com/user-attachments/assets/3bc079fb-d453-4824-9d0a-a5edf4d1da06" />
</p>

<br>

---
## <a id="苦労した点"></a> ⚠️ 苦労した点

<br>

<ul>
  <li>
    <h3>TCP と UDP の並列化</h3>
    <p>制御系は信頼性重視のTCP、チャットは低遅延なUDPで分離。</p>
    <p><code>TCPServer</code>のクラス変数を<code>UDPServer</code>から参照することで、UDP側でもメンバー情報を正しく同期。</p>
  </li>
  <br>
  <li>
    <h3>アクティブでないユーザの検出 と 自動退出</h3>
    <p><code>last_active_time</code>を監視し、一定時間無操作のユーザーは自動退出。</p>
    <p>ホスト退出時は全員に通知を行い、ルーム自体を削除。</p>
  </li>
</ul>

<br>

---

## <a id="追加予定の機能"></a> 🔥 追加予定の機能

<br>

<ul>
  <li>
    <h3>GUI クライアントの実装（Electron）</h3>
    <p>Electron でクライアントを GUI 化し、ユーザー名・ルーム名・パスワードの入力やチャット表示、</p>
    <p>通知などを直感的に操作可能なウィンドウで提供します。</p>
    <p>サーバー（server.py）はそのまま使用し、クライアント（client.py）のみを Electron（Node.js）で置換。</p>
    
  </li>
</ul>

<br>


---
## <a id="qiita-seisaku-katei-no-kaisetsu-ki"></a>✏️ Qiitaでの発信 : 開発ストーリー

<br>

<ul>
  <li>
    <p>実装の背景や設計の工夫について、Qiita記事で詳しく解説しています。</p>
    <p>
      <a href="https://qiita.com/your-article-link" target="_blank" rel="noopener noreferrer">
        TCP・UDP×マルチスレッドで作る、ゼロからのチャットアプリ開発
      </a>
    </p>
  </li>
</ul>

<br>

---
## <a id="参考文献"></a>📗 参考文献

<br>

### 公式ドキュメント

- [Python socket - ソケット通信](https://docs.python.org/3/library/socket.html)

  TCP・UDP通信の基本構文と使い方を参照

- [Python threading - マルチスレッド](https://docs.python.org/3/library/threading.html)

  マルチスレッド処理（Thread の生成・開始・join）を実装するために参照

- [PyCryptodome — RSA (PKCS1_OAEP)](https://pycryptodome.readthedocs.io/en/latest/src/cipher/oaep.html)

  RSA公開鍵暗号の暗号化・復号化の仕組みを理解するために参照

- [PyCryptodome — AES (CFBモード)](https://www.pycryptodome.org/)

  共通鍵暗号方式によるデータの暗号化のために参照

- [Streamlit](https://docs.streamlit.io/)

  GUIを迅速に実装するために参照
  
<br>

### 参考にしたサイト

- [今更ながらソケット通信に入門する（Pythonによる実装例付き）](https://qiita.com/t_katsumura/items/a83431671a41d9b6358f)

- [python マルチスレッド マルチプロセス](https://qiita.com/Jungle-King/items/1d332a91647a3d996b82)

- [暗号化アルゴリズムの基本と実装をPythonで詳解](https://qiita.com/Leapcell/items/946a00fa060119f67444)

<br>

---

## <a id="ライセンス情報"></a>📜 ライセンス情報
このプロジェクトは [MIT License](https://opensource.org/licenses/MIT) のもとで公開されています。  

自由に利用、改変、再配布が可能ですが、利用の際は本ライセンス表記を保持してください。
