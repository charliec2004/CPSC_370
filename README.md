# CPSC 370 — Contract Net Tournament

Group workspace for Assignment 1: build a Python contractor that bids on computational tasks and executes awarded jobs locally.

**New to the project? Read [How Auctioneers works](AGENT_GUIDE.md)** for the full plain-English walkthrough, a worked bidding example, the code map, and the current limitations.

**Team name:** `Auctioneers` — use this exact name for all practice and tournament runs.

**Tournament machine:** Charles's laptop. Tune and validate the final strategy on this machine.

The agent uses exact optimized matrix, prime, sorting, Monte Carlo, and hash-search executors. NumPy accelerates sorting and Monte Carlo, with Python fallbacks. Startup measures their speed, and settlements adjust computation estimates and delivery overhead. The default `competitive` mode lowers prices quickly after losses and screens hash-search deadline risk. Read the [current strategy](COMPETITIVE_STRATEGY.md) and [delivery estimate evidence](DELIVERY_ESTIMATES.md). Python 3.12.13 is now the recommended measured runtime; the existing 3.9.6 environment remains a fallback. See the [runtime comparison and rules explanation](PYTHON_RUNTIME.md).

## Setup

```bash
git clone https://github.com/charliec2004/CPSC_370.git
cd CPSC_370/contract-net/student
python3.12 -m venv .venv312
source .venv312/bin/activate
python -m pip install -r requirements-validated.txt
python verify.py
```

On Windows, activate the environment with `.venv312\Scripts\activate`.

NumPy 2.0.2 accelerates Monte Carlo while preserving Python's exact random stream. Without NumPy, the agent uses and calibrates a Python fallback. See [Monte Carlo correctness and measurements](MONTE_CARLO_PROOF.md). The pinned optional package supports Python 3.9–3.12.

## Practice

The [practice dashboard](https://contractnet.blackdial.workers.dev/dev?room=practice) shows tasks, bids, and protocol messages. Copy `contract-net/student/.env.example` to `.env` in the same directory and set `CLASS_TOKEN` to the class token from Canvas. The `.env` file is ignored by Git.

```bash
python my_contractor.py --name Auctioneers --practice
```

Machine labels use the SDK default (`Darwin arm64` on this Mac); there is no custom `--machine` launch option.

For the tournament, fill `INSTRUCTOR_TOURNAMENT_WEBSOCKET_URL` in `.env`, then run `python my_contractor.py --name Auctioneers`. A blank setting stops with a clear error. An explicit `--url` takes precedence; `--practice` selects the practice room.

The default is `--pricing competitive`. The earlier `--pricing adaptive` and `--pricing markup` modes remain available to compare pricing; all modes use the current faster executors.

The agent reads `.env` beside `my_contractor.py`, regardless of your working directory. An existing `CLASS_TOKEN` environment variable takes precedence; `--token` overrides both. Values may be plain or quoted and are read literally, without shell expansion. Coordinate runs: two agents using the same name cannot stay connected at once.

On the tested macOS runtime, Ctrl+C requests a graceful stop: the agent refuses new work and waits for pending bids and awarded contracts to settle before disconnecting. Wait for it to exit before another teammate starts it.

## Validation and evidence

The [optimization report](OPTIMIZATION_PROOF.md) contains correctness arguments, repeatable benchmarks, and live trial results. From the repository root, run the broader checks with:

```bash
contract-net/student/.venv/bin/python validation/prove_optimizations.py
```

This tests the actual implementation over a local WebSocket and makes no connection to the class server. Pause the practice agent before benchmarking. The supplied `python verify.py` remains the quick reference-answer check.

## Working together

- Create a branch for each change and open a pull request into `main`.
- Implement the bidding strategy in `contract-net/student/my_contractor.py`.
- Leave the supplied `contractnet/` SDK and reference task implementations unchanged.
- Run `python verify.py` from `contract-net/student` before submitting changes, especially executor changes.
- Keep practice evidence and strategy notes for the final write-up; do not commit credentials.

Read the [assignment](CPSC370-Assignment1-ContractNet.pdf), [starter README](contract-net/student/README.md), and [wire protocol](contract-net/PROTOCOL.md) for the full requirements.

The final course submission is the tournament version of `my_contractor.py` and one PDF of at most two pages covering strategy and tournament analysis.
