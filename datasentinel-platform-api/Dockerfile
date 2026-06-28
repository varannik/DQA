FROM python:3.11-slim
WORKDIR /app
COPY datasentinel-platform-api/requirements.txt ./
COPY datasentinel-contracts /datasentinel-contracts
RUN pip install --no-cache-dir /datasentinel-contracts && pip install --no-cache-dir -r requirements.txt
COPY datasentinel-platform-api/app ./app
COPY datasentinel-platform-api/migrations ./migrations
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
