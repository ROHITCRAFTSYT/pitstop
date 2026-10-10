# Scout (the patient)

Scout is a small tool-using research agent: give it a company website and it
returns a JSON brief (headcount, funding, founding year, HQ, leaders) built from
Crustdata company and people data.

It ships with the kinds of faults real agents ship with. Pitstop's job is to
find them from traces and fix them. Don't fix them by hand.

```bash
python -m evals.run --out results.json --model claude-haiku   # hackathon LiteLLM proxy
python -m evals.run --out results.json --model fake           # offline, deterministic
SCOUT_DATA=live python -m evals.run --out results.json        # real Crustdata API
```
