"""Every test gets its own roots: the blind ledgers, state, transcripts, prompt files and sealed folder live in
a throwaway repo (GIT_ROOT), and blind folders under a throwaway neutral root. Production has no overrides."""
import pytest


@pytest.fixture(autouse=True)
def _blind_roots(tmp_path_factory, monkeypatch):
    from seam import blind, points
    import subprocess
    repo = tmp_path_factory.mktemp("repo")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    for k, v in (("user.email", "t@t"), ("user.name", "t"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(repo), "config", k, v], check=True)
    (repo / ".gitignore").write_text("blind/\nsealed/\n")
    monkeypatch.setattr(blind, "NEUTRAL_ROOT", tmp_path_factory.mktemp("nr"))
    monkeypatch.setattr(blind, "GIT_ROOT", repo)
    monkeypatch.setattr(blind, "LOGS", repo / "agents" / "logs")
    monkeypatch.setattr(blind, "STATE", repo / "blind")
    monkeypatch.setattr(blind, "TRANSCRIPTS", repo / "blind" / "transcripts")
    monkeypatch.setattr(blind, "SEALED", repo / "sealed")
    monkeypatch.setattr(blind, "SEALED_STATE", repo / "sealed" / "blind")
    monkeypatch.setattr(blind, "SEALED_TRANSCRIPTS", repo / "sealed" / "blind" / "transcripts")
    monkeypatch.setattr(points, "PROMPTS", repo / "masks" / "prompts")
    return repo
