# Budget-aware pricing experiment

The baseline sells a fast job cheaply even when its budget is large. The new optional `--pricing adaptive` mode tests whether asking for more of that budget increases profit. It changes pricing only; execution, timing, queue handling, and the Python 3.9.6 runtime stay the same.

## Policy

1. Calculate the usual delivery estimate and 1.28-based minimum price. Refuse work that fails the existing checks.
2. Round the budget downward to four decimal places. Ask for `minimum + share × (budget − minimum)`.
3. Start the share at 0.50 for each task type. Increase it by 0.05 after a correct delivery, capped at 0.95. Decrease it by 0.10 after a valid loss to another contractor, floored at zero.

Failed deliveries and invalid bids do not train the price share. State resets on restart. The default remains `--pricing markup`, so both policies can be reproduced. The practice experiment explicitly uses `--pricing adaptive`.

A job with a 4.41 budget and a 0.21 baseline price starts at 2.31. Under `best_value`, that increases our auction score by 2.10 with unchanged delivery time. It can earn more when accepted, but can also lose to a competitor. Winning price alone does not tell us the competitor's score because their estimated time matters too. This is simple outcome feedback, not a model of their strategy.

The 0.50 initial share and adjustment sizes are hypotheses to test. There is no proof that they maximize profit. A per-task-type model also mixes different input sizes and budgets.

## Checks

From the repository root:

```bash
contract-net/student/.venv/bin/python validation/check_pricing.py
```

[Recorded checks](validation/pricing_checks.json) cover 28 budget/precision boundaries; increase/decrease behavior and caps; ignored invalid feedback; separation between task types; six baseline bidding checks; existing lifecycle checks; and all five task types delivered and settled through the actual SDK over a localhost WebSocket in adaptive mode. The supplied `verify.py` also passed all reference and custom executor checks. SDK files, reference tasks, verifier, and requirements remain unchanged.

These tests establish implementation behavior. The local manager's generous budget and synthetic settlements do not establish profitability.

## Initial live snapshot — September 8, 2026

From the first bid at 18:28:24 through the last included settlement at 18:30:11 Pacific, adaptive mode completed **14 jobs correctly, with zero failures and 26.93 credits profit**. All five task types are represented. See [the recorded bids and settlements](validation/adaptive_live_results.json).

| Task | Correct deliveries | Profit |
|---|---:|---:|
| Sort checksum | 4 | 7.60 |
| Prime count | 3 | 9.61 |
| Monte Carlo | 1 | 1.77 |
| Hash search | 5 | 6.31 |
| Matrix checksum | 1 | 1.64 |

This is a short snapshot, not the whole continuing run. Competing public bids were not sampled during it. The earlier baseline's 49 jobs earned 19.68 credits, but different task mixes, timing, and auction conditions prevent treating the totals as a controlled improvement percentage. The new mode demonstrably collected its higher prices and delivered correct answers; competitive superiority remains unproven.

## What to measure

Compare profit per unit of wall-clock time, total failures, acceptance rate, and profit by task type. A higher profit per completed job can hide excessive auction losses. Use repeated or interleaved baseline/adaptive trials with similar task mixes and record changes in competition. A short sequential trial cannot isolate all those effects.

Each `BID` log includes its baseline price and adaptive share, allowing a hypothetical baseline payment comparison for jobs we actually won. Such a calculation is not an observed second run: it assumes the same awards, runtimes, and availability, and omits jobs a different policy might have won or declined.

## Remaining work on runtime risk

Raising prices does not fix underestimated execution or missed deadlines. The next separate timing experiment should measure per-task prediction errors on held-out runs and test an upper runtime quantile for admission and cost coverage, while checking the loss of competitiveness from longer quotes.

Hash search needs its own model. Under the independent uniform-hash model, with success probability `p = threshold / 2^32` per attempt, the probability of still searching after k attempts is `(1-p)^k`. A deadline can therefore admit a nonzero failure probability even when it comfortably exceeds the mean. Expected payment must be weighed against compute cost and the manager's budget-based failure penalty, using live rules. This model and a risk-based admission/price rule are **not implemented** in this experiment. Repeated practice seeds cannot validate unseen-seed tail behavior.

Do not describe a successful practice run as a proven tournament-winning strategy. See [the agent guide](AGENT_GUIDE.md) for the complete explanation.
