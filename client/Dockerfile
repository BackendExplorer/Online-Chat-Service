# ------------------------------------------------------------
# Secure-Chat クライアント (Streamlit GUI) 用 Dockerfile
# ------------------------------------------------------------
FROM python:3.11-slim

# 依存ライブラリ
RUN pip install --no-cache-dir \
        streamlit \
        streamlit-autorefresh \
        pycryptodome

# 作業ディレクトリ
WORKDIR /app
COPY client.py .

# style.css を使う場合は同じフォルダにコピー
COPY style.css ./

# Streamlit が外部から見えるように設定
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false

EXPOSE 8501

CMD ["streamlit", "run", "client.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
