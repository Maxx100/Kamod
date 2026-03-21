FROM python:3.11-slim

WORKDIR /app

COPY services/website/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core ./core

COPY services/website .

RUN mkdir -p /app/logs

CMD ["python", "main.py"]