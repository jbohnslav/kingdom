from kingdom import tmux


def test_should_send_command_when_shell_idle() -> None:
    assert tmux.should_send_command("")
    assert tmux.should_send_command("zsh")
    assert tmux.should_send_command("bash")


def test_should_not_send_when_agent_running() -> None:
    assert not tmux.should_send_command("claude")
    assert not tmux.should_send_command("codex")
    assert not tmux.should_send_command("agent")
