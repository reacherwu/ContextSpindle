# Multi-stage ultra-compact build for DiffHound MCP Server
FROM rust:1.80-alpine AS builder

RUN apk add --no-cache musl-dev

WORKDIR /app
COPY . .

# Build standalone diffhound binary
RUN cargo build --release --bin diffhound

# Minimal runtime stage
FROM alpine:3.20

RUN apk add --no-cache ca-certificates git

WORKDIR /root
COPY --from=builder /app/target/release/diffhound /usr/local/bin/diffhound

# Initialize local memory manifold
RUN diffhound init /root

# Default entrypoint runs the stdio MCP server for Glama introspection
ENTRYPOINT ["diffhound", "mcp"]
