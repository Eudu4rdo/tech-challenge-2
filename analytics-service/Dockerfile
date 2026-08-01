FROM python:3.12-alpine AS builder
WORKDIR /src
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-alpine
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

ENV PORT=8005

EXPOSE 8005

CMD ["python", "app.py"]
