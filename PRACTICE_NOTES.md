# Auctioneers practice notes

## Starter baseline — September 8, 2026, about 5:00 p.m. Pacific

Machine: Charles's laptop, Darwin arm64. Runtime: Python 3.9.6 in `contract-net/student/.venv`. Strategy: unchanged starter, charging estimated computation cost times 1.6 and quoting queue time plus estimated computation time.

Source: the public practice dashboard and `/api/state?room=practice`. This is a point-in-time observation, not a completed tournament result.

| Metric | Observed value |
|---|---:|
| Submitted bids | 37 |
| Refusals | 0 |
| Contracts won | 0 |
| Completed jobs | 0 |
| Failed jobs | 0 |
| Profit | 0 credits |

The agent registered successfully and is sending bids. With no awards yet, we have no actual delivery times or settlement evidence for our own agent. Zero failures does not demonstrate reliable delivery when no contracts were won.

### Examples from the public bid record

The live policy scores bids as `price + 2 * est_seconds`; lower wins.

| Task | Our price | Our estimate | Our score | Winner | Winning price | Winning estimate | Winning score |
|---|---:|---:|---:|---|---:|---:|---:|
| #16 `sort_checksum` | 2.4853 | 1.5533 s | 5.5919 | CEBidders_A1 | 1.4243 | 0.8902 s | 3.2047 |
| #15 `hash_search` | 0.8765 | 0.5478 s | 1.9721 | team_abudabi | 1.1192 | 0.2798 s | 1.6788 |

Task #15 illustrates why lowering price alone is not the whole strategy: the winner charged more than us but quoted a shorter time. The trace reports that winner delivering correctly in 0.32 seconds. Task #16's winner delivered correctly in 1.13 seconds versus its 0.89-second estimate.

Task IDs repeat in the looping practice room; these examples refer to the observations around 5:00 p.m., not all occurrences of those IDs.

### Runtime experiment

Python 3.13.12 is already installed on Charles's laptop. A separate local run of the supplied calibration measured the following throughputs. The Python 3.9 figures are from the agent's startup at 4:55 p.m.; measurements were not simultaneous or repeated, so this is preliminary evidence only.

| Task | Python 3.9.6 work units/s | Python 3.13.12 work units/s |
|---|---:|---:|
| `monte_carlo_pi` | 5,529,030 | 8,244,462 |
| `prime_count` | 180,546,426 | 191,314,551 |
| `hash_search` | 1,961,540 | 1,699,650 |
| `sort_checksum` | 19,495,231 | 26,348,039 |
| `matmul_mod` | 15,064,286 | 18,001,942 |

The newer runtime improved four calibration measurements but reduced hash throughput. The running agent remains on Python 3.9.6; these measurements do not justify assuming every task gets faster.

## Next experiment

Before reducing prices, measure the reference executor on representative larger inputs and compare predicted computation time with measured computation time. Use fresh synthetic inputs for offline experiments and keep actual practice delivery measurements separate, because server billing includes network and queue delay. Then choose one change to test and record the resulting awards, costs, penalties, and profit.

Do not invent delivery estimates to win auctions. Faster execution or better measured estimates must support any shorter promise. Preserve these baseline observations when recording later strategies.
