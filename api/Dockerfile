# --- Build stage ---
FROM golang:1.23-alpine AS builder
WORKDIR /src

# Cache deps first
COPY go.mod go.sum ./
RUN go mod download

# Build the binary
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-s -w" \
    -o /out/server \
    ./cmd/server

# --- Final stage: distroless static (~5MB base, ~15MB final) ---
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=builder /out/server /server
EXPOSE 8080
ENTRYPOINT ["/server"]
