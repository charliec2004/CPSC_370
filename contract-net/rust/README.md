# Rust contractor

The rewrite contains Python-compatible integer-seeded random generation, all
five exact task executors, calibration, cost-based bidding, and a WebSocket
client. The executable also accepts JSON lines on stdin for offline validation.
The supplied Python contractor and SDK remain unchanged.

## Connect

After building, run from the repository root:

```sh
caffeinate -i ./contract-net/rust/target/release/auctioneers run \
  --name Auctioneers \
  --env-file /path/to/contract-net/student/.env \
  --url 'wss://contractnet.blackdial.workers.dev/agent?room=fall26r2'
```

`caffeinate` is optional and macOS-specific. Stop another process using the same
team name first. `--practice` selects the practice room; otherwise `--url` takes
precedence over `INSTRUCTOR_TOURNAMENT_WEBSOCKET_URL`. `CLASS_TOKEN` is required.
Environment settings override the selected `.env`, and `--token` overrides both.
Without `--env-file`, the default is `student/.env` beside the Rust source tree
used to build the executable. Values are literal, without shell expansion.

Remote connections require `wss://` with certificate verification and an explicit
Rustls ring provider. Plain `ws://` is accepted only for loopback tests.

The client reserves compute and delivery allowance when proposing, including
three simultaneous offers, and executes awards serially off the event loop.
Duplicate awards do not rerun work. Results survive socket reconnects in memory,
are replayed only after registration, and remain retained until settlement or
expiry. A process restart loses that state. Server registration time anchors
award deadlines; wall-clock skew does not affect cutoff calculation.

Ctrl+C refuses new offers and drains pending bids and contracts. Pending bids
expire five seconds after their bidding window; unsettled awarded contracts
expire 30 seconds after their deadline and log the missing confirmation. This
does not claim they settled successfully. Supported deadlines are at most 300
seconds, bidding windows at most 60 seconds, and outstanding commitments at most
256. Authentication rejection or duplicate-name takeover stops reconnecting.

## Build and validate

From the repository root (Rust with edition 2024 support and Python 3.12):

```sh
cargo build --release --locked --manifest-path contract-net/rust/Cargo.toml
python3.12 validation/check_rust.py
cargo test --locked --manifest-path contract-net/rust/Cargo.toml
cargo clippy --locked --manifest-path contract-net/rust/Cargo.toml --all-targets -- -D warnings
# Use the project's Python environment with websockets installed:
contract-net/student/.venv312/bin/python validation/check_rust_client.py
```

## Offline execution

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
overhead, and hash deadline risk. The local WebSocket process tests cover three
simultaneous offers, duplicate awards, failed deadlines, reoffers, work finishing
offline, replay after lost acknowledgements, draining shutdown, bad tokens and
duplicate-name takeover.

## Pricing and validation limits

The recovered 1%-of-budget policy could bid below cost indefinitely. Bids now
have a floor of 1.28 times modelled cost, including queue time, delivery allowance,
and hash failure risk. If that exceeds the budget, the client refuses. Correct
deliveries that cost more than their price raise the next budget share toward
120% of measured cost. Two correct settlements raise the share by a meaningful
amount rather than multiplying a nearly zero bid. This changes policy relative
to Python and does not guarantee profit on stochastic hash tasks.

The release build, 239 parity comparisons, five initial Rust tests, and local
WebSocket lifecycle tests passed before live launch. The first `wss://` launch
exposed a missing Rustls crypto provider that plain-WebSocket tests did not cover.
The provider was explicitly enabled and installed, and the release binary rebuilt
successfully. Further tests were skipped at the user's request; TLS integration
has not yet been verified by the automated suite.

The user's subsequent live `fall26r2` log confirmed TLS registration with
concurrency 3 and six correct settlements (tasks 4, 9, 10, 12, 13, and 15).
Their reported profits sum to +$1.86; the two settled hash tasks contributed
+$1.33. One prime task lost $0.04. This is an initial run excerpt, not a final
room result or a controlled performance comparison.
