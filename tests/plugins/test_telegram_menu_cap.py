"""Tests for Telegram 60-command menu cap and prioritization."""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

if "telegram" not in sys.modules:
    class _FakeBotCommand:
        def __init__(self, command, description):
            self.command = command
            self.description = description

    _tg = types.ModuleType("telegram")
    _tg.BotCommand = _FakeBotCommand  # type: ignore[attr-defined]
    for _s in ("BotCommandScopeDefault", "BotCommandScopeAllPrivateChats", "BotCommandScopeAllGroupChats"):
        setattr(_tg, _s, type(_s, (), {}))
    sys.modules["telegram"] = _tg

from gateway.config import PlatformConfig
from plugins.platforms.telegram.adapter import (
    TelegramAdapter,
    _is_dev_infra_command,
    prioritize_telegram_menu_commands,
)


def _make_candidates():
    domain = [(f"domain_cmd_{i}", f"Domain {i}") for i in range(45)]
    infra = [(n, n.title()) for n in (
        "config", "debug", "model", "tools", "toolsets", "reload", "kanban", "cron", "diff",
        "verbose", "yolo", "approvals", "reasoning", "fast", "battery", "timestamps", "footer",
        "focus", "egress", "context", "rollback", "snapshot")]
    return domain, infra, domain + infra


def test_menu_cap_60():
    _, _, all_cmds = _make_candidates()
    registered, hidden = prioritize_telegram_menu_commands(all_cmds, max_commands=60)
    assert len(registered) == 60
    assert len(hidden) == 7
    assert len(registered) + len(hidden) == len(all_cmds)


def test_domain_commands_survive():
    domain, _, all_cmds = _make_candidates()
    registered, hidden = prioritize_telegram_menu_commands(all_cmds, max_commands=60)
    registered_names = {name for name, _ in registered}
    assert {name for name, _ in domain}.issubset(registered_names)
    assert all(_is_dev_infra_command(name) for name, _ in hidden)


def test_under_cap_noop():
    cmds = [("help", "Help"), ("slides", "Slides")]
    registered, hidden = prioritize_telegram_menu_commands(cmds, max_commands=60)
    assert registered == cmds and hidden == []


def test_register_command_menu_logging(caplog):
    domain, _, all_cmds = _make_candidates()
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="fake:token", extra={}))
    mock_bot = MagicMock(set_my_commands=AsyncMock())
    adapter._bot = mock_bot

    with (
        patch("hermes_cli.commands_platforms.telegram_menu_max_commands", return_value=60),
        patch("hermes_cli.commands_platforms.telegram_menu_commands", return_value=(all_cmds, 0)),
        caplog.at_level("INFO"),
    ):
        asyncio.run(adapter._register_command_menu())

    assert mock_bot.set_my_commands.await_count == 3
    sent = mock_bot.set_my_commands.call_args[0][0]
    assert len(sent) == 60 and {name for name, _ in domain}.issubset({cmd.command for cmd in sent})
    assert "Telegram menu: 60 commands registered, 7 hidden (over 60 limit):" in caplog.text
    assert any(f"/{name}" in caplog.text for name in ("context", "rollback", "snapshot", "egress"))
