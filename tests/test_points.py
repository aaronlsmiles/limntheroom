"""seam/points.py: blind point prompts for the take masks and the render masks, and the render's custody."""
import json
from pathlib import Path

import numpy as np
import pytest

from blindkit import commit, custody_chain, pair_meta, run
from seam import blind, frame_pick, masks, points

H, W = 72, 128


def frames(n=10, h=H, w=W):
    return np.stack([np.full((h, w, 3), 10 * i, np.uint8) for i in range(n)])


def home(h=H, w=W):
    m = np.zeros((h, w), bool)
    m[20:40, 10:30] = True
    return m


@pytest.fixture
def d(tmp_path):
    return {"logs": blind.LOGS, "prompts": points.PROMPTS}


def rec(d, st, tmp_path, answer, name="t", **kw):
    return run(points.record, st, tmp_path, answer, name=name, **kw)


# --- take masks ---------------------------------------------------------------------------------
def test_objects_for_each_cue():
    assert points.take_objects("glass") == ["page", "home_ink", "home_gold", "home_paper", "hand", "glass"]
    assert points.take_objects("torch")[-2:] == ["torch", "standing_object"]
    with pytest.raises(blind.BlindError):
        points.take_objects("ladder")


def test_object_descriptions_carry_no_material_or_mask_names():
    for name, text in points.DESCRIPTIONS.items():
        assert not any(w in text.lower() for w in ("ink", "gold", "paper", "home", "_")), name


def prep_take(d, take="t01a", cue="glass", n=10, stride=3):
    return points.build_take_folder(frames(n), take=take, objects=points.take_objects(cue), video_sha256="v" * 64,
                                    stride=stride)


def test_take_stride_is_every_sixth_analysis_frame():
    """Hub call 130: 2.5 stills a second, so a textured 13 s take (33 stills) fits the session."""
    assert points.TAKE_STRIDE == 6


def test_take_folder_over_the_payload_budget_logs_no_attempt(d, monkeypatch):
    budget = blind.PAYLOAD_BUDGET
    monkeypatch.setattr(blind, "PAYLOAD_BUDGET", 100)
    with pytest.raises(blind.BlindError, match="budget"):
        prep_take(d)
    assert not (d["logs"] / "take-mask-points" / "t01a.json").exists()
    # Never monkeypatch.undo() here: it would also undo the conftest's redirect of the ledger roots.
    monkeypatch.setattr(blind, "PAYLOAD_BUDGET", budget)
    st = prep_take(d)                                    # the same take still has both attempts
    log = json.loads((d["logs"] / "take-mask-points" / "t01a.json").read_text())
    assert [a["code"] for a in log["steps"]["place"]["attempts"]] == [st["code"]]


def test_take_folder_and_prepared_attempt(d):
    st = prep_take(d)
    folder = Path(st["folder"])
    lines = (folder / "objects.txt").read_text().splitlines()
    assert [ln.split(":")[0] for ln in lines] == list("abcdef") and "home" not in "".join(lines)
    assert [s["frame"] for s in st["stills"]] == [0, 3, 6, 9]
    log = json.loads((d["logs"] / "take-mask-points" / "t01a.json").read_text())
    assert log["steps"]["place"]["attempts"][0]["status"] == "prepared"
    with pytest.raises(blind.BlindError, match="unrecorded"):
        prep_take(d)


TAKE_OK = {"objects": {"a": [{"still": 1, "x": 10, "y": 10, "positive": True}],
                       "b": [{"still": 1, "x": 20, "y": 30.5, "positive": True}],
                       "c": [{"still": 1, "x": 60, "y": 30, "positive": True}],
                       "d": [{"still": 1, "x": 100, "y": 30, "positive": True}],
                       "f": [{"still": 2, "x": 64, "y": 50, "positive": True},
                             {"still": 2, "x": 70, "y": 60, "positive": False},
                             {"still": 4, "x": 64, "y": 50, "positive": True}]},
           "not_found": ["e"]}


def test_record_take_writes_prompts_in_analysis_frames(d, tmp_path):
    st = prep_take(d)
    log = rec(d, st, tmp_path, json.dumps(TAKE_OK))
    assert log["steps"]["place"]["result"]["status"] == "placed"
    p = json.loads((d["prompts"] / "t01a.json").read_text())
    assert p["objects"]["glass"] == [{"frame": 3, "x": 64.0, "y": 50.0, "positive": True},
                                     {"frame": 3, "x": 70.0, "y": 60.0, "positive": False},
                                     {"frame": 9, "x": 64.0, "y": 50.0, "positive": True}]
    assert p["not_found"] == ["hand"]
    assert masks.load_prompts(d["prompts"] / "t01a.json", size=(720, 1280), n_frames=10)["glass"][0] == (3, 64.0, 50.0, True)


