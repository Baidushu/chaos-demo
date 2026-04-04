FROM python:3.9

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y iproute2 stress-ng

COPY app.py .

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
