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

The [practice dashboard](https://contractnet.blackdial.workers.dev/dev?room=practice) shows tasks, bids, and protocol messages. Get the class token from Canvas; keep it out of commits and pull requests.

```bash
python my_contractor.py --name Auctioneers --url 'wss://contractnet.blackdial.workers.dev/agent?room=practice' --token CLASS_TOKEN
```

Replace `CLASS_TOKEN` locally with the token from Canvas. Coordinate runs: two agents using the same name cannot stay connected at once.

## Working together

- Create a branch for each change and open a pull request into `main`.
- Implement the bidding strategy in `contract-net/student/my_contractor.py`.
- Leave the supplied `contractnet/` SDK and reference task implementations unchanged.
- Run `python verify.py` from `contract-net/student` before submitting changes, especially executor changes.
- Keep practice evidence and strategy notes for the final write-up; do not commit credentials.

Read the [assignment](CPSC370-Assignment1-ContractNet.pdf), [starter README](contract-net/student/README.md), and [wire protocol](contract-net/PROTOCOL.md) for the full requirements.

The final course submission is the tournament version of `my_contractor.py` and one PDF of at most two pages covering strategy and tournament analysis.
