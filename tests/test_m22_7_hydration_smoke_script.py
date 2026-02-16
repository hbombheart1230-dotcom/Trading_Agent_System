from __future__ import annotations

import json

from scripts.smoke_m22_hydration import main as smoke_main


def test_m22_7_smoke_normal_requires_no_fallback(capsys):
    rc = smoke_main(["--require-skill-fetch", "--require-no-fallback", "--show-json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["skill_fetch"]["used_runner"] is True
    assert obj["scanner_skill"]["fallback"] is False
    assert obj["monitor"]["order_status_fallback"] is False


def test_m22_7_smoke_timeout_requires_fallback(capsys):
    rc = smoke_main(["--simulate-timeout", "--require-skill-fetch", "--require-fallback", "--show-json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["skill_fetch"]["errors_total"] >= 1
    assert obj["scanner_skill"]["fallback"] is True
    assert obj["monitor"]["order_status_fallback"] is True


def test_m22_7_smoke_timeout_fails_when_no_fallback_required(capsys):
    rc = smoke_main(["--simulate-timeout", "--require-no-fallback"])
    out = capsys.readouterr().out
    assert rc == 3
    assert "require-no-fallback failed" in out
