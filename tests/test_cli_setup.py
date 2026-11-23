from __future__ import annotations

from click.testing import CliRunner

from project_intel.cli import setup as setup_mod
from project_intel.cli.main import main


def test_doctor_reports_missing_tool_with_hint(monkeypatch):
    monkeypatch.setattr(setup_mod.shutil, "which", lambda b: None if b == "tokei" else f"/bin/{b}")
    out = CliRunner().invoke(main, ["doctor"]).output
    assert "✗ tokei" in out and "brew install tokei" in out
    assert "✓ graphify" in out


def test_setup_missing_harness_binary_prints_command(monkeypatch):
    monkeypatch.setattr(setup_mod.shutil, "which", lambda b: None)
    out = CliRunner().invoke(main, ["setup", "--harness", "codex"]).output
    assert "codex mcp add atlas -- atlas mcp-serve" in out
    assert "--no-llm" in out


def test_setup_claude_installs_recipe_once_and_never_overwrites(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_mod.shutil, "which", lambda b: None)
    monkeypatch.setattr(setup_mod.Path, "home", lambda: tmp_path)
    dest = tmp_path / ".claude" / "agents" / "atlas-synthesis.md"
    runner = CliRunner()
    assert "synthesis agent installed" in runner.invoke(main, ["setup", "--harness", "claude"]).output
    assert dest.read_text().startswith("---\nname: atlas-synthesis")
    dest.write_text("mine")
    assert "left untouched" in runner.invoke(main, ["setup", "--harness", "claude"]).output
    assert dest.read_text() == "mine"


def test_doctor_install_runs_installer_for_missing_tool(monkeypatch):
    ran = []
    monkeypatch.setattr(setup_mod.shutil, "which",
                        lambda b: None if b in ("graphify", "brew") else f"/bin/{b}")
    monkeypatch.setattr(setup_mod.subprocess, "run",
                        lambda cmd, **kw: ran.append(cmd) or type("R", (), {"returncode": 0})())
    CliRunner().invoke(main, ["doctor", "--install"])
    assert ran == [["uv", "tool", "install", "graphifyy"]]


def _only(*present):
    return lambda b: f"/bin/{b}" if b in present else None


def test_setup_detects_single_harness(monkeypatch):
    monkeypatch.setattr(setup_mod.shutil, "which", _only("agy"))
    monkeypatch.setattr(setup_mod.subprocess, "run",
                        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    out = CliRunner().invoke(main, ["setup"]).output
    assert "Detected: agy" in out and "registered in agy" in out
    assert "Setting up Atlas for claude" not in out


def test_setup_asks_when_several(monkeypatch):
    monkeypatch.setattr(setup_mod.shutil, "which", _only("agy", "claude"))
    monkeypatch.setattr(setup_mod.subprocess, "run",
                        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    monkeypatch.setattr(setup_mod.Path, "home", lambda: __import__("pathlib").Path("/nonexistent-home"))
    monkeypatch.setattr(setup_mod, "_install_recipe", lambda home: None)
    monkeypatch.setattr(setup_mod, "_interactive", lambda: True)
    out = CliRunner().invoke(main, ["setup"], input="agy\n").output
    assert "Several agents found" in out and "Setting up Atlas for agy" in out
    assert "Setting up Atlas for claude" not in out


def test_setup_several_without_tty_asks_for_flag(monkeypatch):
    monkeypatch.setattr(setup_mod.shutil, "which", _only("agy", "claude"))
    result = CliRunner().invoke(main, ["setup"])
    assert result.exit_code != 0 and "pass --harness" in result.output


def test_setup_none_found(monkeypatch):
    monkeypatch.setattr(setup_mod.shutil, "which", lambda b: None)
    assert "No supported agent" in CliRunner().invoke(main, ["setup"]).output
