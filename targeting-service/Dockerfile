FROM python:3.12-alpine AS builder
WORKDIR /src
RUN apk add --no-cache build-base postgresql-dev
COPY requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-alpine
WORKDIR /app
RUN apk add --no-cache postgresql-libs
COPY --from=builder /install /usr/local
COPY . .

ENV PORT=8003

EXPOSE 8003

CMD ["python", "app.py"]

