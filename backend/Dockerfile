FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY . .
# Cloud Run / Google Cloud passes the port in $PORT (8080 if it is not set)
EXPOSE 8080
CMD ["sh", "-c", "uvicorn planner.app:app --host 0.0.0.0 --port ${PORT:-8080}"]