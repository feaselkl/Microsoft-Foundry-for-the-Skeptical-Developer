FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py features.json ./

# Container Apps sets PORT; default matches for local runs.
ENV PORT=8000
EXPOSE 8000

CMD ["python", "server.py"]
