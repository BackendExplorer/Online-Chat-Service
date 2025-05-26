# ------------------------------------------------------------
# Secure-Chat  サーバ用 Dockerfile
# ------------------------------------------------------------
FROM python:3.11-slim

# 必要パッケージだけをインストール
RUN pip install pycryptodome

# 作業ディレクトリ
WORKDIR /app
COPY server.py .

# TCP 9001 と UDP 9002 を公開
EXPOSE 9001/tcp
EXPOSE 9002/udp

CMD ["python", "server.py"]
