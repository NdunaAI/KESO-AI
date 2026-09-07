FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# python-oracledb runs in "thin" mode by default (pure Python, no Oracle
# Instant Client needed) for standard TCP/TCPS connections. If KESO's Oracle
# version or network setup requires "thick" mode, install Instant Client
# here and call oracledb.init_oracle_client() in server.py.
EXPOSE 8100
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8100"]
