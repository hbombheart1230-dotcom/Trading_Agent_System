from __future__ import annotations

import json
from pathlib import Path

from scripts.run_m26_dataset_manifest_check import main as manifest_main
from scripts.run_m26_scorecard import main as scorecard_main


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_m26_3_scorecard_passes_with_seed_dataset(tmp_path: Path, capsys):
    root = tmp_path / "m26_dataset"
    rc_seed = manifest_main(["--dataset-root", str(root), "--seed-demo", "--json"])
    _ = capsys.readouterr().out.strip()
    assert rc_seed == 0

    rc = scorecard_main(["--dataset-root", str(root), "--day", "2026-02-17", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["executed_trade_total"] >= 1
    assert obj["missing_file_total"] == 0
    assert "total_pnl_proxy" in obj
    assert "risk_adjusted" in obj
    assert "drawdown" in obj


def test_m26_3_scorecard_computes_positive_realized_pnl(tmp_path: Path, capsys):
    root = tmp_path / "m26_dataset"
    rc_seed = manifest_main(["--dataset-root", str(root), "--seed-demo", "--json"])
    _ = capsys.readouterr().out.strip()
    assert rc_seed == 0

    _write_jsonl(
        root / "execution" / "intents.jsonl",
        [
            {"ts": "2026-02-17T00:01:00+00:00", "intent_id": "i1", "symbol": "005930", "action": "BUY", "qty": 1},
            {"ts": "2026-02-17T00:02:00+00:00", "intent_id": "i2", "symbol": "005930", "action": "SELL", "qty": 1},
        ],
    )
    _write_jsonl(
        root / "execution" / "fills.jsonl",
        [
            {"ts": "2026-02-17T00:01:05+00:00", "intent_id": "i1", "fill_price": 100, "fill_qty": 1},
            {"ts": "2026-02-17T00:02:05+00:00", "intent_id": "i2", "fill_price": 110, "fill_qty": 1},
        ],
    )
    (root / "market" / "ohlcv_1d.csv").write_text(
        "ts,symbol,open,high,low,close,volume\n2026-02-17T00:00:00+00:00,005930,100,112,99,110,1000\n",
        encoding="utf-8",
    )

    rc = scorecard_main(["--dataset-root", str(root), "--day", "2026-02-17", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["realized_pnl_proxy"] > 0.0
    assert obj["total_pnl_proxy"] > 0.0
    assert obj["win_rate"] > 0.0


def test_m26_3_scorecard_fails_when_required_files_missing(tmp_path: Path, capsys):
    root = tmp_path / "missing"
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps({"schema_version": "m26.dataset_manifest.v1", "dataset_id": "x", "components": {}}, ensure_ascii=False),
        encoding="utf-8",
    )

    rc = scorecard_main(["--dataset-root", str(root), "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["missing_file_total"] >= 1
    assert any("missing_required_files" in x for x in obj["failures"])
