from kingdom import cli


def test_hand_command_defaults_to_opus_45() -> None:
    assert "opus" in cli.hand_command().lower()
    assert "4.5" in cli.hand_command()
