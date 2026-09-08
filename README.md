# CPSC 370 — Contract Net Tournament

Group workspace for Assignment 1: build a Python contractor that bids on computational tasks and executes awarded jobs locally.

**Team name:** `Auctioneers` — use this exact name for all practice and tournament runs.

**Tournament machine:** Charles's laptop. Tune and validate the final strategy on this machine.

## Setup

```bash
git clone https://github.com/charliec2004/CPSC_370.git
cd CPSC_370/contract-net/student
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python verify.py
```

On Windows, activate the environment with `.venv\Scripts\activate`.

## Practice

The [practice dashboard](https://contractnet.blackdial.workers.dev/dev?room=practice) shows tasks, bids, and protocol messages. Copy `contract-net/student/.env.example` to `.env` in the same directory and set `CLASS_TOKEN` to the class token from Canvas. The `.env` file is ignored by Git.

```bash
python my_contractor.py --name Auctioneers --url 'wss://contractnet.blackdial.workers.dev/agent?room=practice'
```

The agent reads `.env` beside `my_contractor.py`, regardless of your working directory. An existing `CLASS_TOKEN` environment variable takes precedence; `--token` overrides both. Values may be plain or quoted and are read literally, without shell expansion. Coordinate runs: two agents using the same name cannot stay connected at once.

## Working together

- Create a branch for each change and open a pull request into `main`.
- Implement the bidding strategy in `contract-net/student/my_contractor.py`.
- Leave the supplied `contractnet/` SDK and reference task implementations unchanged.
- Run `python verify.py` from `contract-net/student` before submitting changes, especially executor changes.
- Keep practice evidence and strategy notes for the final write-up; do not commit credentials.

Read the [assignment](CPSC370-Assignment1-ContractNet.pdf), [starter README](contract-net/student/README.md), and [wire protocol](contract-net/PROTOCOL.md) for the full requirements.

The final course submission is the tournament version of `my_contractor.py` and one PDF of at most two pages covering strategy and tournament analysis.
