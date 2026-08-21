# syntax=docker/dockerfile:1.26
# --- compile ----------------------------------------------------------------
# Alpine's Rust is musl-native, so the release binary is static and the runtime
# stage needs no libc at all. TLS roots come from webpki-roots, compiled in by
# ureq, so it needs no ca-certificates bundle either.
FROM rust:1.97-alpine AS builder

RUN apk add --no-cache musl-dev

WORKDIR /src

# Dependencies first, against a stub source: this layer is keyed on the
# manifests alone, so editing the real code does not recompile the whole tree.
COPY rust-toolchain.toml Cargo.toml Cargo.lock ./
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    mkdir -p src \
    && echo 'fn main() {}' > src/main.rs \
    && echo '' > src/lib.rs \
    && cargo build --release --locked \
    && rm -rf src

COPY src ./src
COPY templates ./templates
COPY config.yaml ./config.yaml

# Cargo keys freshness on mtime, and the stub artifacts above are newer than
# the source COPY just laid down, so make the real ones unambiguously newer.
RUN --mount=type=cache,target=/usr/local/cargo/registry \
    touch src/*.rs \
    && cargo build --release --locked --bin compote3 \
    && strip target/release/compote3

# --- runtime ----------------------------------------------------------------
# Nothing but the binary and a default config: no shell, no package manager,
# no interpreter. The dashboard HTML is compiled into the binary.
FROM scratch AS runtime

COPY --from=builder /src/target/release/compote3 /usr/local/bin/compote3
COPY --from=builder /src/config.yaml /root/config.yaml

WORKDIR /root
EXPOSE 9000

ENTRYPOINT ["/usr/local/bin/compote3"]
