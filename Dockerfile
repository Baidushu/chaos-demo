FROM python:3.9

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y iproute2 stress-ng

COPY app.py .
COPY app ./app
COPY chaos_service ./chaos_service

# 多 worker：订单在 Redis `order:{id}`，进程间共享；gunicorn worker 数可按 CPU 调。
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
