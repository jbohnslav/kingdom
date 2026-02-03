from kingdom import cli


def test_hand_command_runs_hand_module() -> None:
    tokens = cli.hand_command().lower().split()
    assert tokens[-2:] == ["-m", "kingdom.hand"]
