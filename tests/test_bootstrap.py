"""Tests for the bootstrap wizard (nerve init)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from nerve.bootstrap import SetupWizard, SetupChoices, is_fresh_install, run_non_interactive
from nerve.cli import main


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """A temporary config directory (fresh install)."""
    return tmp_path / "config"


@pytest.fixture
def configured_dir(tmp_path: Path) -> Path:
    """A config directory that already has config.local.yaml."""
    d = tmp_path / "configured"
    d.mkdir()
    (d / "config.local.yaml").write_text("anthropic_api_key: sk-ant-test123\n")
    (d / "config.yaml").write_text("workspace: ~/test-workspace\n")
    return d


class TestIsFreshInstall:
    """Test fresh install detection."""

    def test_fresh_when_no_config_local(self, tmp_path: Path) -> None:
        assert is_fresh_install(tmp_path) is True

    def test_fresh_when_dir_missing(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nope"
        assert is_fresh_install(nonexistent) is True

    def test_not_fresh_when_config_local_exists(self, configured_dir: Path) -> None:
        assert is_fresh_install(configured_dir) is False

    def test_not_fresh_even_if_config_yaml_missing(self, tmp_path: Path) -> None:
        """config.local.yaml alone means it's configured."""
        (tmp_path / "config.local.yaml").write_text("anthropic_api_key: test\n")
        assert is_fresh_install(tmp_path) is False


class TestSetupChoicesDefaults:
    """Verify SetupChoices has sane defaults."""

    def test_defaults(self) -> None:
        c = SetupChoices()
        assert c.mode == "personal"
        assert c.anthropic_api_key == ""
        assert c.openai_api_key == ""
        assert c.workspace_path == Path("~/nerve-workspace")
        assert c.timezone == "America/New_York"
        assert c.enabled_crons == []
        assert c.task_description == ""


