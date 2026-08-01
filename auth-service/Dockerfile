FROM golang:1.21-alpine AS builder
WORKDIR /src
RUN apk add --no-cache ca-certificates
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /out/auth-service .

FROM alpine:3.20
WORKDIR /app
RUN apk add --no-cache ca-certificates tzdata \
    && addgroup -S appgroup \
    && adduser -S appuser -G appgroup
COPY --from=builder /out/auth-service /usr/local/bin/auth-service
EXPOSE 8001
USER appuser

ENTRYPOINT ["/usr/local/bin/auth-service"]