@pytest.mark.parametrize("bad", [
    {"objects": {}, "not_found": []},
    {**TAKE_OK, "notes": "x"},
    {"objects": {**TAKE_OK["objects"], "e": [{"still": 1, "x": 1, "y": 1, "positive": True}]}, "not_found": ["e"]},
    {"objects": {**TAKE_OK["objects"], "f": [{"still": 2, "x": 64, "y": 50, "positive": False}]}, "not_found": ["e"]},
    {"objects": {**TAKE_OK["objects"], "f": [{"still": 5, "x": 64, "y": 50, "positive": True}]}, "not_found": ["e"]},
    {"objects": {**TAKE_OK["objects"], "f": [{"still": 2, "x": 1280, "y": 50, "positive": True}]}, "not_found": ["e"]},
    {"objects": {**TAKE_OK["objects"], "f": [{"still": 2, "x": True, "y": 50, "positive": True}]}, "not_found": ["e"]},
    {"objects": {**TAKE_OK["objects"], "f": [{"still": 2, "x": 1, "y": 1, "positive": True}] * 7}, "not_found": ["e"]},
    {"objects": {**TAKE_OK["objects"], "f": [{"still": 3, "x": 1, "y": 1, "positive": False},
                                             {"still": 4, "x": 1, "y": 1, "positive": True}]}, "not_found": ["e"]},
])
def test_parse_take_points_problems(bad):
    assert points.parse_take(bad, letters=list("abcdef"), n_stills=4)[1]


def test_take_problems_never_echo_agent_keys(d, tmp_path):
    st = prep_take(d)
    secret = "it would hop onto the glass"
    bad = {"objects": {**TAKE_OK["objects"], secret: []}, "not_found": ["e", secret]}
    log = rec(d, st, tmp_path, json.dumps(bad))
    assert not log["steps"]["place"]["attempts"][0]["valid"] and secret not in json.dumps(log)


def test_take_needs_every_file_read(d, tmp_path):
    st = prep_take(d)
    reads = [r["name"] for r in st["inventory"] if r["name"] != "003.png"]
    reads = [blind.BRIEF_NAME] + [n for n in reads if n != blind.BRIEF_NAME]
    log = rec(d, st, tmp_path, json.dumps(TAKE_OK), reads=reads)
    a = log["steps"]["place"]["attempts"][0]
    assert not a["valid"] and any("003.png" in p for p in a["problems"])


def test_reject_take_from_a_fixed_list_allows_one_more(d, tmp_path):
    st = prep_take(d)
    rec(d, st, tmp_path, json.dumps(TAKE_OK))
    with pytest.raises(blind.BlindError, match="closed"):
        prep_take(d)
    with pytest.raises(blind.BlindError, match="one of"):
        points.reject_take("t01a", reason="the glass track follows the hand")
    points.reject_take("t01a", reason="wrong-object")
    assert not (d["prompts"] / "t01a.json").exists() and (d["prompts"] / "t01a.rejected1.json").exists()
    st2 = prep_take(d)
    log = rec(d, st2, tmp_path, json.dumps(TAKE_OK), name="u.jsonl")
    assert log["steps"]["place"]["result"]["status"] == "placed" and log["rejections"][0]["reason"] == "wrong-object"
    with pytest.raises(blind.BlindError, match="attempts"):
        points.reject_take("t01a", reason="lost")


# --- render masks -------------------------------------------------------------------------------
def picked(d, tmp_path, render="t01-ink", pick='{"pick": 3}', n=10):
    st = frame_pick.build_folder(frames(n, 720, 1280), render=render, home=home(720, 1280), video_sha256="v" * 64,
                                 size=(54, 96), stride=2)      # pick 3 = frame 4 below
    run(frame_pick.record, st, tmp_path, pick, name=f"pick-{render}")
    return st


def first_track(tmp_path, m, render="t01-ink", prompts_sha=None, video="v" * 64):
    p = tmp_path / f"first-{blind.new_code()}.npz"
    p1 = Path(points.PROMPTS) / "render" / f"{render}.p1.json"
    masks.save_masks(p, {"creature": m}, take=render, extra={
        "prompts_sha256": prompts_sha or (blind.sha256_path(p1) if p1.exists() else "0" * 64), "video_sha256": video})
    return p


