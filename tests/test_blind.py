"""seam/blind.py: folders, ledgers, transcripts, briefs, contact sheets and the rater."""
import json
from pathlib import Path

import numpy as np
import pytest

from blindkit import all_files, run
from seam import blind

HOME = str(Path.home())


def folder_in_root(name="bfolder"):
    return Path(blind.NEUTRAL_ROOT) / name


# --- folders --------------------------------------------------------------------------------
def test_write_folder_inventory_and_refuses_reuse():
    folder = folder_in_root("bf1")
    inv = blind.write_folder(folder, {"b.png": b"bb", "a.md": b"aa"})
    assert [r["name"] for r in inv] == ["a.md", "b.png"] and inv[0]["sha256"] == blind.sha256_bytes(b"aa")
    with pytest.raises(blind.BlindError, match="exists"):
        blind.write_folder(folder, {"c.png": b"c"})


def _noisy_png(seed, h=360, w=640):
    rgb = np.random.default_rng(seed).integers(0, 256, (h, w, 3), dtype=np.uint8)
    return blind.png_bytes(rgb)


def test_payload_bytes_is_the_sessions_jpeg90_base64():
    import base64
    import cv2
    data = _noisy_png(1)
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
    assert blind.payload_bytes({"001.png": data, "a.md": b"x" * 10**6}) == len(base64.b64encode(jpg))
    assert blind.payload_bytes({"001.png": b"not an image"}) == len(base64.b64encode(b"not an image"))


def test_write_folder_refuses_a_folder_over_the_budget_and_writes_nothing():
    files = {f"{k:03d}.png": _noisy_png(k) for k in range(1, 4)}
    size = blind.payload_bytes(files)
    folder = folder_in_root("bf2")
    with pytest.raises(blind.BlindError, match="budget"):
        blind.write_folder(folder, files, budget=size - 1)
    assert not folder.exists()
    assert len(blind.write_folder(folder, files, budget=size)) == 3


@pytest.mark.parametrize("name", ["../x.md", "ink.png", "t03.txt"])
def test_write_folder_refuses_bad_file_names(name):
    with pytest.raises(blind.BlindError):
        blind.write_folder(folder_in_root(), {name: b"a"})


def test_default_root_is_persistent_and_neutral(monkeypatch):
    monkeypatch.undo()
    assert blind.NEUTRAL_ROOT == Path.home() / ".blind"
    assert "/T/" not in str(blind.NEUTRAL_ROOT) and "folders" not in str(blind.NEUTRAL_ROOT)


def test_new_code_is_opaque_and_fresh():
    a, b = blind.new_code(), blind.new_code()
    assert a != b and a.startswith("b") and len(a) == 11


def test_png_roundtrip_is_deterministic():
    img = (np.arange(48 * 64 * 3) % 251).astype(np.uint8).reshape(48, 64, 3)
    assert blind.png_bytes(img) == blind.png_bytes(img.copy())


# --- strict JSON and outputs ----------------------------------------------------------------
@pytest.mark.parametrize("text,want", [('{"pick": 3}', {"pick": 3}), ('```json\n{"pick": 3}\n```', {"pick": 3})])
def test_parse_output(text, want):
    assert blind.parse_output(text) == want


@pytest.mark.parametrize("text", ['Here: {"pick": 3}', '[1, 2]', '', '{"pick": 3} done', '{"a": NaN}',
                                  '{"a": 1, "a": 2}', '{"a": {"b": 1, "b": 2}}'])
def test_parse_output_refuses_anything_else(text):
    with pytest.raises(blind.BlindError):
        blind.parse_output(text)


# --- agent files ----------------------------------------------------------------------------
def test_agent_spec_reads_the_vendored_definitions():
    p = blind.agent_spec(blind.PICKER)
    assert p["name"] == "blind-frame-picker" and p["tools"] == ["Read"] and p["model"] == blind.MODEL
    assert p["max_turns"] == 40 and p["prompt"].startswith("You pick frames")
    assert blind.agent_spec(blind.RATER)["name"] == "blind-cue-rater"


