# Arena-style improvement loop (how to use several Claude accounts)
Claude cannot spawn hundreds of agents from one chat, but you can run a tournament by hand:
1. Give each helper the HANDOFF prompt plus one target, e.g. "improve trip inference", "improve stop matching for Hindi/English", "improve shrinkage", "improve UI".
2. Each helper works on its OWN git branch and must not change `crowd/validate.py` or the metric definitions.
3. Run `python run_pipeline.py` on the REAL data for each branch and compare `outputs/metrics.json`.
   Primary score: `ARENA_SCORE` (0.4 × skill vs route baseline + 0.3 × week-2-vs-3 Spearman + 0.3 × 3-class level accuracy). Also compare holdout R² in `outputs/holdout_scores.csv`.
   Hard gates: stop match rate (outputs/match_report.md) not lower than main; tickets kept not lower than main.
4. Merge only the winning change per target; re-run tests (`pytest tests`) and the clean-clone check.
Beware: the score rewards self-consistency across weeks, not ground truth; no data here reveals actual crowding, so also read charts and sanity-check.
