"""Score the ruling_status derivation against the hand-labeled check sets."""

import json
from collections import defaultdict

from tariffagent.data.db import connect

con = connect()
report = {"heuristic_version": "v3 (meta, reverse links, HQ text with proposal and negation filters, short forms)", "sets": {}}
for name, path, note in [
    ("check_50", "evals/status_check/labels.jsonl", "Stratified sample read before v2 and v3. The heuristic was fixed after reading it, so this score is in-sample."),
    ("holdout_20", "evals/status_check/holdout_labels.jsonl", "Drawn after v2: 15 text-derived cases plus 5 that v2 stopped flagging. v3 fixes came after, so partly in-sample."),
    ("holdout_v3_10", "evals/status_check/holdout_v3_labels.jsonl", "Drawn after v3 was frozen: 10 text-derived cases. This is the honest out-of-sample number for text-derived status."),
]:
    rows = [json.loads(line) for line in open(path)]
    per = defaultdict(lambda: [0, 0])
    errors = []
    for r in rows:
        got = con.execute("SELECT status FROM ruling_status WHERE id=?", (r["id"],)).fetchone()[0]
        ok = got == r["label"]
        per[r["stratum"]][0] += ok
        per[r["stratum"]][1] += 1
        if not ok:
            errors.append({"id": r["id"], "label": r["label"], "derived": got, "stratum": r["stratum"]})
    correct = sum(v[0] for v in per.values())
    report["sets"][name] = {
        "n": len(rows),
        "accuracy": round(correct / len(rows), 3),
        "by_stratum": {k: f"{v[0]}/{v[1]}" for k, v in per.items()},
        "errors": errors,
        "note": note,
    }
report["v1_on_check_50"] = {"accuracy": 0.96, "errors": ["H325434 (denied interim revocation)", "964559 (not specifically revoked)"]}
dist = {r[0]: r[1] for r in con.execute("SELECT method, COUNT(*) FROM ruling_status GROUP BY method")}
report["population_by_method"] = dist
json.dump(report, open("evals/reports/ruling_status_accuracy.json", "w"), indent=2)
print(json.dumps(report, indent=2))