def test_agent_spec_refuses_a_definition_with_more_tools(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("---\nname: x\ntools: Read, Bash\n---\n\nbody\n")
    with pytest.raises(blind.BlindError, match="Read only"):
        blind.agent_spec(p)


# --- briefs ---------------------------------------------------------------------------------
def test_render_brief_fills_exactly_the_placeholders():
    assert blind.render_brief("A {{ONE}} and {{TWO}}.", {"ONE": "x", "TWO": "y"}) == "A x and y."
    with pytest.raises(blind.BlindError, match="missing"):
        blind.render_brief("A {{ONE}} and {{TWO}}.", {"ONE": "x"})
    with pytest.raises(blind.BlindError, match="unused"):
        blind.render_brief("A {{ONE}}.", {"ONE": "x", "TWO": "y"})
    with pytest.raises(blind.BlindError, match="placeholder"):
        blind.render_brief("A {{ONE}}.", {"ONE": "has {{THREE}}"})


Q2 = ["One (fixture)", "Two (fixture)", "Nothing in particular", "Can't tell"]


def q2_file(tmp_path):
    p = tmp_path / "q2.json"
    p.write_text(json.dumps({"schema": "p47-q2-options/1", "options": Q2}))
    return p


def test_q2_block_and_order(tmp_path):
    assert blind.q2_block(q2_file(tmp_path)) == "- One (fixture)\n- Two (fixture)\n- Nothing in particular\n- Can't tell"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "p47-q2-options/1", "options": ["A", "Can't tell", "Nothing in particular"]}))
    with pytest.raises(blind.BlindError, match="last"):
        blind.q2_block(bad)


def test_render_sealed_brief_guards_sealed_and_refuses_overwrite(tmp_path):
    tpl = tmp_path / "t.md"
    tpl.write_text("Options:\n{{Q2_OPTIONS}}\n")
    sealed = tmp_path / "sealed"
    with pytest.raises(blind.BlindError, match="sealed"):
        blind.render_sealed_brief(tpl, q2_file(tmp_path), tmp_path / "public.md", sealed_root=sealed)
    out = sealed / "briefs" / "b.md"
    r = blind.render_sealed_brief(tpl, q2_file(tmp_path), out, sealed_root=sealed)
    assert out.read_text() == "Options:\n- One (fixture)\n- Two (fixture)\n- Nothing in particular\n- Can't tell\n"
    assert r["template_sha256"] == blind.sha256_path(tpl)
    with pytest.raises(blind.BlindError, match="exists"):
        blind.render_sealed_brief(tpl, q2_file(tmp_path), out, sealed_root=sealed)
    with pytest.raises(blind.BlindError, match="sealed"):
        blind.render_sealed_brief(tpl, q2_file(tmp_path), blind.ROOT / "agents" / "x.md")


# --- contact sheets -------------------------------------------------------------------------
def test_contact_sheet_layout_and_labels():
    frames = [np.full((72, 128, 3), 40 * i, np.uint8) for i in range(5)]
    sheets = blind.contact_sheets(frames, [0.0, 0.5, 1.0, 1.5, 2.0], cols=2, rows=2, tile=(128, 72))
    assert len(sheets) == 2 and sheets[0].shape == (144, 256, 3)
    assert tuple(sheets[0][143, 127]) == (80, 80, 80)
    assert tuple(sheets[0][1, 1]) == (255, 255, 255) and tuple(sheets[0][73, 1]) == (255, 255, 255)
    assert tuple(sheets[1][100, 200]) == (128, 128, 128)


def test_sheet_times_even_spacing():
    assert blind.sheet_times(4.0, per_second=2) == [0.25, 0.75, 1.25, 1.75, 2.25, 2.75, 3.25, 3.75]


def test_validate_choices_counts_stray_keys():
    fields = {"q1": ["A", "B"], "q2": ["C", "D"]}
    assert blind.validate_choices({"items": {"x1": {"q1": "A", "q2": "D"}}, "notes": ""}, ["x1"], fields) == []
    secret = "the creature hopped"
    probs = blind.validate_choices({"items": {"x1": {"q1": "a", "q2": "D"}, secret: {}}, "notes": "", secret: 1},
                                   ["x1", "x2"], fields)
    assert any("x2" in p for p in probs) and any("x1.q1" in p for p in probs)
    assert secret not in " ".join(probs)


# --- the rater (I6, A3; round 2: fixed rounds, refs, panels from the sealed manifest) -----------
def brief(tmp_path):
    p = tmp_path / "rendered-brief.md"
    p.write_text("rendered brief")
    return p


IMG = np.zeros((36, 64, 3), np.uint8)


def probe_folder(tmp_path, round_id="probe", refs=("render-a", "render-b")):
    items = [{"ref": r, "sheets": [IMG, IMG] if k == 0 else [IMG]} for k, r in enumerate(refs)]
    return blind.build_rater_folder(items, round_id=round_id, brief=brief(tmp_path))


def ledger(round_id="probe"):
    return json.loads((Path(blind.LOGS) / "rater" / f"{round_id}.json").read_text())


