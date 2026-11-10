"""seam/dispatch.py: the bare `claude -p` call, its outcomes, its commits, and the reviewers' attacks (no live calls)."""
import io
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from blindkit import all_files, store, stream
from seam import blind, dispatch, frame_pick


def prep(render="t01-ink"):
    h = np.zeros((72, 128), bool)
    h[20:40, 10:30] = True
    return frame_pick.build_folder(np.zeros((6, 72, 128, 3), np.uint8), render=render, home=h, video_sha256="v" * 64,
                                   size=(54, 96), stride=2)      # ledger tests: still k = frame 2(k - 1)


def ledger(render="t01-ink"):
    return json.loads(frame_pick.log_path(render).read_text())


def git(*args):
    return subprocess.run(["git", "-C", str(blind.GIT_ROOT), *args], capture_output=True, text=True)


class FakeProc:
    """A fake `claude -p`: its stdout yields the stream in two chunks; `during` runs between them (while the
    dispatcher is reading), as an attacker with a stopped process would act."""

    def __init__(self, data: bytes, code: int, during=None):
        self.returncode = code
        half = len(data) // 2
        self._chunks = [data[:half], data[half:]]
        self._during = during
        self.stdout = self

    def read(self, n=-1):
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if not self._chunks and self._during:
            self._during()
        return chunk

    def wait(self):
        return self.returncode

    def kill(self):
        pass


def popen_for(projects, st, answer, *, write_stream=True, write_store=True, store_copies=1, result=True, code=0,
              during=None):
    def popen(cmd, cwd, stdout, stderr, stdin, env):
        assert Path(cwd) == Path(st["folder"]) and stdout == subprocess.PIPE and stdin == subprocess.DEVNULL
        assert "CLAUDECODE" not in env
        sid = cmd[cmd.index("--session-id") + 1]
        tmp = Path(projects).parent / "fake"
        tmp.mkdir(parents=True, exist_ok=True)
        data = b""
        if write_stream:
            data = stream(tmp / "s.jsonl", st, reads=all_files(st), answer=answer, session_id=sid, result=result).read_bytes()
        if write_store:
            for k in range(store_copies):
                d = Path(projects) / (f"-x-blind-{st['code']}" if k == 0 else f"-elsewhere-{k}")
                d.mkdir(parents=True, exist_ok=True)
                store(d / f"{sid}.jsonl", st, reads=all_files(st), answer=answer, session_id=sid)
        return FakeProc(data, code, (lambda: during(Path(projects), st)) if during else None)
    return popen


def go(tmp_path, st, answer='{"pick": 2}', **kw):
    projects = tmp_path / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    return dispatch.run(st["code"], popen=popen_for(projects, st, answer, **kw), projects=projects), projects


def test_command_is_bare_read_only_pinned_and_streamed():
    st = prep()
    agent = blind.agent_spec(st["agent"])
    cmd = dispatch.command(st, agent, "sid")
    for flag in ("--restricted", "--strict-mcp-config", "--disable-slash-commands", "--verbose"):
        assert flag in cmd
    assert "--allowedTools" not in cmd and cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert cmd[cmd.index("--tools") + 1] == "Read" and cmd[cmd.index("--model") + 1] == "claude-opus-5-5"
    assert cmd[2] == st["dispatch"]


def test_run_records_commits_and_purges(tmp_path):
    st = prep()
    out, projects = go(tmp_path, st)
    assert out["status"] == "recorded" and out["valid"], out
    a = ledger()["attempts"][0]
    assert a["transcript_sha256"] == blind.sha256_path(Path(blind.TRANSCRIPTS) / f"{st['code']}.jsonl")
    blind.require_committed(frame_pick.log_path("t01-ink"))
    assert git("log", "-1", "--format=%s").stdout.strip() == f"blind ledger: prompt-frame {st['code']} recorded"
    assert not dispatch.store_dirs(st["code"], projects) and '"pick"' not in json.dumps(out)


