# ------------------------------------------------------------
# Secure-Chat クライアント (Streamlit GUI) 用 Dockerfile
# ------------------------------------------------------------
FROM python:3.11-slim

RUN pip install \
        streamlit \
        streamlit-autorefresh \
        pycryptodome

WORKDIR /app
COPY client.py style.css .

EXPOSE 8501

CMD ["streamlit", "run", "client.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
