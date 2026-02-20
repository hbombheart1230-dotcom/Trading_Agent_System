from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m26_dataset_manifest_check import main as manifest_main
from scripts.run_m26_promotion_gate_check import main as gate_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m26_5_promotion_gate_passes_for_better_candidate(tmp_path: Path, capsys):
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

    rc = gate_main(
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
            "--min-delta-total-pnl-proxy",
            "5",
            "--min-sortino-proxy",
            "0",
            "--max-drawdown-ratio",
            "1",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["winner"] == "candidate"
    assert obj["recommended_action"] == "promote_candidate"
    assert obj["values"]["delta_total_pnl_proxy"] >= 5.0


def test_m26_5_promotion_gate_fails_when_threshold_not_met(tmp_path: Path, capsys):
    root = tmp_path / "same_dataset"
    rc_seed = manifest_main(["--dataset-root", str(root), "--seed-demo", "--json"])
    _ = capsys.readouterr().out.strip()
    assert rc_seed == 0

    rc = gate_main(
        [
            "--a-dataset-root",
            str(root),
            "--b-dataset-root",
            str(root),
            "--a-label",
            "baseline",
            "--b-label",
            "candidate",
            "--day",
            "2026-02-17",
            "--min-delta-total-pnl-proxy",
            "1",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["failure_total"] >= 1
    assert any("delta_total_pnl_proxy < min" in x for x in obj["failures"])