def prep_render(d, render="t01-ink", step="place", mask=None, tmp_path=None, **kw):
    mp = first_track(tmp_path, mask, render, **kw) if mask is not None else None
    return points.build_render_folder(frames(10, 720, 1280), render=render, home=home(720, 1280), video_sha256="v" * 64,
                                      step=step, masks_path=mp)


def test_render_place_needs_a_logged_pick(d, tmp_path):
    with pytest.raises(blind.BlindError, match="no pick"):
        prep_render(d)
    picked(d, tmp_path, render="t03-ink", pick='{"pick": "none"}')
    with pytest.raises(blind.BlindError, match="none"):
        prep_render(d, render="t03-ink")


def test_render_place_needs_the_same_home(d, tmp_path):
    picked(d, tmp_path)
    other = np.zeros((720, 1280), bool)
    other[0:10, 0:10] = True
    with pytest.raises(blind.BlindError, match="home"):
        points.build_render_folder(frames(10, 720, 1280), render="t01-ink", home=other, video_sha256="v" * 64)


def test_render_place_folder_is_only_that_frame_with_its_home_outlined(d, tmp_path):
    picked(d, tmp_path)
    st = prep_render(d)
    folder = Path(st["folder"])
    assert sorted(p.name for p in folder.iterdir()) == sorted([blind.BRIEF_NAME, "task.txt", "frame.png", "frame.grid.png"])
    assert st["frame"] == 4
    import cv2
    img = cv2.cvtColor(cv2.imread(str(folder / "frame.png")), cv2.COLOR_BGR2RGB)
    assert int(img[300, 300, 0]) == 40 and (img[19:41, 9:31] != 40).any()     # the frame, with the outline on it


def run_place(d, tmp_path, answer='{"x": 700, "y": 400}'):
    picked(d, tmp_path)
    return rec(d, prep_render(d), tmp_path, answer, name="pl")


def test_render_place_then_check_then_track_then_custody(d, tmp_path):
    run_place(d, tmp_path)
    p1 = json.loads((d["prompts"] / "render" / "t01-ink.p1.json").read_text())
    assert p1["objects"] == {"creature": [{"frame": 4, "x": 700.0, "y": 400.0, "positive": True}]}
    m = np.zeros((10, 720, 1280), bool)
    m[4:, 380:420, 680:720] = True
    st = prep_render(d, step="check", mask=m, tmp_path=tmp_path)
    assert (Path(st["folder"]) / "mask.grid.png").exists() and st["first_track_sha256"]
    log = rec(d, st, tmp_path, '{"covers": true}', name="ck")
    assert log["steps"]["check"]["result"]["status"] == "covers"
    final = d["prompts"] / "render" / "t01-ink.json"
    mp = tmp_path / "final.npz"
    masks.save_masks(mp, {"creature": m}, take="t01-ink", extra={"prompts_sha256": blind.sha256_path(final),
                                                                 "video_sha256": "v" * 64})
    meta = pair_meta("t01-ink", m, final, mp)
    with pytest.raises(blind.BlindError, match="track"):
        points.custody("t01-ink", prompts=final, pair_meta=meta, creature=m)
    points.record_track("t01-ink", mp)                                    # commits its ledger entry itself
    assert points.custody("t01-ink", prompts=final, pair_meta=meta, creature=m) == 4
    lp = points._log_path("render", "t01-ink")
    lp.write_text(lp.read_text() + " ")
    with pytest.raises(blind.BlindError, match="changes"):
        points.custody("t01-ink", prompts=final, pair_meta=meta, creature=m)
    commit()
    for bad in ({**meta, "render_mask_digest": "0" * 64}, {**meta, "render_mask_file_sha256": "0" * 64},
                {"render": "t01-ink"}, None):
        with pytest.raises(blind.BlindError, match="track|another render"):
            points.custody("t01-ink", prompts=final, pair_meta=bad, creature=m)
    for bad, match in (({**meta, "prompts_sha256": "0" * 64}, "final prompt file"),
                       ({**meta, "video_sha256": "w" * 64}, "video the pick"),
                       ({**meta, "gate": {"pass": False, "sha256": "g" * 64}}, "gate"),
                       ({k: v for k, v in meta.items() if k != "gate"}, "gate"),
                       ({**meta, "creature_digest": "0" * 64}, "writer recorded")):
        with pytest.raises(blind.BlindError, match=match):
            points.custody("t01-ink", prompts=final, pair_meta=bad, creature=m)
    for c in (~m, None):
        with pytest.raises(blind.BlindError, match="writer recorded"):
            points.custody("t01-ink", prompts=final, pair_meta=meta, creature=c)
    edited = tmp_path / "edited.json"
    edited.write_text(json.dumps({"take": "t01-ink", "objects": {"creature": [
        {"frame": 4, "x": 701.0, "y": 400.0, "positive": True}]}}))
    with pytest.raises(blind.BlindError, match="logged final points"):
        points.custody("t01-ink", prompts=edited, pair_meta=meta, creature=m)


