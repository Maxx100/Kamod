FROM python:3.11-slim

WORKDIR /app

COPY services/website/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core ./core
RUN pip install --no-cache-dir -r core/requirements.txt

COPY services/website .

RUN mkdir -p /app/logs

CMD ["python", "main.py"]