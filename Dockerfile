FROM python:3.11-slim
WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PORT=8080 PYTHONUNBUFFERED=1
CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]