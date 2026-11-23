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
