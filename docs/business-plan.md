# Pitstop business plan (built with cfo.ai)

This plan was built on 2026-10-10 by **Ari, cfo.ai's AI CFO**, in the cfo.ai workspace
`ROHITCRAFTSYT CFOAI`. It has four model pages: *Pitstop: Controls*, *Revenue and
economics*, *Cash and runway* and *Sensitivities*, plus 12 saved scenarios and a forecast
simulator. The figures below are copied from Ari's output. They are forecast
assumptions, not actual revenue.

- **Live model (view-only, no login):** https://cfo.ai/s/W2RB_otvpzPIaBn6 (all four pages)
- **Spreadsheet export of the Controls page:** [`docs/cfo-ai/pitstop-controls.xlsx`](cfo-ai/pitstop-controls.xlsx)
  (pricing and allowances, operating assumptions, design-partner targets)

## Inputs we gave Ari

| Item | Value |
|---|---|
| Free tier | Open-source CLI, bring your own model keys (no modeled revenue or cost) |
| Team plan | $49 / repo / month, 40 pit stops included |
| Business plan | $299 / month, 5 repos, 400 pit stops included |
| Overage | $1.50 / pit stop |
| Variable cost per pit stop | model calls $0.30–$1.20 (midpoint $0.75), runner $0.02, logs $0.01 |
| Observed real-run model cost | $0.04–$0.21 per pit stop ([reports/](../reports/)) |
| Fixed monthly costs | founders $4,000 (combined), infra $300, tools $150, marketing $300 |
| Growth | months 1–3: 10 → 25 → 40 Team repos, 1 → 1.5 → 2 Business accounts; months 4–12: +15% additions, −3% churn (12% net) |
| Starting cash | $10,000 |
| Forecast window | Oct 2026 – Sep 2027 |

## Base case (40 stops per repo, $0.78 total variable cost per stop)

| Metric | Result |
|---|---|
| 12-month revenue | **$47,352** |
| Month-12 monthly revenue | $7,094 |
| Company gross margin (incl. fixed infra) | 31.5% |
| Monthly burn, month 1 → month 12 | $4,429 → $1,982 |
| Cash exhaustion | **Month 3 (December 2026)** |
| Operating break-even | Not reached within 12 months |
| Additional cash needed (no buffer) | **$28,506** |
| Break-even scale | ~191 Team repos + 9.5 Business accounts (month 12 reaches ~111 + 5.5) |

## Unit economics (midpoint model cost)

| Plan / usage | Contribution | Margin before fixed infra |
|---|---|---|
| Team, $49, 40 stops | $17.80 / repo | 36.3% |
| Business, 40 stops per repo | $143 / account | 47.8% |
| Team, $29, 40 stops | **−$2.20 / repo** | negative |
| Business, 80 stops per repo (full 400 allowance) | **−$13 / account** | negative |
| Team, $49, full allowance at the $1.20 upper model cost | $49.20 cost vs $49 revenue | ≈ 0 |

## Sensitivity: additional cash needed over 12 months

Business pricing is fixed; usage changes on both plans; demand is held constant.

| Stops / repo / month | Team $29 | Team $49 | Team $79 |
|---|---|---|---|
| 20 | $28,816 | $14,257 | $1,560 |
| 40 | $43,245 | $28,506 | $8,544 |
| 80 | $27,886 | $13,494 | $1,332 |

The $79 cases reach operating break-even in May, July and April 2027 respectively,
but every case still needs interim funding. Ari also saved three model-cost scenarios
(low $0.30, high $1.20, and an "observed cost" illustration at $0.125).

## What we take from it

1. **Cash, not growth, is the first constraint.** $10k runs out in December 2026, so we
   need about $28.5k of bridge funding (or prize money and design-partner prepayments)
   to get through the first year at $49.
2. **Don't launch at $29.** Each Team repo loses money there before fixed costs.
3. **Business allowance is too generous.** At 80 stops per repo it loses $13 per
   account. Ari's recommendation is to test a smaller allowance.
4. **Meter the real cost of a pit stop, failed patches included.** Pitstop's own budget
   ledger already records this per run (`reports/*.json` → `ledger`). Our real runs cost
   $0.04–$0.21, well under the $0.75 planning midpoint. If that holds in production,
   margins improve a lot. Ari flags this as the biggest pricing risk to confirm.
5. **$79 Team pricing is the strongest lever.** At $79 it breaks even within the year
   in all three usage cases.

Assumptions Ari disclosed as zero: taxes, payment fees, capex, financing, free-CLI
support, salary increases, extra hires.