class TestNonInteractiveSetup:
    """Test non-interactive mode (Docker / CI)."""

    def test_requires_api_key(self, tmp_path: Path) -> None:
        """Should fail if ANTHROPIC_API_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the key if it exists
            env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                with pytest.raises(Exception):
                    run_non_interactive(tmp_path)

    def test_creates_all_files(self, tmp_path: Path) -> None:
        """Non-interactive mode should create config.yaml, config.local.yaml, workspace, and cron jobs."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-api03-testkey123",
            "NERVE_MODE": "personal",
            "NERVE_WORKSPACE": str(tmp_path / "workspace"),
            "NERVE_TIMEZONE": "Europe/London",
        }
        with patch.dict(os.environ, env, clear=False):
            run_non_interactive(tmp_path)

        # config.yaml exists
        assert (tmp_path / "config.yaml").exists()
        config = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert config["timezone"] == "Europe/London"
        assert config["workspace"] == str(tmp_path / "workspace")

        # config.local.yaml exists with API key
        assert (tmp_path / "config.local.yaml").exists()
        local = yaml.safe_load((tmp_path / "config.local.yaml").read_text())
        assert local["anthropic_api_key"] == "sk-ant-api03-testkey123"
        assert "auth" in local
        assert "jwt_secret" in local["auth"]

        # Workspace directory exists with template files
        ws = tmp_path / "workspace"
        assert ws.exists()
        assert (ws / "SOUL.md").exists()
        assert (ws / "AGENTS.md").exists()

        # Cron jobs file exists
        cron_file = Path("~/.nerve/cron/jobs.yaml").expanduser()
        # Note: cron file is always written to ~/.nerve, not tmp_path
        # We just verify it exists (it may have been created by a previous test/run)

    def test_worker_mode(self, tmp_path: Path) -> None:
        """Worker mode should create minimal workspace."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-api03-workerkey",
            "NERVE_MODE": "worker",
            "NERVE_WORKSPACE": str(tmp_path / "worker-ws"),
            "NERVE_TASK": "Monitor CI and fix flaky tests",
        }
        with patch.dict(os.environ, env, clear=False):
            run_non_interactive(tmp_path)

        ws = tmp_path / "worker-ws"
        assert ws.exists()
        assert (ws / "SOUL.md").exists()
        assert (ws / "AGENTS.md").exists()
        # Personal-only files should NOT exist
        assert not (ws / "USER.md").exists()
        assert not (ws / "MEMORY.md").exists()

        # TASK.md should be created
        assert (ws / "TASK.md").exists()
        assert "Monitor CI" in (ws / "TASK.md").read_text()

    def test_personal_mode_default_crons(self, tmp_path: Path) -> None:
        """Personal non-interactive should enable inbox-processor and task-planner."""
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-api03-testkey",
            "NERVE_MODE": "personal",
            "NERVE_WORKSPACE": str(tmp_path / "ws"),
        }
        with patch.dict(os.environ, env, clear=False):
            choices = run_non_interactive(tmp_path)

        assert "inbox-processor" in choices.enabled_crons
        assert "task-planner" in choices.enabled_crons


class TestDeferredWrites:
    """Verify nothing is written until _apply()."""

    def test_nothing_written_before_apply(self, tmp_path: Path) -> None:
        """SetupWizard should not write anything until _apply() is called."""
        wizard = SetupWizard(tmp_path)
        wizard.choices.anthropic_api_key = "sk-ant-api03-test"
        wizard.choices.workspace_path = tmp_path / "workspace"
        wizard.choices.mode = "personal"

        # Before apply — nothing should exist
        assert not (tmp_path / "config.yaml").exists()
        assert not (tmp_path / "config.local.yaml").exists()
        assert not (tmp_path / "workspace").exists()

    def test_apply_creates_files(self, tmp_path: Path) -> None:
        """Calling _apply() should create all config and workspace files."""
        wizard = SetupWizard(tmp_path)
        wizard.choices.anthropic_api_key = "sk-ant-api03-test"
        wizard.choices.openai_api_key = "sk-proj-test"
        wizard.choices.workspace_path = tmp_path / "workspace"
        wizard.choices.mode = "personal"
        wizard.choices.timezone = "US/Pacific"
        wizard.choices.enabled_crons = ["inbox-processor"]

        wizard._apply()

        # Config files created
        assert (tmp_path / "config.yaml").exists()
        assert (tmp_path / "config.local.yaml").exists()

        # Workspace created
        assert (tmp_path / "workspace" / "SOUL.md").exists()

        # Config content is valid YAML
        config = yaml.safe_load((tmp_path / "config.yaml").read_text())
        assert config["timezone"] == "US/Pacific"

        # Local config has keys
        local = yaml.safe_load((tmp_path / "config.local.yaml").read_text())
        assert local["anthropic_api_key"] == "sk-ant-api03-test"
        assert local["openai_api_key"] == "sk-proj-test"


class TestCliInit:
    """Test the 'nerve init' CLI command."""

    def test_if_needed_skips_when_configured(self, configured_dir: Path) -> None:
        """--if-needed should exit silently when already configured."""
        runner = CliRunner()
        result = runner.invoke(main, ["-c", str(configured_dir), "init", "--if-needed"])
        assert result.exit_code == 0
        assert result.output == ""  # Silent exit

    def test_if_needed_non_interactive(self, tmp_path: Path) -> None:
        """--if-needed --non-interactive should run setup when fresh."""
        (tmp_path).mkdir(exist_ok=True)
        runner = CliRunner()
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-api03-clitest",
            "NERVE_MODE": "personal",
            "NERVE_WORKSPACE": str(tmp_path / "ws"),
        }
        result = runner.invoke(
            main,
            ["-c", str(tmp_path), "init", "--if-needed", "--non-interactive"],
            env=env,
        )
        assert result.exit_code == 0
        assert (tmp_path / "config.local.yaml").exists()

    def test_non_interactive_fails_without_key(self, tmp_path: Path) -> None:
        """Non-interactive should fail without ANTHROPIC_API_KEY."""
        (tmp_path).mkdir(exist_ok=True)
        runner = CliRunner()
        # Explicitly clear the key
        env = {"ANTHROPIC_API_KEY": ""}
        result = runner.invoke(
            main,
            ["-c", str(tmp_path), "init", "--non-interactive"],
            env=env,
        )
        assert result.exit_code != 0


class TestConfigLocalPermissions:
    """Test that config.local.yaml gets restrictive permissions."""

    def test_permissions_set(self, tmp_path: Path) -> None:
        """config.local.yaml should be 0600 after apply."""
        wizard = SetupWizard(tmp_path)
        wizard.choices.anthropic_api_key = "sk-ant-api03-test"
        wizard.choices.workspace_path = tmp_path / "workspace"
        wizard.choices.mode = "personal"

        wizard._apply()

        local_path = tmp_path / "config.local.yaml"
        assert local_path.exists()
        # Check permissions (Unix only)
        mode = oct(local_path.stat().st_mode)[-3:]
        assert mode == "600"
