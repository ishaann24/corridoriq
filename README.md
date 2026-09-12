# CorridorIQ

An AI-assisted commercial corridor opportunity finder for entrepreneurs deciding
where to open a business. Built for the "Beyond the Prompt" hackathon using the
NYC and Dallas–Fort Worth commercial corridor dataset.

deployment link- https://corridoriq.streamlit.app/

## What it does

You pick a **region**, a **business format** (café, or café/restaurant in DFW),
a **target audience**, and an **activity period**. CorridorIQ ranks the top
commercial corridors for that combination using a transparent, deterministic
scoring formula, business fit + audience relevance + activity match + anchor
signal − existing supply penalty and shows the evidence behind every score.

You can also ask a free-text question in the **Ask CorridorIQ** section. This
is a small AI agent (via Groq) that decides whether to call the ranking tool
or the corridor-detail tool, fetches real data, and answers grounded only in
that data, it never invents corridor names, scores, or facts, and asks a
clarifying question rather than guessing if your question doesn't map to the
data it has.

## How it's built

- `data_loader.py` loads and flattens `NYC_CORRIDORS_full.json` and
  `DALLAS_FORT_WORTH_CORRIDORS_full.json` into a shared, metro-agnostic
  structure (corridors, audience segments, archetypes, fit scores, anchors).
- `scoring_engine.py` deterministic, explainable scoring. No AI here; this
  is the ground truth the AI layer is only allowed to describe.
- `app.py` Streamlit UI. Renders rankings, corridor detail, and the
  Groq-powered explain button and Ask CorridorIQ agent.

## Running it

```bash
pip install -r requirements.txt
mkdir -p .streamlit
echo 'GROQ_API_KEY = "your-real-groq-key"' > .streamlit/secrets.toml
streamlit run app.py
```

Get a free Groq key at console.groq.com. The app still runs without one —
the "Explain" button falls back to a plain-text summary built from the same
evidence, and Ask CorridorIQ shows a graceful message instead of erroring.

## Important limitations (read this before trusting a number)

- Audience scores are **relative indices from 0–10**, not headcounts. A
  higher score means stronger relevance to that audience *compared with
  other corridors* , not a literal population count.
- Daypart activity figures are **relative activity indicators**, not
  measured foot traffic.
- Several signals in the source dataset , including whitespace and crime
  perception  are labeled by the data provider itself as
  `CURATED_EXPERT_ESTIMATE` or `EXPERT_SUPPLY_DEMAND_JUDGMENT_NOT_MEASURED_SATURATION`,
  not measured outcomes.
- **Dallas–Fort Worth corridors have no per-corridor place or anchor data**
  (`places` and `anchors` are empty for every DFW corridor in the source
  export). Existing-supply penalties and anchor bonuses for DFW rely
  entirely on metro-level `special_zones` records instead — this is called
  out directly in the app when it applies.
- This tool produces an **opportunity indicator based on available data
  signals** — never a guarantee of business success, revenue, or foot
  traffic.

## Data source

`EXPORT_MANIFEST.json` pins the exact release: bundle `usa-corridors-20260906-r2`,
65 NYC corridors, 72 DFW corridors, 55 shared audience segments, 6,684 total
fit scores.