def test_run_needs_the_prepared_attempt_committed_at_head(tmp_path):
    st = prep()
    lp = frame_pick.log_path("t01-ink")
    lp.write_text(lp.read_text() + " ")
    with pytest.raises(blind.BlindError, match="changes"):
        go(tmp_path, st)
    assert ledger()["attempts"][0]["status"] == "prepared"


def test_nothing_reached_the_api_is_a_dispatch_failure(tmp_path):
    st = prep()
    out, _ = go(tmp_path, st, write_stream=False, write_store=False, code=1)
    assert out["status"] == "dispatch_failed" and ledger()["result"] is None
    assert git("log", "-1", "--format=%s").stdout.strip().endswith("dispatch_failed")


def test_an_empty_stream_with_a_clean_exit_is_lost_not_failed(tmp_path):
    st = prep()
    out, _ = go(tmp_path, st, write_stream=False, write_store=False, code=0)
    assert out["status"] == "lost_after_dispatch" and ledger()["result"]["status"] == "failed"


@pytest.mark.parametrize("kw,reason", [({"write_store": False}, "store-missing"), ({"store_copies": 2}, "store-duplicate"),
                                       ({"result": False}, "no-result")])
def test_reaching_the_api_without_a_clean_record_is_lost_and_closes_the_step(tmp_path, kw, reason):
    st = prep()
    out, projects = go(tmp_path, st, **kw)
    a = ledger()["attempts"][0]
    assert out["status"] == "lost_after_dispatch" and a["reason"] == reason and a["disclose_in_a1"]
    assert ledger()["result"]["status"] == "failed"
    blind.require_committed(frame_pick.log_path("t01-ink"))
    with pytest.raises(blind.BlindError, match="closed"):
        prep()


# --- the reviewers' demonstrations, step by step --------------------------------------------------
def test_round3_c1_git_clean_cannot_rewind_a_recorded_pick(tmp_path):
    """Prepare, dispatch and record a pick (still 2); `git clean -fd agents`; prepare again and record still 4.
    The second pick must not happen, and verify must keep still 2."""
    st = prep()
    out, _ = go(tmp_path, st, '{"pick": 2}')
    assert out["result_status"] == "picked"
    git("clean", "-fd", "agents")
    with pytest.raises(blind.BlindError):
        st2 = prep()
        go(tmp_path / "again", st2, '{"pick": 4}')
    assert frame_pick.verify("t01-ink") == 2


def test_round3_c1_checkout_cannot_rewind_a_recorded_pick(tmp_path):
    """The same with `git checkout -- <ledger> <registry>` after an earlier commit."""
    st = prep()
    go(tmp_path, st, '{"pick": 2}')
    git("checkout", "--", "agents/logs/prompt-frame/t01-ink.json", "agents/logs/registry.jsonl")
    with pytest.raises(blind.BlindError):
        st2 = prep()
        go(tmp_path / "again", st2, '{"pick": 4}')
    with pytest.raises(blind.BlindError):
        go(tmp_path / "again2", st, '{"pick": 4}')                              # nor the same folder again
    assert frame_pick.verify("t01-ink") == 2


def test_round3_c1_rewinding_to_the_prepared_commit_cannot_redispatch(tmp_path):
    st = prep()
    go(tmp_path, st, '{"pick": 2}')
    git("checkout", "HEAD~1", "--", "agents/logs/prompt-frame/t01-ink.json", "agents/logs/registry.jsonl")
    shutil.rmtree(blind.TRANSCRIPTS, ignore_errors=True)
    with pytest.raises(blind.BlindError, match="changes"):
        go(tmp_path / "again", st, '{"pick": 4}')


