# Pitstop business plan (cfo.ai)

> Status: **inputs drafted, cfo.ai model pending.** The numbers below are the
> assumptions to enter into cfo.ai. The exported cfo.ai plan (pricing, costs,
> revenue, runway) replaces this section once it's generated.

## Product
Pitstop as a service: connect a GitHub repo and a neatlogs project. When an
agent's evals or production traces start failing, Pitstop opens a PR with a
verified fix and the before/after numbers.

## Pricing (proposed)
| Plan | Price | Includes |
|---|---|---|
| OSS CLI | free | self-hosted, bring your own model keys |
| Team | $49 / repo / month | hosted runner, 40 pit stops/month, GitHub PRs, neatlogs read-back |
| Business | $299 / month | 5 repos, 400 pit stops/month, scheduled heals on production trace failures, SSO |
| Overage | $1.50 / pit stop | beyond plan limits |

## Unit costs (per pit stop, estimated)
| Item | Cost |
|---|---|
| Pitstop model calls (claude-sonnet-4.6, ~4 diagnose + ~6 patch calls) | $0.30–$1.20 |
| Re-running the customer's evals | customer's own model keys (BYOK) |
| Runner compute (AWS Lambda/EC2, ~5 min) | ~$0.02 |
| Storage, logs, egress | ~$0.01 |
Target gross margin: ≥ 70% on Team.

## Fixed costs (monthly, early stage)
| Item | Cost |
|---|---|
| Founders (2, minimal salary) | $4,000 |
| Infra baseline (hosting, CI, observability) | $300 |
| Tools and subscriptions | $150 |
| Marketing / community | $300 |

## Revenue assumptions
- Month 1–3: 10 → 40 Team repos (design partners from the neatHack community), 1–2 Business.
- Month 4–12: 15% month-over-month growth in paid repos; 3% monthly churn.
- Starting cash: $10,000 (hackathon prize money and founder savings).

## Questions for the cfo.ai model
- Break-even month and runway at these assumptions.
- Sensitivity: pit stops per repo (20 / 40 / 80) vs. gross margin.
- Price test: Team at $29 / $49 / $79.
