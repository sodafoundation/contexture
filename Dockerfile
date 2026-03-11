FROM golang:1.21-alpine AS builder

WORKDIR /app

# Install dependencies required for Alpine
RUN apk add --no-cache git

# Copy go.mod and go.sum first to leverage Docker cache
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the OCS engine
RUN go build -o /app/bin/ocs ./pkg/ocs/main.go

# Run stage
FROM alpine:latest

WORKDIR /app

# Copy the built binary
COPY --from=builder /app/bin/ocs /app/ocs

# Expose port (default 8000)
EXPOSE 8000

# Run the binary
CMD ["/app/ocs"]
