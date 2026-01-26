from kingdom import cli


def test_hand_command_defaults_to_opus_alias() -> None:
    tokens = cli.hand_command().lower().split()
    assert "--model" in tokens
    model_index = tokens.index("--model") + 1
    assert tokens[model_index] == "opus"
