# ContextSpindle MCP server image
FROM rust:1-alpine AS builder

RUN apk add --no-cache musl-dev

WORKDIR /app
COPY . .

RUN cargo build --release --bin contextspindle

# Minimal runtime stage
FROM alpine:3.20

RUN apk add --no-cache ca-certificates

WORKDIR /workspace
COPY --from=builder /app/target/release/contextspindle /usr/local/bin/contextspindle

VOLUME ["/workspace/.contextspindle", "/workspace/.continuum"]

ENTRYPOINT ["/bin/sh", "-c", "contextspindle init /workspace >/dev/null && exec contextspindle mcp"]
