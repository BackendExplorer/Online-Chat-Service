FROM python:3.11-slim

# 依存ライブラリ
RUN pip install \
        streamlit \
        streamlit-autorefresh \
        pycryptodome

# 作業ディレクトリ
WORKDIR /app

# プロジェクト一式をコピー
# （docker-compose で指定した build context = client/ の中身をすべて）
COPY . .

# Streamlit ポート
EXPOSE 8501

# エントリーポイント
# main.py から起動する構成
CMD ["streamlit", "run", "client.py", "--server.port=8501", "--server.address=0.0.0.0"]
