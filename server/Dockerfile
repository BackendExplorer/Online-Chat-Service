FROM python:3.11-slim

# sqlite3コマンドラインツールをインストール
RUN apt-get update && apt-get install -y sqlite3

# 必要パッケージだけをインストール
RUN pip install pycryptodome

# 作業ディレクトリ
WORKDIR /app
# カレントディレクトリの全ファイルをコピー (server.py, sqlite_logger.py)
COPY . .

# TCP 9001 と UDP 9002 を公開
EXPOSE 9001/tcp
EXPOSE 9002/udp

CMD ["python", "server.py"]