FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render uses the PORT env var
ENV PORT=8080

CMD ["python", "main.py", "--mode", "worker"]
