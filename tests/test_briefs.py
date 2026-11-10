"""The frozen briefs in agents/briefs/: law-free, consistent with the code that reads their answers, and
holding the registered wording. (tests/test_sealed_leaks.py checks them against the sealed laws too.)"""
import json
import re
from pathlib import Path

import pytest

from rating import prepare
from seam import blind, frame_pick, points

BRIEFS = blind.BRIEFS
ALL = sorted(BRIEFS.glob("*.md"))
TEMPLATES = ["rater-probe-draft.md", "rater-study-baseline.md", "rater-study-clips.md", "human-rater-study.md",
             "human-rater-study-failure-path.md"]       # the last: deviation D3 (call 143)
PICKER_BRIEFS = ["prompt-frame.md", "take-mask-points.md", "render-mask-points.md"]
ROOT = blind.ROOT


def text(name):
    return (BRIEFS / name).read_text(encoding="utf-8")


def json_blocks(t):
    return [json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", t, re.S)]


def test_the_expected_briefs_exist():
    assert sorted(p.name for p in ALL) == sorted(TEMPLATES + PICKER_BRIEFS)


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_no_banned_word_reaches_an_agent_or_rater(path):
    """Model names and ids, material names at the start of any word, and the project's name."""
    banned = prepare.parse_banned("\n".join(prepare.banned_lines({"laws": [], "materials": {}}, strict_materials=True)))
    assert prepare.find_banned(path.read_text(encoding="utf-8"), banned) == []


@pytest.mark.parametrize("path", ALL, ids=lambda p: p.name)
def test_placeholders(path):
    want = {"Q2_OPTIONS"} if path.name in TEMPLATES else set()
    assert set(blind.PLACEHOLDER.findall(path.read_text(encoding="utf-8"))) == want


@pytest.mark.parametrize("name", TEMPLATES)
def test_q1_options_in_registered_order(name):
    t = text(name)
    block = "\n".join(f"- {o}" for o in prepare.Q1_OPTIONS)
    assert block in t


@pytest.mark.parametrize("name", TEMPLATES[:3])
def test_rater_templates_render_and_name_their_fields(name, tmp_path):
    q2 = tmp_path / "q2.json"
    q2.write_text(json.dumps({"schema": "p47-q2-options/1", "options": ["One (fixture)", "Two (fixture)",
                                                                       "Nothing in particular", "Can't tell"]}))
    out = blind.render_sealed_brief(BRIEFS / name, q2, tmp_path / "out.md", sealed_root=tmp_path)
    rendered = Path(out["out"]).read_text()
    assert "- One (fixture)\n- Two (fixture)\n- Nothing in particular\n- Can't tell" in rendered
    kind = name[len("rater-"):-len(".md")]
    fields = blind.rater_fields(kind, ["One (fixture)", "Two (fixture)", "Nothing in particular", "Can't tell"])
    for f in fields:
        assert f"**`{f}`:" in rendered
    ex = json_blocks(rendered)[-1]
    code = next(iter(ex["items"]))
    assert blind.validate_choices(ex, [code], fields) == []
    assert blind.RATER_BRIEF_NAME in rendered


def test_probe_brief_asks_the_registered_questions():
    t = text("rater-probe-draft.md")
    assert "Does a drawn figure come to life and move out of its place on the page?" in t
    assert prepare.TEXT["q1"] in t and prepare.TEXT["q2"] in t


def test_study_briefs_ask_the_registered_questions():
    assert prepare.TEXT["q1b"] in text("rater-study-baseline.md") and prepare.TEXT["q2b"] in text("rater-study-baseline.md")
    assert prepare.TEXT["q1"] in text("rater-study-clips.md") and prepare.TEXT["q2"] in text("rater-study-clips.md")


def test_human_record_holds_the_on_screen_wording():
    t = text("human-rater-study.md")
    for k in ("title", "q1b", "q2b", "q1", "q2", "watch_note"):
        assert prepare.TEXT[k] in t, k
    for line in prepare.TEXT["baseline_intro"] + prepare.TEXT["clips_intro"]:
        assert f"> {line}" in t


def _quote_block(t, start, stop):
    out, on = [], False
    for line in t.splitlines():
        if line.startswith(start):
            on = True
            continue
        if on and line.startswith(stop):
            break
        if on and line.startswith(">"):
            out.append(line)
    return out


def test_human_record_holds_the_registered_invite_text():
    reg = _quote_block((ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8"), "**Invite text**", "**Reported")
    mine = _quote_block(text("human-rater-study.md"), "## 1.", "## 2.")
    assert reg and mine == reg


def test_picker_brief_examples_parse_with_the_recorders():
    pf = json_blocks(text("prompt-frame.md"))
    assert frame_pick.parse_pick(pf[0], 60) == (37, [])
    tk = json_blocks(text("take-mask-points.md"))[0]
    assert points.parse_take(tk, letters=["a", "b", "c"], n_stills=10)[1] == []
    rm = json_blocks(text("render-mask-points.md"))
    assert points.parse_place(rm[0], (720, 1280)) == ({"x": 702.0, "y": 431.0}, [])
    assert points.parse_check(rm[1], (720, 1280)) == (None, [])
    assert points.parse_check(rm[2], (720, 1280))[1] == []


def test_folder_file_names_match_the_briefs():
    assert "`stills.txt`" in text("prompt-frame.md") and "target.txt" not in text("prompt-frame.md")
    assert "dashed outline" in text("prompt-frame.md") and "dashed outline" in text("render-mask-points.md")
    assert f"`{blind.BRIEF_NAME}`" in text("prompt-frame.md")
    for n in ("`objects.txt`", "`stills.txt`"):
        assert n in text("take-mask-points.md")
    for n in ("`task.txt`", "`frame.png`", "`frame.grid.png`", "`mask.grid.png`"):
        assert n in text("render-mask-points.md")


@pytest.mark.parametrize("agent", ["blind-frame-picker.md", "blind-cue-rater.md"])
def test_agent_definitions_are_read_only(agent):
    t = (ROOT / "agents" / agent).read_text(encoding="utf-8")
    front = t.split("---")[1]
    assert re.search(r"^tools: Read$", front, re.M)
    assert "Never read any path outside that folder" in t


def test_the_clips_reference_is_the_ringed_baseline_picture():
    assert "ring" in text("rater-study-clips.md") and "ringed still from part 1" in text("human-rater-study.md")


@pytest.mark.parametrize("name", ["prompt-frame.md", "take-mask-points.md", "rater-probe-draft.md",
                                  "rater-study-baseline.md", "rater-study-clips.md"])
def test_long_folders_ask_for_batched_reads(name):
    assert "in parallel" in text(name)


# --- D3 (call 143): the failure path's record is version 1 with the counts changed, and its invite is the one in §24 ---------
FAILURE_PATH = "human-rater-study-failure-path.md"
D3_CHANGES = [("It takes about 15 minutes.", "It takes about 5 minutes."),
              ("eight still pictures, then eight short silent clips", "three still pictures, then three short silent clips"),
              ("**Part 1, the stills** (eight,", "**Part 1, the stills** (three,"),
              ("**Part 2, the clips** (eight,", "**Part 2, the clips** (three,")]


def _from_the_invitation(t):
    """Everything a rater receives, from the invitation on; the header paragraphs say which record this is."""
    return t[t.index("## 1."):]


def test_the_failure_path_record_is_version_1_with_the_counts_changed():
    want = _from_the_invitation(text("human-rater-study.md"))
    for old, new in D3_CHANGES:
        assert want.count(old) == 1, old
        want = want.replace(old, new)
    assert _from_the_invitation(text(FAILURE_PATH)) == want
    assert "eight" not in _from_the_invitation(text(FAILURE_PATH))


def test_the_failure_path_invite_is_the_one_in_d3():
    reg = _quote_block((ROOT / "PREREGISTRATION.md").read_text(encoding="utf-8"), "- *Invite text, failure path", "- *Why:*")
    mine = _quote_block(text(FAILURE_PATH), "## 1.", "## 2.")
    assert reg and mine == reg
