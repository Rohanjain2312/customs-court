# Contributing

Thanks for looking. Customs Court is a small research project, so the rules are simple.

## Setup

```bash
uv sync --extra embed --extra cloud --extra demo
cp .env.example .env   # keys are only needed for live runs
make test              # offline: recorded responses, no key, no spend
make eval-smoke        # offline: re-scores committed runs and replays a recorded classification
```

Building the full data set (`make data`) downloads the USITC HTS and CBP CROSS rulings politely (about one request per second, cached on disk). It takes hours. The tests use a 12 MB slice in `tests/fixtures/data`.

## Ground rules

- No live API calls in tests or CI. Record fixtures with `TARIFFAGENT_LIVE=1 TARIFFAGENT_RECORD=1 uv run pytest tests/test_agent_e2e.py` and commit the files under `tests/fixtures/data/cache`.
- Corpus text is untrusted. Anything that reaches a model from rulings or notes goes through `UntrustedText`.
- Every number in the README or `docs/CASE_STUDY.md` must come from a file in `evals/reports/`.
- Model ids come from environment variables, never from code. Opus-class and Fable-class models are refused by `config.py` to keep costs low.
- Writing style: plain words, short sentences, no em dashes, no hype.
- Run `make lint` and `make test` before opening a pull request.

## Where things live

See `docs/ARCHITECTURE.md` for the component map and `docs/EVAL.md` for how results are produced.
