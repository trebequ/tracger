FROM python:3.11-slim

WORKDIR /app

# Ensure logs output immediately
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persistent storage volume for sqlite db
VOLUME ["/app/data"]

CMD ["python", "run.py"]
