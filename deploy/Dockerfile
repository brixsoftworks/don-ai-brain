FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Ollama
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://ollama.com/install.sh | sh

COPY . .

# Expose FastAPI and Ollama ports
EXPOSE 8000
EXPOSE 11434

CMD ["sh", "-c", "ollama serve & uvicorn server.app:app --host 0.0.0.0 --port 8000"]