@pytest.mark.parametrize("kw,match", [({"prompts_sha": "0" * 64}, "p1"), ({"video": "w" * 64}, "video")])
def test_the_check_binds_the_first_track_to_its_prompts_and_video(d, tmp_path, kw, match):
    run_place(d, tmp_path)
    with pytest.raises(blind.BlindError, match=match):
        prep_render(d, step="check", mask=np.zeros((10, 720, 1280), bool), tmp_path=tmp_path, **kw)


@pytest.mark.parametrize("extra,match", [({"prompts_sha256": "0" * 64, "video_sha256": "v" * 64}, "final prompt"),
                                         (None, "video")])
def test_record_track_binds_the_final_prompts_and_the_video(d, tmp_path, extra, match):
    run_place(d, tmp_path)
    m = np.zeros((10, 720, 1280), bool)
    rec(d, prep_render(d, step="check", mask=m, tmp_path=tmp_path), tmp_path, '{"covers": true}', name="ck")
    final = d["prompts"] / "render" / "t01-ink.json"
    mp = tmp_path / "final.npz"
    masks.save_masks(mp, {"creature": m}, take="t01-ink",
                     extra=extra or {"prompts_sha256": blind.sha256_path(final), "video_sha256": "w" * 64})
    with pytest.raises(blind.BlindError, match=match):
        points.record_track("t01-ink", mp)


def test_render_check_adds_one_point(d, tmp_path):
    run_place(d, tmp_path)
    st = prep_render(d, step="check", mask=np.zeros((10, 720, 1280), bool), tmp_path=tmp_path)
    rec(d, st, tmp_path, '{"covers": false, "x": 720, "y": 410, "positive": false}', name="ck")
    final = json.loads((d["prompts"] / "render" / "t01-ink.json").read_text())
    assert final["objects"]["creature"][1] == {"frame": 4, "x": 720.0, "y": 410.0, "positive": False}
    with pytest.raises(blind.BlindError, match="closed"):
        prep_render(d, step="check", mask=np.zeros((10, 720, 1280), bool), tmp_path=tmp_path)


def test_two_invalid_checks_keep_the_first_point(d, tmp_path):
    run_place(d, tmp_path)
    for k in range(2):
        log = rec(d, prep_render(d, step="check", mask=np.zeros((10, 720, 1280), bool), tmp_path=tmp_path), tmp_path, "not json",
                  name=f"ck{k}")
    assert log["steps"]["check"]["result"]["status"] == "failed_kept_first"
    final = json.loads((d["prompts"] / "render" / "t01-ink.json").read_text())
    assert final["objects"]["creature"] == [{"frame": 4, "x": 700.0, "y": 400.0, "positive": True}]


def test_render_place_null_is_not_found(d, tmp_path):
    log = run_place(d, tmp_path, answer='{"x": null, "y": null}')
    assert log["steps"]["place"]["result"]["status"] == "not_found"
    with pytest.raises(blind.BlindError, match="place"):
        prep_render(d, step="check", mask=np.zeros((10, 720, 1280), bool), tmp_path=tmp_path)


@pytest.mark.parametrize("ans", ['{"x": 700}', '{"x": 700, "y": 400, "positive": true}', '{"x": -1, "y": 3}',
                                 '{"x": null, "y": 3}'])
def test_render_place_bad_outputs(d, tmp_path, ans):
    assert not run_place(d, tmp_path, answer=ans)["steps"]["place"]["attempts"][0]["valid"]


def test_check_needs_the_mask_at_the_prompt_frame(d, tmp_path):
    run_place(d, tmp_path)
    with pytest.raises(blind.BlindError, match="mask"):
        prep_render(d, step="check", mask=np.zeros((4, 720, 1280), bool), tmp_path=tmp_path)