def test_round3_c1_rater_ledgers_cannot_be_rewound(tmp_path):
    img = np.zeros((36, 64, 3), np.uint8)
    brief = tmp_path / "b.md"
    brief.write_text("brief")
    items = [{"ref": "render-a", "sheets": [img]}]
    st = blind.build_rater_folder(items, round_id="probe", brief=brief)
    q2 = tmp_path / "q2.json"
    q2.write_text(json.dumps({"schema": "p47-q2-options/1", "options": ["One (fixture)", "Nothing in particular", "Can't tell"]}))
    ans = json.dumps({"items": {st["codes"][0]: {"leaves_place": "Yes", "reacted_to": "The pen", "did": "One (fixture)"}},
                      "notes": ""})
    projects = tmp_path / "projects"
    projects.mkdir()

    def popen(cmd, cwd, stdout, stderr, stdin, env):
        sid = cmd[cmd.index("--session-id") + 1]
        reads = all_files(st, blind.RATER_BRIEF_NAME)
        d = projects / f"-x-blind-{st['code']}"
        d.mkdir(parents=True, exist_ok=True)
        store(d / f"{sid}.jsonl", st, reads=reads, answer=ans, session_id=sid)
        return FakeProc(stream(tmp_path / "s.jsonl", st, reads=reads, answer=ans, session_id=sid).read_bytes(), 0)
    assert dispatch.run(st["code"], q2=q2, popen=popen, projects=projects)["status"] == "recorded"
    git("clean", "-fd", "agents")
    with pytest.raises(blind.BlindError):
        blind.build_rater_folder(items, round_id="probe", brief=brief)


def test_round3_c2_adjudicate_after_kill_and_deletion_is_lost(tmp_path):
    """kill -9 the dispatcher mid-call, delete the stream and the store, then adjudicate: no fresh attempt."""
    st = prep()
    blind.mark_dispatched(st, session_id="s", command_sha256="c" * 64, agent=blind.agent_spec(st["agent"]))
    s = Path(st["transcripts"]) / f"{st['code']}.jsonl"
    s.parent.mkdir(parents=True, exist_ok=True)
    s.write_text('{"type": "system", "subtype": "init"}\n')
    projects = tmp_path / "projects"
    (projects / f"-x-blind-{st['code']}").mkdir(parents=True)
    s.unlink()
    shutil.rmtree(projects / f"-x-blind-{st['code']}")
    assert dispatch.adjudicate(st["code"], projects=projects)["status"] == "lost_after_dispatch"
    assert ledger()["result"]["status"] == "failed" and ledger()["attempts"][0]["adjudicated_utc"]
    blind.require_committed(frame_pick.log_path("t01-ink"))
    with pytest.raises(blind.BlindError, match="closed"):
        prep()


def test_round3_c2_unlinking_the_stream_and_store_mid_run_is_lost(tmp_path):
    """SIGSTOP the call, read the answer, unlink the stream file and the store, let it finish: the
    dispatcher decides from the bytes it already holds, so the attempt is lost, not failed."""
    def unlink_everything(projects, st):
        (Path(st["transcripts"]) / f"{st['code']}.jsonl").unlink()
        for d in dispatch.store_dirs(st["code"], projects):
            shutil.rmtree(d)
    st = prep()
    out, _ = go(tmp_path, st, during=unlink_everything)
    assert out["status"] == "lost_after_dispatch" and ledger()["result"]["status"] == "failed"
    with pytest.raises(blind.BlindError, match="closed"):
        prep()


def test_replacing_the_stream_file_mid_run_is_lost(tmp_path):
    def replace(projects, st):
        p = Path(st["transcripts"]) / f"{st['code']}.jsonl"
        p.unlink()
        p.write_bytes(b"")
    st = prep()
    out, _ = go(tmp_path, st, during=replace)
    assert out["status"] == "lost_after_dispatch" and ledger()["attempts"][0]["reason"] == "stream-replaced"


def test_purge_only_removes_this_folders_store(tmp_path):
    projects = tmp_path / "projects"
    (projects / "-Users-someone-project").mkdir(parents=True)
    (projects / "-x-blind-b0123456789").mkdir()
    dispatch.purge("b0123456789", projects)
    assert sorted(p.name for p in projects.iterdir()) == ["-Users-someone-project"]


def test_stream_info_reads_bytes_not_files():
    data = b'{"type": "system", "subtype": "init"}\nnot json\n{"type": "result", "num_turns": 3}\n'
    assert dispatch.stream_info(data) == ({"num_turns": 3}, True)
    assert dispatch.stream_info(b"") == ({}, False)
    assert io  # keeps the import for readers of FakeProc
