from scripts.restart_live_session import _build_parser


def test_restart_defaults_to_regular_session_hard_gate_mode() -> None:
    args = _build_parser().parse_args([])

    assert args.allow_offhours is False


def test_restart_allows_explicit_offhours_drill() -> None:
    args = _build_parser().parse_args(["--allow-offhours"])

    assert args.allow_offhours is True
