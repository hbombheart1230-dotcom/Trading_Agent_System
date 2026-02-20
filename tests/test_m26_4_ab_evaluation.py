from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m26_ab_evaluation import main as ab_main
from scripts.run_m26_dataset_manifest_check import main as manifest_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m26_4_ab_eval_promotes_b_when_b_better(tmp_path: Path, capsys):
    a_root = tmp_path / "dataset_a"
    b_root = tmp_path / "dataset_b"

    rc_seed_a = manifest_main(["--dataset-root", str(a_root), "--seed-demo", "--json"])
    _ = capsys.readouterr().out.strip()
    assert rc_seed_a == 0

    rc_seed_b = manifest_main(["--dataset-root", str(b_root), "--seed-demo", "--json"])
    _ = capsys.readouterr().out.strip()
    assert rc_seed_b == 0

    _write_jsonl(
        b_root / "execution" / "intents.jsonl",
        [
            {"ts": "2026-02-17T00:01:00+00:00", "intent_id": "ib1", "symbol": "005930", "action": "BUY", "qty": 1},
            {"ts": "2026-02-17T00:02:00+00:00", "intent_id": "ib2", "symbol": "005930", "action": "SELL", "qty": 1},
        ],
    )
    _write_jsonl(
        b_root / "execution" / "fills.jsonl",
        [
            {"ts": "2026-02-17T00:01:05+00:00", "intent_id": "ib1", "fill_price": 100, "fill_qty": 1},
            {"ts": "2026-02-17T00:02:05+00:00", "intent_id": "ib2", "fill_price": 115, "fill_qty": 1},
        ],
    )
    (b_root / "market" / "ohlcv_1d.csv").write_text(
        "ts,symbol,open,high,low,close,volume\n2026-02-17T00:00:00+00:00,005930,100,116,99,115,1000\n",
        encoding="utf-8",
    )

    rc = ab_main(
        [
            "--a-dataset-root",
            str(a_root),
            "--b-dataset-root",
            str(b_root),
            "--a-label",
            "baseline",
            "--b-label",
            "candidate",
            "--day",
            "2026-02-17",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["comparison"]["winner"] == "candidate"
    assert obj["comparison"]["promotion_gate"]["recommended_action"] == "promote_candidate"


def test_m26_4_ab_eval_fails_when_b_dataset_invalid(tmp_path: Path, capsys):
    a_root = tmp_path / "dataset_a"
    b_root = tmp_path / "dataset_b_missing"
    b_root.mkdir(parents=True, exist_ok=True)

    rc_seed_a = manifest_main(["--dataset-root", str(a_root), "--seed-demo", "--json"])
    _ = capsys.readouterr().out.strip()
    assert rc_seed_a == 0

    rc = ab_main(
        [
            "--a-dataset-root",
            str(a_root),
            "--b-dataset-root",
            str(b_root),
            "--day",
            "2026-02-17",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert any("b_scorecard" in x for x in obj["failures"])
