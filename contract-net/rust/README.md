# Rust rewrite — offline executor milestone

The rewrite contains Python-compatible integer-seeded random generation, all
five exact task executors, calibration, and the recovered competition-first
bidding strategy. The executable accepts JSON lines on stdin and emits one
JSON response per line. It is currently an offline tool; WebSocket registration,
award handling, queue reservations, reconnect delivery, settlement routing, and
graceful shutdown still need implementation and local protocol integration tests.
The Python contractor remains the tournament entry point.

From the repository root (Rust with edition 2024 support and Python 3.12):

```sh
cargo build --release --locked --manifest-path contract-net/rust/Cargo.toml
python3.12 validation/check_rust.py
cargo test --locked --manifest-path contract-net/rust/Cargo.toml
cargo clippy --locked --manifest-path contract-net/rust/Cargo.toml --all-targets -- -D warnings
```

Example stdin line:

```json
{"task_type":"prime_count","params":{"lo":2,"hi":100},"timeout_ms":1000}
```

Response: `{"result":"25"}`. Results are decimal strings to preserve exact
integers. Errors use `{"error":"..."}` without echoing requests. Requests are
limited to 16 KiB per line; oversized input terminates the process with status 2.
Malformed complete lines produce errors and allow subsequent requests to run.
Timeouts default to 30 seconds and must be between 1 and 60,000 milliseconds.
Cancellation is cooperative: a sort or prime-sieve segment can run past the
cutoff before the next check. This is not a hard process execution limit.

Use `Work::parse` at untrusted boundaries before executing work. Supported bounds:

| Parameter | Limit |
| --- | --- |
| Numeric random seed magnitude | `2^64 - 1` |
| Monte Carlo samples | 50,000,000 |
| Sort count | 5,000,000 |
| Matrix dimension / modulus | 2,048 / `1..2^64 - 1` |
| Prime upper endpoint / effective interval width | 10^12 / 10,000,000 |
| Hash seed / threshold | 128 Unicode characters / `1..2^32` |

Parameters must be JSON integers (hash seeds also accept strings). Unsupported
inputs are rejected instead of coerced. Negative random seeds use their absolute
value, matching CPython. The public `Work` variants are for trusted callers;
constructing them directly bypasses validation.

Validation covers 239 exact reference comparisons, including the five assignment
golden cases, rejection sampling across 32/64-bit boundaries, checksum wraparound,
Unicode hashes, and segmented prime ranges. Twelve invalid requests and malformed
and oversized input exercise the CLI boundary. Rust tests cover mixed CPython
random draws, expired execution, queue admission, adaptive pricing, delivery
overhead, and hash deadline risk. No live manager connection or performance claim
is part of this milestone.

The recovered strategy starts bids at 1% of budget and allows bids below expected
cost; it has not been established as behaviorally equivalent to the Python
contractor on this branch. Validate that policy separately before live use.
