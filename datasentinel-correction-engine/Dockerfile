FROM python:3.11-slim
WORKDIR /app
COPY datasentinel-correction-engine/requirements.txt ./
COPY datasentinel-contracts /datasentinel-contracts
RUN pip install --no-cache-dir /datasentinel-contracts && pip install --no-cache-dir -r requirements.txt
COPY datasentinel-correction-engine/app ./app
CMD ["python", "-m", "app.main"]
