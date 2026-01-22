# syntax=docker/dockerfile:1.21
# Build stage
FROM golang:1.25-alpine AS builder

WORKDIR /app

# Copy go mod files
COPY go.mod ./
COPY go.sum* ./

# Download dependencies (with cache mount for speed)
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

# Copy source code
COPY . .

# Build the application (with cache mount for build cache)
RUN --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux go build -installsuffix cgo -o compote3 .

# Runtime stage
FROM alpine:latest

RUN apk --no-cache add ca-certificates

WORKDIR /root/

# Copy the binary from builder
COPY --from=builder /app/compote3 .
COPY --from=builder /app/templates ./templates
COPY --from=builder /app/config.yaml ./config.yaml

# Expose port
EXPOSE 9000

# Run the application
CMD ["./compote3"]