def test_rounds_are_a_fixed_set(tmp_path):
    with pytest.raises(blind.BlindError, match="round"):
        probe_folder(tmp_path, round_id="probe-again")


def test_rater_codes_are_drawn_inside_and_refs_stay_sealed(tmp_path):
    st = probe_folder(tmp_path)
    text = (Path(st["folder"]) / "items.txt").read_text()
    assert "render-a" not in text and len(st["codes"]) == 2 and all(c.startswith("q") for c in st["codes"])
    assert [ln.split(":")[0] for ln in text.splitlines()] == st["codes"]
    led = ledger()
    assert led["attempts"][0]["order_seed"] == st["order_seed"] and "render-a" not in json.dumps(led)
    assert led["refs_sha256"] == blind.sha256_json(["render-a", "render-b"])
    assert blind.registry_codes("rater-probe-draft", "probe") == [st["code"]]
    with pytest.raises(blind.BlindError, match="unrecorded"):
        probe_folder(tmp_path)


def test_a_second_round_over_the_same_items_is_refused(tmp_path):
    probe_folder(tmp_path)
    with pytest.raises(blind.BlindError, match="another round"):
        probe_folder(tmp_path, round_id="draft-1")
    probe_folder(tmp_path, round_id="draft-1", refs=("render-c", "render-d"))


def test_rater_reference_must_be_the_panel_in_the_sealed_manifest(tmp_path):
    panel = tmp_path / "panel.png"
    panel.write_bytes(blind.png_bytes(IMG))
    items = [{"ref": "render-a", "panel": panel, "sheets": [IMG]}]
    with pytest.raises(blind.BlindError, match="rating-manifest"):
        blind.build_rater_folder(items, round_id="study-clips", brief=brief(tmp_path))
    man = Path(blind.SEALED) / "rating-manifest.json"
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(json.dumps({"items": [{"ref": "render-a", "panel_sha256": "0" * 64}]}))
    with pytest.raises(blind.BlindError, match="baseline panel"):
        blind.build_rater_folder(items, round_id="study-clips", brief=brief(tmp_path))
    man.write_text(json.dumps({"items": [{"ref": "render-a", "panel_sha256": blind.sha256_path(panel)}]}))
    st = blind.build_rater_folder(items, round_id="study-clips", brief=brief(tmp_path))
    assert (Path(st["folder"]) / f"{st['codes'][0]}.ref.png").read_bytes() == panel.read_bytes()


def answers(st, did="One (fixture)"):
    return {"items": {c: {"leaves_place": "Yes", "reacted_to": "The pen", "did": did} for c in st["codes"]}, "notes": ""}


def test_record_rater_seals_answers_and_commits_the_read_log(tmp_path):
    st = probe_folder(tmp_path)
    rec = run(blind.record_rater, st, tmp_path, json.dumps(answers(st)), reads=all_files(st, blind.RATER_BRIEF_NAME),
              q2_path=q2_file(tmp_path))
    assert rec["valid"], rec["problems"]
    assert json.loads((Path(blind.SEALED) / "machine-rater" / f"{st['code']}.json").read_text())["output"] == answers(st)
    a = ledger()["attempts"][0]
    assert a["status"] == "recorded" and a["read_log"]["reads"][0] == "<folder>/rater-brief.md"
    assert "One (fixture)" not in json.dumps(ledger()) and ledger()["result"]["status"] == "rated"


def test_record_rater_invalid_answers_and_unread_sheets(tmp_path):
    st = probe_folder(tmp_path)
    reads = [n for n in all_files(st, blind.RATER_BRIEF_NAME) if not n.endswith("-2.png")]
    rec = run(blind.record_rater, st, tmp_path, json.dumps(answers(st, did="Spun round")), reads=reads,
              q2_path=q2_file(tmp_path))
    assert not rec["valid"]
    assert any("never read" in p for p in rec["problems"]) and any(".did" in p for p in rec["problems"])


# --- deviation D1 (Aaron, 10 Nov, call 139): the keyframe rescue's rubric-1 round -------------------------------------------
def test_the_rescue_has_its_own_round_with_the_probe_brief(tmp_path):
    assert blind.ROUNDS["rescue"] == "probe-draft"
    assert set(blind.ROUNDS) == {"probe", "rescue", "draft-1", "draft-2", "study-baseline", "study-clips"}
    st = probe_folder(tmp_path, round_id="rescue", refs=("rescue-render",))
    assert st["kind"] == "rater-probe-draft" and len(st["codes"]) == 1
    assert ledger("rescue")["kind"] == "probe-draft"
