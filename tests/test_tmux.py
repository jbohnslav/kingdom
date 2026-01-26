import unittest

from kingdom import tmux


class TmuxPaneCommandTests(unittest.TestCase):
    def test_should_send_command_when_shell_idle(self) -> None:
        self.assertTrue(tmux.should_send_command(""))
        self.assertTrue(tmux.should_send_command("zsh"))
        self.assertTrue(tmux.should_send_command("bash"))

    def test_should_not_send_when_agent_running(self) -> None:
        self.assertFalse(tmux.should_send_command("claude"))
        self.assertFalse(tmux.should_send_command("codex"))
        self.assertFalse(tmux.should_send_command("agent"))
