# Match Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thay LosslessCut, CapCut, đặt tên file và 3 terminal Temporal bằng một web app local: đánh dấu trận trên timeline, nhập tên, bấm một nút để cắt, ghép, chèn overlay và upload YouTube.

**Architecture:** Một process Python. Flask phục vụ editor (JS thuần, ES modules, không build step), stream video gốc qua HTTP Range và cung cấp API JSON. Một luồng nền chạy pipeline từng trận; mỗi bước bỏ qua nếu kết quả đã có trên đĩa. Trạng thái (phiên làm việc, job, lịch sử tên) là file JSON trong `DATA_DIR`.

**Tech Stack:** Python 3.13, uv, Flask, ffmpeg/ffprobe (đã cài qua Homebrew, có `h264_videotoolbox`), google-api-python-client, Pillow, OpenCV, pytest, ruff; JS thuần chạy trên Chrome, `node --test` (Node 22) cho logic JS thuần.

**Spec:** `docs/superpowers/specs/2026-11-20-match-editor-design.md`. Mockup đã chốt: `docs/superpowers/specs/mockups/editor-layout.html` và `docs/superpowers/specs/mockups/timeline-scrub.html`. Người làm đọc cả spec lẫn mockup liên quan trước khi làm task của mình.

## Global Constraints

- Chạy bằng đúng một lệnh: `uv run main.py`. Không thêm build step, không thêm framework frontend, không thêm dependency Python mới ngoài những gì đã có trong `pyproject.toml`.
- Server chỉ bind `127.0.0.1`.
- Không bao giờ sửa, ghi đè hoặc xoá file trong `INPUT_DIR` trong lúc xử lý. Chỉ thao tác "Lưu trữ" mới di chuyển file nguồn.
- Không bao giờ upload nếu workspace đã có `upload.json` chứa `video_id`.
- UI bám đúng mockup: bố cục 3 cột, bảng màu (biến CSS `--bg #14161a`, `--panel #1c1f25`, `--panel2 #232730`, `--line #2f3440`, `--accent #ffd400`, màu trận `#3fa7ff`, `#5ed38a`, `#ff8a4c` rồi lặp lại), chữ tiếng Việt như trong mockup.
- Thời điểm cắt lưu bằng giây (float), đã làm tròn theo frame của file nguồn.
- Định dạng tiêu đề giữ nguyên: `Nam/Hùng vs Tú/Long | Cafe Game (2026-11-20)`, ngày là ngày quay, định dạng `%Y-%m-%d`.
- Tên file trong workspace giữ nguyên: `metadata.json`, `selected.jpg`, `thumbnail.jpg`, `processed.mov`, `upload.json` (hằng số trong `utils.py`).
- Quy ước workspace hiện có được giữ: workspace là thư mục `W`, "đường dẫn video" tương ứng là `W.parent / f"{W.name}.mov"` (không cần tồn tại). Nhờ đó `uploader.py`, `thumbnail_enhancement/` và `rethumbnail.py` dùng tiếp các hàm `utils.get_*_path(video_path)`.
- YouTube API luôn được mock trong test. Test không gọi mạng.
- Trước mỗi commit: `uv run pytest -q` và `uv run ruff check .` phải sạch.
- Làm việc trên branch `feat/match-editor`, không commit thẳng vào `main`.
- Commit message theo kiểu hiện có của repo (`feat:`, `fix:`, `chore:`, `test:`), kết thúc bằng dòng `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

## Review Focus

Các tình huống spec ngầm đòi hỏi nhưng dễ bị bỏ sót. Mỗi dòng đã có test ở task ghi kèm.

1. **File nguồn không có audio, hoặc hai đoạn khác độ phân giải.** Encode vẫn phải ra video hợp lệ, không crash. (Task 5)
2. **File nguồn bị xoá hoặc đổi tên khỏi `INPUT_DIR` trong khi phiên còn tham chiếu.** App vẫn mở được, nguồn đó hiện là "thiếu", không cho đưa trận dùng nó vào hàng đợi. (Task 8)
3. **Đường dẫn lạ trong URL stream video** (`../token.json`, đường dẫn tuyệt đối). Trả 404, không đọc file ngoài `INPUT_DIR`. (Task 8)
4. **Token YouTube hết hạn hoặc bị thu hồi giữa lúc hàng đợi chạy.** Job chuyển sang lỗi với thông báo cần đăng nhập lại, luồng nền không chết, các bước trước upload của job khác vẫn chạy. (Task 7)
5. **File phiên bị hỏng hoặc ghi dở do tắt máy.** App khởi động với phiên rỗng và giữ lại file hỏng dưới tên khác, không crash và không âm thầm xoá. (Task 3)

## File Structure

```
main.py                      CLI: không tham số = chạy server; giữ auth, rethumbnail
config.py                    thêm DATA_DIR, APP_PORT, DEFAULT_TOURNAMENT, QUOTA_RETRY_HOURS; bỏ biến Temporal
utils.py                     thêm workspace_video_path(); bỏ scan theo candidates
video_prep.py                metadata từ form, chọn thumbnail theo đoạn; bỏ parse_filename
video_overlay.py             giữ phần vẽ overlay; thêm dựng lệnh render theo đoạn
media_probe.py        (mới)  ffprobe: thời lượng, fps, kích thước, có audio, ngày quay
uploader.py                  thêm resume phiên upload, phân loại lỗi quota; bỏ bước visibility
cleanup.py                   viết lại: lưu trữ workspace, xoá processed.mov, lưu trữ nguồn
app/__init__.py       (mới)
app/models.py         (mới)  Segment, Match, Session, Job + validate
app/store.py          (mới)  đọc/ghi JSON nguyên tử: phiên, job, lịch sử tên
app/pipeline.py       (mới)  các bước của một trận
app/jobs.py           (mới)  hàng đợi, luồng nền, máy trạng thái
app/server.py         (mới)  Flask app factory, API, stream video
app/static/index.html (mới)
app/static/style.css  (mới)
app/static/js/model.js    (mới)  logic thuần: đoạn, trận, hoàn tác (có test Node)
app/static/js/api.js      (mới)
app/static/js/player.js   (mới)  phát nhiều nguồn trên một trục thời gian
app/static/js/timeline.js (mới)  vẽ, zoom, scrub, kéo mép
app/static/js/matches.js  (mới)  thẻ trận, form, gợi ý tên
app/static/js/queue.js    (mới)  nút upload, hàng đợi
app/static/js/main.js     (mới)  nối các phần, phím tắt, tự lưu
tests/js/model.test.js    (mới)
Xoá: temporal/, thumbnail_ranking/, thumbnail_selector.py, web_selector/ và test tương ứng
```

---

### Task 1: Phép thử phát HEVC trong trình duyệt (cần chủ project)

Đây là cổng quyết định, không phải code sản phẩm. Kết quả quyết định có làm Task 2 hay không.

**Files:**
- Create: `scratch/playback_spike.py` (xoá ở cuối task, không commit)

- [ ] **Step 1: Viết script thử**

Một file Flask duy nhất, nhận đường dẫn video qua tham số dòng lệnh, bind `127.0.0.1:8770`. Route `/video` trả file bằng `send_file(path, conditional=True)`. Route `/` trả một trang có thẻ `<video>` chiếm ngang màn hình, một `<input type=range>` rộng toàn trang mà sự kiện `input` gán `video.currentTime`, hiển thị `currentTime` và số mili-giây từ lúc gán tới sự kiện `seeked` gần nhất, và phím `,` `.` để lùi/tới 1 frame (1/30 giây).

- [ ] **Step 2: Kiểm tra tự động phần Range**

Run: `uv run python scratch/playback_spike.py input/ms_Test1vsTest2.mov &` rồi `curl -s -o /dev/null -w "%{http_code} %{size_download}\n" -H "Range: bytes=0-1023" http://127.0.0.1:8770/video`
Expected: `206 1024`

- [ ] **Step 3: Nhờ chủ project thử với file quay thật**

Điều phối viên yêu cầu chủ project chạy script với một file quay thật dài hàng chục phút, mở bằng Chrome, kéo thanh trượt qua lại và bấm `,` `.`. Ghi lại: có phát được không, độ trễ seek điển hình, cảm giác kéo có dùng được không.

- [ ] **Step 4: Quyết định**

- Phát được và độ trễ seek điển hình dưới 150ms: bỏ qua Task 2.
- Không phát được, hoặc kéo giật không dùng nổi: làm Task 2.

Ghi kết quả thành một dòng ở đầu mục "Task 2" của file plan này rồi xoá `scratch/`.

---

### Task 2 (có điều kiện): Bản proxy để xem trong editor

**Kết quả Task 1 (2026-11-20): BỎ QUA task này.** Chủ project đã thử file quay thật 1GB và 2GB trên Chrome, phát và kéo con trỏ ổn. Editor phát thẳng file gốc.

Chỉ làm nếu Task 1 kết luận cần. Nếu bỏ qua, `media_probe.playback_path(source)` ở Task 4 trả luôn file gốc.

**Files:**
- Create: `proxy.py`
- Test: `tests/test_proxy.py`

**Interfaces:**
- Produces: `proxy.proxy_path(source: Path) -> Path` (trong `config.DATA_DIR / "proxies"`, tên gồm stem, kích thước file và mtime của nguồn để nguồn đổi thì proxy cũ mất hiệu lực); `proxy.build_proxy_command(source: Path, dest: Path) -> list[str]`; `proxy.ensure_proxy(source: Path) -> Path` (tạo nếu chưa có, ghi ra file tạm rồi rename).

- [ ] **Step 1: Viết test thất bại**

```python
def test_build_proxy_command_is_short_gop_h264_720p(tmp_path):
    cmd = build_proxy_command(tmp_path / "a.mov", tmp_path / "a.mp4")
    joined = " ".join(cmd)
    assert "scale=-2:720" in joined
    assert "-g 15" in joined
    assert "h264_videotoolbox" in joined
    assert "+faststart" in joined

def test_proxy_path_changes_when_source_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    src = tmp_path / "a.mov"; src.write_bytes(b"x")
    first = proxy_path(src)
    src.write_bytes(b"xy")
    assert proxy_path(src) != first
```

- [ ] **Step 2: Chạy, xác nhận fail** — Run: `uv run pytest tests/test_proxy.py -q` — Expected: FAIL vì chưa có module `proxy`.
- [ ] **Step 3: Viết `proxy.py`** theo interface trên. Proxy giữ nguyên fps và audio (AAC) để timecode khớp file gốc.
- [ ] **Step 4: Chạy lại** — Expected: PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add editor proxy generation for sources the browser cannot scrub"`

Khi task này được làm, Task 8 thêm trạng thái "đang tạo bản xem trước" cho nguồn và Task 10 hiện trạng thái đó ở cột trái.

---

### Task 3: Dọn Temporal và code thừa; mô hình dữ liệu và lưu trữ

**Files:**
- Delete: `temporal/`, `thumbnail_ranking/`, `thumbnail_selector.py`, `web_selector/`, `tests/test_main.py`, `tests/test_quality_filter.py`, `tests/test_thumbnail_ranking_pipeline.py`
- Modify: `pyproject.toml`, `config.py`, `constants.py`, `utils.py`, `main.py`, `env.template`, `.gitignore`, `tests/conftest.py`
- Create: `app/__init__.py`, `app/models.py`, `app/store.py`
- Test: `tests/test_models.py`, `tests/test_store.py`

**Interfaces:**
- Produces (config): `config.DATA_DIR: Path` (env `DATA_DIR`, mặc định `./data`, tự tạo), `config.APP_PORT: int` (env `APP_PORT`, mặc định `8765`), `config.DEFAULT_TOURNAMENT = "Cafe Game"`, `config.QUOTA_RETRY_HOURS: int` (mặc định `4`). Bỏ `TEMPORAL_SERVER_ADDRESS`, `TOP_RANKED_CANDIDATES_NUM`, `THUMBNAIL_SELECTOR_PORT`.
- Produces (utils): `utils.workspace_video_path(workspace_dir: Path) -> Path` trả `workspace_dir.parent / f"{workspace_dir.name}.mov"`.
- Produces (models, đều là dataclass có `to_dict()` và `from_dict()`):
  - `Segment(source: str, start: float, end: float)`; `source` là tên file trong `INPUT_DIR`.
  - `Match(id: str, match_type: str, team1: list[str], team2: list[str], tournament: str, segments: list[Segment])`; `match_type` thuộc `ms|md|ws|wd|xd`; `id` do client sinh, chỉ gồm `[a-z0-9-]`.
  - `Session(sources: list[str], matches: list[Match], selected_match_id: str | None)`.
  - `Job(match: Match, recorded_date: str, status: str, step: str, progress: float, error: str | None, youtube_link: str | None, queued_at: str)`; `status` thuộc `queued|running|waiting_quota|error|done`; `step` thuộc `metadata|select_thumbnail|render_thumbnail|encode|upload|set_thumbnail|cleanup`.
  - `validate_session(session: Session, durations: dict[str, float]) -> list[str]` trả danh sách lỗi (rỗng nếu hợp lệ).
  - `match_problems(match: Match) -> list[str]` trả lý do trận chưa upload được (rỗng nếu đủ điều kiện).
- Produces (store): `load_session() -> Session`, `save_session(s: Session) -> None`, `workspace_dir(match_id: str) -> Path` (`DATA_DIR/workspaces/<id>`), `load_job(match_id) -> Job | None`, `save_job(job: Job) -> None`, `list_jobs() -> list[Job]` (sắp theo `queued_at`), `delete_workspace(match_id) -> None`, `load_players() -> dict[str, int]`, `record_players(names: list[str]) -> None`, `seed_players_from_completed() -> None`.

- [ ] **Step 1: Xoá code thừa và dependency**

Xoá các thư mục và file ở mục Delete. Gỡ khỏi `pyproject.toml`: `temporalio`, `torch`, `torchvision`, `clip` (cả mục `[tool.uv.sources]`), `imagehash`. Với `tqdm` và `requests`: chạy `grep -rn "import tqdm\|from tqdm\|import requests\|from requests" --include='*.py' . | grep -v .venv`, chỉ gỡ nếu không còn kết quả. Chuyển `pytest` và `freezegun` sang nhóm `dev`. Gỡ các hằng `WORKFLOW_STAGE_*` và `TEMPORAL_TASK_QUEUE` khỏi `constants.py`; gỡ `CANDIDATES_DIR`, `TOP_RANKED_CANDIDATES_DIR` và hai hàm get tương ứng khỏi `utils.py`. Rút `main.py` còn hai lệnh `auth` và `rethumbnail` (lệnh mặc định thêm ở Task 8). Chạy `uv sync`.

- [ ] **Step 2: Cập nhật config, env và gitignore** theo interface trên. `tests/conftest.py` đặt thêm `os.environ["DATA_DIR"]` trỏ vào một thư mục tạm. `env.template` bỏ biến Temporal và `TOP_RANKED_CANDIDATES_NUM`, thêm `DATA_DIR`, `APP_PORT`. `.gitignore` thêm `data/`.

- [ ] **Step 3: Xác nhận phần còn lại vẫn chạy**

Run: `uv run pytest -q && uv run ruff check .`
Expected: toàn bộ test còn lại PASS, ruff sạch.

- [ ] **Step 4: Commit** — `git commit -m "chore: remove Temporal and unused thumbnail ranking code"`

- [ ] **Step 5: Viết test thất bại cho models**

```python
DUR = {"a.mov": 100.0, "b.mov": 50.0}

def _m(id="m1", segs=(("a.mov", 1.0, 5.0),), t1=("Nam",), t2=("Tú",)):
    return Match(id=id, match_type="ms", team1=list(t1), team2=list(t2),
                 tournament="Cafe Game", segments=[Segment(*s) for s in segs])

def test_valid_session_has_no_errors():
    assert validate_session(Session(["a.mov"], [_m()], None), DUR) == []

def test_overlap_across_matches_is_rejected():
    s = Session(["a.mov"], [_m("m1", [("a.mov", 1, 5)]), _m("m2", [("a.mov", 4, 8)])], None)
    assert any("chồng" in e for e in validate_session(s, DUR))

def test_touching_segments_are_allowed():
    s = Session(["a.mov"], [_m("m1", [("a.mov", 1, 5)]), _m("m2", [("a.mov", 5, 8)])], None)
    assert validate_session(s, DUR) == []

def test_segment_outside_source_or_reversed_is_rejected():
    assert validate_session(Session(["a.mov"], [_m(segs=[("a.mov", 90, 101)])], None), DUR)
    assert validate_session(Session(["a.mov"], [_m(segs=[("a.mov", 5, 5)])], None), DUR)

def test_segment_of_unselected_source_is_rejected():
    assert validate_session(Session(["a.mov"], [_m(segs=[("b.mov", 1, 2)])], None), DUR)

def test_match_id_must_be_filesystem_safe():
    assert validate_session(Session(["a.mov"], [_m(id="../x")], None), DUR)

def test_match_problems():
    assert match_problems(_m()) == []
    assert match_problems(_m(t2=()))            # thiếu tên một bên
    assert match_problems(_m(segs=()))          # chưa có đoạn

def test_roundtrip_keeps_vietnamese_names():
    m = _m(t1=("Tú", "Hùng"))
    assert Match.from_dict(m.to_dict()) == m
```

- [ ] **Step 6: Chạy, xác nhận fail** — Run: `uv run pytest tests/test_models.py -q` — Expected: FAIL vì chưa có `app.models`.
- [ ] **Step 7: Viết `app/models.py`.** Thông báo lỗi bằng tiếng Việt; lỗi chồng đoạn chứa chữ "chồng".
- [ ] **Step 8: Chạy lại** — Expected: PASS.

- [ ] **Step 9: Viết test thất bại cho store** (mỗi test `monkeypatch.setattr(config, "DATA_DIR", tmp_path)`)

```python
def test_session_roundtrip(tmp_path, monkeypatch): ...
    # save_session rồi load_session trả về đối tượng bằng nhau

def test_missing_session_file_gives_empty_session(): ...
    # load_session() == Session([], [], None)

def test_corrupt_session_file_is_kept_aside_not_deleted(tmp_path, monkeypatch):
    (tmp_path / "session.json").write_text("{ half written")
    assert load_session() == Session([], [], None)
    assert list(tmp_path.glob("session.json.corrupt-*"))

def test_save_session_is_atomic(tmp_path, monkeypatch):
    # sau save_session không còn file *.tmp trong DATA_DIR

def test_jobs_listed_in_queue_order(): ...
    # hai job với queued_at khác nhau, list_jobs trả theo thứ tự tăng dần

def test_record_players_counts_usage():
    record_players(["Nam", "Tú"]); record_players(["Nam"])
    assert load_players() == {"Nam": 2, "Tú": 1}

def test_seed_players_from_completed_runs_once(tmp_path, monkeypatch):
    # COMPLETED_DIR/x/metadata.json có team1_names ["An"], team2_names ["Bình"]
    # seed hai lần liên tiếp, load_players() == {"An": 1, "Bình": 1}
```

- [ ] **Step 10: Chạy, xác nhận fail** — Expected: FAIL vì chưa có `app.store`.
- [ ] **Step 11: Viết `app/store.py`.** Ghi JSON ra file tạm cùng thư mục rồi `os.replace`. `session.json` và `players.json` nằm trực tiếp trong `DATA_DIR`; job lưu ở `workspace_dir(id) / "job.json"`. `seed_players_from_completed` chỉ chạy khi `players.json` chưa tồn tại.
- [ ] **Step 12: Chạy lại** — Run: `uv run pytest -q && uv run ruff check .` — Expected: PASS, sạch.
- [ ] **Step 13: Commit** — `git commit -m "feat: add session, match and job models with JSON store"`

---

### Task 4: Thông tin nguồn, metadata từ form, chọn thumbnail theo đoạn

**Files:**
- Create: `media_probe.py`
- Modify: `video_prep.py`
- Test: `tests/test_media_probe.py`, sửa `tests/test_video_prep.py`, `tests/test_auto_thumbnail.py`

**Interfaces:**
- Consumes: `Segment` (Task 3).
- Produces:
  - `media_probe.SourceInfo(name: str, duration: float, fps: float, width: int, height: int, has_audio: bool, recorded_at: str)` (dataclass có `to_dict()`; `recorded_at` là ISO 8601).
  - `media_probe.probe(path: Path) -> SourceInfo`; có cache theo `(path, size, mtime)`.
  - `media_probe.playback_path(path: Path) -> Path`: trả `path` (hoặc proxy nếu Task 2 được làm).
  - `video_prep.create_metadata_from_fields(match_type: str, team1: list[str], team2: list[str], tournament: str, match_date: str) -> MatchMetadata`.
  - `video_prep.sample_timestamps(segments: list[Segment], count: int) -> list[tuple[str, float]]`.
  - `video_prep.select_thumbnail_from_segments(segments: list[Segment], source_dir: Path, output_path: Path) -> None`.

- [ ] **Step 1: Viết test thất bại**

```python
# tests/test_media_probe.py — mock subprocess.run trả JSON ffprobe
def test_probe_reads_streams_and_creation_time(mock_run, tmp_path):
    # streams: video 1920x1080 r_frame_rate "30000/1001", một stream audio
    # format: duration "61.5", tags.creation_time "2026-11-19T12:02:03.000000Z"
    info = probe(src)
    assert (info.width, info.height, info.has_audio) == (1920, 1080, True)
    assert info.fps == pytest.approx(29.97, abs=0.01)
    assert info.duration == 61.5
    assert info.recorded_at.startswith("2026-11-19")

def test_probe_falls_back_to_mtime_and_detects_no_audio(mock_run, tmp_path):
    # không có tags, không có stream audio; os.utime đặt mtime 2026-11-18
    assert info.has_audio is False
    assert info.recorded_at.startswith("2026-11-18")

# tests/test_video_prep.py
def test_metadata_from_fields_matches_existing_format():
    m = create_metadata_from_fields("md", ["Nam", "Hùng"], ["Tú", "Long"], "Cafe Game", "2026-11-20")
    assert m.title == "Nam/Hùng vs Tú/Long | Cafe Game (2026-11-20)"
    assert m.match_type == "Men's Doubles"
    assert "#mensdoubles" in m.description and "#cafegame" in m.description
    assert m.category == "17"

def test_metadata_rejects_unknown_match_type():
    with pytest.raises(ValueError): create_metadata_from_fields("zz", ["A"], ["B"], "X", "2026-01-01")

# tests/test_auto_thumbnail.py
def test_sample_timestamps_stay_inside_kept_segments():
    segs = [Segment("a.mov", 10, 20), Segment("b.mov", 0, 30)]
    pts = sample_timestamps(segs, 8)
    assert len(pts) == 8
    for src, t in pts:
        assert (src == "a.mov" and 10 <= t <= 20) or (src == "b.mov" and 0 <= t <= 30)
    assert pts == sorted(pts, key=lambda p: (p[0] != "a.mov", p[1]))   # theo thứ tự trận

def test_select_thumbnail_from_segments_skips_if_output_exists(tmp_path): ...
def test_select_thumbnail_from_segments_picks_sharpest(mock_extract, tmp_path): ...
```

- [ ] **Step 2: Chạy, xác nhận fail** — Run: `uv run pytest tests/test_media_probe.py tests/test_video_prep.py tests/test_auto_thumbnail.py -q`
- [ ] **Step 3: Viết code.** `sample_timestamps` trải đều `count` điểm trên tổng thời lượng được giữ, bỏ 10% đầu và 10% cuối như thuật toán cũ, rồi ánh xạ từng điểm về `(source, t)`. `select_thumbnail_from_segments` dùng lại `score_frame`, `_extract_frame_at` và công thức điểm tổng hợp hiện có. Xoá `parse_filename`, `create_metadata`, `create_and_store_metadata`, `create_workspace`, `auto_select_thumbnail` và các test của chúng; giữ các test của `score_frame`, `_extract_frame_at`, `create_title`, `create_description`.
- [ ] **Step 4: Chạy lại** — Run: `uv run pytest -q && uv run ruff check .` — Expected: PASS, sạch.
- [ ] **Step 5: Commit** — `git commit -m "feat: build metadata from form fields and pick thumbnails from kept segments"`

---

### Task 5: Encode một lần: cắt, ghép, overlay

**Files:**
- Modify: `video_overlay.py`
- Test: sửa `tests/test_video_overlay.py`, tạo `tests/test_render_integration.py`

**Interfaces:**
- Consumes: `Segment`, `media_probe.probe`.
- Produces:
  - `video_overlay.RenderInput(path: str, start: float, end: float, has_audio: bool, width: int, height: int)`.
  - `video_overlay.overlay_timing(total_duration: float) -> tuple[bool, float]` trả `(show_thanks, thanks_start)`.
  - `video_overlay.build_render_command(inputs: list[RenderInput], cafe_png: str, thanks_png: str | None, thanks_start: float, logo_path: str | None, logo_size: int | None, output_path: str, use_hardware: bool) -> list[str]`.
  - `video_overlay.render_match(segments: list[Segment], source_dir: Path, output_path: Path, progress: Callable[[float], None] | None = None) -> str`.

- [ ] **Step 1: Viết test thất bại**

```python
def _inp(path="a.mov", s=10.0, e=25.0, audio=True, w=1920, h=1080):
    return RenderInput(path, s, e, audio, w, h)

def test_overlay_timing():
    assert overlay_timing(100.0) == (True, 88.0)
    assert overlay_timing(24.0) == (False, 12.0)

def test_each_segment_is_a_seeked_input():
    cmd = build_render_command([_inp(s=10, e=25), _inp("b.mov", 0, 5.5)], "c.png", None, 0, None, None, "o.mov", True)
    j = " ".join(cmd)
    assert "-ss 10.000 -t 15.000 -i a.mov" in j
    assert "-ss 0.000 -t 5.500 -i b.mov" in j
    assert "concat=n=2:v=1:a=1" in j

def test_overlays_follow_concat_and_use_trimmed_time():
    cmd = build_render_command([_inp(), _inp()], "c.png", "t.png", 18.0, "logo.png", 192, "o.mov", True)
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.index("concat=") < fc.index("overlay=")
    assert "enable='lte(t,12)'" in fc and "enable='gte(t,18.000)'" in fc
    assert "scale=192:-1" in fc

def test_audio_is_reencoded_not_copied():
    cmd = build_render_command([_inp()], "c.png", None, 0, None, None, "o.mov", True)
    assert cmd[cmd.index("-c:a") + 1] == "aac"

def test_segment_without_audio_gets_silence():
    cmd = build_render_command([_inp(audio=False), _inp()], "c.png", None, 0, None, None, "o.mov", True)
    assert "anullsrc" in " ".join(cmd)

def test_mismatched_resolution_is_scaled_to_first_segment():
    cmd = build_render_command([_inp(w=1920, h=1080), _inp(w=1280, h=720)], "c.png", None, 0, None, None, "o.mov", True)
    assert "scale=1920:1080" in cmd[cmd.index("-filter_complex") + 1]

def test_encoder_choice():
    hw = build_render_command([_inp()], "c.png", None, 0, None, None, "o.mov", True)
    sw = build_render_command([_inp()], "c.png", None, 0, None, None, "o.mov", False)
    assert "h264_videotoolbox" in hw and "libx264" in sw
```

```python
# tests/test_render_integration.py — @pytest.mark.skipif(shutil.which("ffmpeg") is None, ...)
# Tạo 2 file nguồn 6 giây bằng `ffmpeg -f lavfi -i testsrc=size=320x240:rate=30 -f lavfi -i sine`,
# và một file thứ ba không có audio.
def test_two_segments_one_file(tmp_path):      # [1,3] + [4,5] -> thời lượng 3.0 ± 0.1
def test_segments_across_two_files(tmp_path):  # a[4,6] + b[0,1.5] -> 3.5 ± 0.1
def test_source_without_audio(tmp_path):       # silent[0,2] + a[0,2] -> 4.0 ± 0.1, đầu ra có stream audio
def test_progress_reaches_100(tmp_path):       # callback được gọi, giá trị cuối >= 99
def test_existing_output_is_not_rerendered(tmp_path):
def test_failed_render_leaves_no_output_file(tmp_path):  # nguồn không tồn tại -> RuntimeError, output_path không tồn tại
```

- [ ] **Step 2: Chạy, xác nhận fail** — Run: `uv run pytest tests/test_video_overlay.py tests/test_render_integration.py -q`
- [ ] **Step 3: Viết code.** Mỗi đoạn là một input riêng với `-ss` và `-t` đặt trước `-i` (seek chính xác tới frame khi encode lại). Mỗi input qua `scale` (về kích thước đoạn đầu), `setsar=1`, `fps` (về fps đoạn đầu) trước `concat`. Đoạn không có audio dùng `anullsrc` cắt đúng thời lượng. Audio ra `aac` 192k. Encoder video giữ đúng tham số hiện có. `render_match` ghi ra `<output>.partial` rồi rename khi ffmpeg thành công; thử phần cứng trước, lỗi thì thử `libx264` như code cũ; đọc `-progress pipe:1` để tính phần trăm từ `out_time_us`. Xoá `add_video_overlays` và `_run_ffmpeg_overlay` cùng test của chúng; giữ nguyên các hàm vẽ overlay và test của chúng.
- [ ] **Step 4: Chạy lại** — Run: `uv run pytest -q && uv run ruff check .` — Expected: PASS, sạch.
- [ ] **Step 5: Commit** — `git commit -m "feat: cut, join and overlay match segments in a single encode"`

---

### Task 6: Upload nối tiếp được và phân loại lỗi quota

**Files:**
- Modify: `uploader.py`, `custom_exceptions.py`
- Test: sửa `tests/test_uploader.py`

**Interfaces:**
- Produces:
  - `custom_exceptions.QuotaExceededError`, `custom_exceptions.AuthRequiredError`.
  - `uploader.UPLOAD_SESSION_FILE = "upload_session.json"` (trong workspace, chứa `{"resumable_uri": str, "file_size": int}`).
  - `uploader.is_quota_error(err: HttpError) -> bool`.
  - `uploader.upload_video_with_idempotency(video_path: str, heartbeat_callback=None) -> UploadedRecord`: chữ ký giữ nguyên, hành vi mở rộng như dưới.
- Bỏ: `update_video_visibility_for_video`, `get_videos_ready_for_upload` và test của chúng.

- [ ] **Step 1: Viết test thất bại**

```python
def test_is_quota_error():
    assert is_quota_error(_http_error(429, "rateLimitExceeded"))
    assert is_quota_error(_http_error(403, "quotaExceeded"))
    assert is_quota_error(_http_error(403, "uploadLimitExceeded"))
    assert not is_quota_error(_http_error(403, "forbidden"))
    assert not is_quota_error(_http_error(500, "backendError"))

def test_session_uri_is_saved_before_upload_finishes(tmp_path):
    # request.next_chunk: lần 1 trả (status 50%, None) và đặt request.resumable_uri = "https://up/1",
    # lần 2 ném ConnectionError
    # -> upload_session.json tồn tại với resumable_uri "https://up/1"; upload.json chưa tồn tại

def test_restart_resumes_saved_session_instead_of_starting_new(tmp_path):
    # workspace có upload_session.json khớp kích thước file
    # -> request được gán resumable_uri đã lưu và _in_error_state = True trước lần next_chunk đầu;
    #    kết quả trả video_id, upload.json được ghi, upload_session.json bị xoá

def test_expired_session_falls_back_to_fresh_upload(tmp_path):
    # next_chunk trên phiên cũ ném HttpError 404 -> xoá upload_session.json, tạo request mới, upload thành công

def test_session_for_different_file_size_is_ignored(tmp_path): ...

def test_quota_http_error_becomes_quota_exceeded(tmp_path):
    # insert().next_chunk ném HttpError 403 uploadLimitExceeded -> QuotaExceededError

def test_missing_or_revoked_token_becomes_auth_required(tmp_path):
    # get_client ném RuntimeError("OAuth token not found...") -> AuthRequiredError
    # next_chunk ném google.auth.exceptions.RefreshError -> AuthRequiredError

def test_already_uploaded_still_raises(tmp_path): ...   # test hiện có, giữ
```

- [ ] **Step 2: Chạy, xác nhận fail** — Run: `uv run pytest tests/test_uploader.py -q`
- [ ] **Step 3: Viết code.** Cơ chế resume dựa trên `googleapiclient.http.HttpRequest.next_chunk`: khi `resumable_uri` đã có và `_in_error_state` là `True`, thư viện gửi PUT rỗng để hỏi server đã nhận bao nhiêu byte rồi gửi tiếp. Đọc `.venv/lib/python3.13/site-packages/googleapiclient/http.py` quanh dòng 1000-1125 để xác nhận trước khi viết. Ghi `upload_session.json` ngay sau lần `next_chunk` đầu tiên gán `resumable_uri`.
- [ ] **Step 4: Chạy lại** — Run: `uv run pytest -q && uv run ruff check .` — Expected: PASS, sạch.
- [ ] **Step 5: Commit** — `git commit -m "feat: resume interrupted YouTube uploads and classify quota errors"`

---

### Task 7: Pipeline một trận và hàng đợi

**Files:**
- Create: `app/pipeline.py`, `app/jobs.py`
- Modify: `cleanup.py`, `rethumbnail.py` (chỉ nếu cần để chạy với workspace mới)
- Test: `tests/test_pipeline.py`, `tests/test_jobs.py`, sửa `tests/test_cleanup.py`, `tests/test_rethumbnail.py`

**Interfaces:**
- Consumes: mọi thứ từ Task 3 đến 6.
- Produces:
  - `pipeline.STEPS: list[str]` đúng thứ tự `metadata, select_thumbnail, render_thumbnail, encode, upload, set_thumbnail, cleanup`.
  - `pipeline.run_step(job: Job, step: str, progress: Callable[[float], None]) -> None`.
  - `cleanup.archive_workspace(match_id: str) -> Path`: xoá `processed.mov` và `upload_session.json`, chuyển workspace vào `COMPLETED_DIR` (tên thư mục đích `<recorded_date>_<match_id>`), giữ `job.json` và ghi thêm `segments.json`.
  - `cleanup.archive_source(name: str) -> Path`: chuyển file từ `INPUT_DIR` sang `COMPLETED_DIR/sources/`, không ghi đè file trùng tên (thêm hậu tố số).
  - `jobs.JobQueue(clock=time.time)` với: `enqueue(matches: list[Match]) -> list[Job]`, `retry(match_id: str) -> None`, `unqueue(match_id: str) -> Match` (ném `ValueError` nếu job đang chạy hoặc đã có `video_id`), `snapshot() -> list[dict]`, `locked_match_ids() -> set[str]`, `run_once() -> bool` (xử lý tối đa một bước của một job, trả `False` nếu không còn gì làm), `start() -> None` (luồng daemon gọi `run_once` lặp lại), `stop() -> None`.

- [ ] **Step 1: Viết test thất bại cho pipeline** (mock `render_match`, `select_thumbnail_from_segments`, `render_thumbnail`, uploader)

```python
def test_metadata_step_writes_metadata_json_with_recorded_date(ws):
    run_step(job, "metadata", noop)
    assert utils.get_metadata(utils.workspace_video_path(ws)).title.endswith("(2026-11-19)")

def test_each_step_skips_when_its_output_exists(ws):
    # tạo sẵn selected.jpg / thumbnail.jpg / processed.mov -> hàm tương ứng không được gọi

def test_upload_step_never_calls_uploader_when_upload_json_has_video_id(ws): ...

def test_cleanup_step_archives_workspace_and_records_players(ws):
    # sau bước cleanup: thư mục nằm trong COMPLETED_DIR, không còn processed.mov,
    # có metadata.json, thumbnail.jpg, upload.json, segments.json; load_players() có tên hai đội

def test_archived_workspace_works_with_rethumbnail(ws):
    # scan_completed_workspaces(COMPLETED_DIR) tìm thấy workspace vừa lưu trữ khi có ảnh thủ công bên trong
```

- [ ] **Step 2: Viết test thất bại cho hàng đợi** (pipeline được thay bằng hàm giả ghi lại lời gọi; `clock` giả)

```python
def test_job_runs_all_steps_in_order_then_done(): ...
def test_jobs_run_one_at_a_time_in_queue_order(): ...
def test_progress_and_step_are_persisted_to_job_json(): ...

def test_error_stops_that_job_and_queue_moves_on():
    # job1 lỗi ở encode -> status "error", error chứa thông báo; job2 vẫn chạy tới done

def test_retry_resumes_from_failed_step_not_from_start(): ...

def test_quota_puts_job_in_waiting_and_blocks_later_uploads_only():
    # job1 ném QuotaExceededError ở upload -> "waiting_quota"
    # job2 vẫn chạy metadata..encode, rồi dừng trước upload với "waiting_quota"

def test_waiting_quota_retries_after_configured_hours():
    # clock + QUOTA_RETRY_HOURS giờ -> run_once thử lại upload

def test_auth_error_marks_job_error_and_worker_survives():
    # upload ném AuthRequiredError -> status "error", error chứa "đăng nhập";
    # run_once tiếp theo vẫn xử lý được bước trước upload của job khác

def test_restart_resumes_unfinished_jobs():
    # tạo job.json với status "running" step "encode" trên đĩa, dựng JobQueue mới -> job chạy tiếp từ encode
    # job "waiting_quota" được thử lại ngay khi khởi động

def test_unqueue_removes_workspace_and_returns_match(): ...
def test_unqueue_refused_when_running_or_uploaded(): ...
def test_enqueue_rejects_match_with_problems_or_already_queued(): ...
```

- [ ] **Step 3: Chạy, xác nhận fail** — Run: `uv run pytest tests/test_pipeline.py tests/test_jobs.py -q`
- [ ] **Step 4: Viết code.** `enqueue` chụp lại bản sao `Match` và `recorded_date` (ngày của `probe(...).recorded_at` của file nguồn chứa đoạn đầu tiên) vào `Job`. Một `threading.Lock` bảo vệ trạng thái hàng đợi; pipeline chạy ngoài lock. Mọi exception không lường trước trong một bước đều bị bắt, ghi vào `job.error`, không làm chết luồng.
- [ ] **Step 5: Chạy lại** — Run: `uv run pytest -q && uv run ruff check .` — Expected: PASS, sạch.
- [ ] **Step 6: Commit** — `git commit -m "feat: add per-match pipeline and resumable background job queue"`

---

### Task 8: Server và API

**Files:**
- Create: `app/server.py`, `app/static/index.html` (trang tạm một dòng, thay ở Task 10)
- Modify: `main.py`, `auth_service.py`
- Test: `tests/test_server.py`, `tests/test_main.py` (mới)

**Interfaces:**
- Consumes: Task 3 đến 7.
- Produces `server.create_app(queue: JobQueue) -> Flask` với các route:

| Method và đường dẫn | Trả về |
|---|---|
| `GET /` | `index.html` |
| `GET /media/<name>` | file trong `INPUT_DIR`, hỗ trợ Range |
| `GET /api/bootstrap` | `{auth, defaults: {tournament, privacy}, sources, session, jobs, players}` |
| `GET /api/sources` | `[SourceInfo + {missing: bool, archivable: bool}]`, sắp theo `recorded_at` |
| `PUT /api/session` | `{ok: true}` hoặc 400 `{errors: [...]}`; 409 nếu thay đổi một trận đang khoá |
| `GET /api/jobs` | `queue.snapshot()` |
| `POST /api/jobs` body `{match_ids: [...]}` | 200 danh sách job; 400 kèm lý do nếu có trận không đủ điều kiện |
| `POST /api/jobs/<id>/retry` | 200 |
| `POST /api/jobs/<id>/unqueue` | 200, hoặc 409 nếu đang chạy hoặc đã upload |
| `POST /api/sources/<name>/archive` | 200, hoặc 409 nếu còn trận chưa xong dùng nguồn này |
| `GET /api/auth` | `{ok: bool, channel: str | None}` |
| `POST /api/auth/login` | chạy luồng OAuth hiện có trong một luồng riêng, trả 202 |

- Produces: `auth_service.auth_status() -> dict` (`{"ok": bool, "channel": str | None}`, không ném exception, có cache 60 giây); `main.py` không tham số: gọi `store.seed_players_from_completed()`, dựng `JobQueue`, `start()`, mở trình duyệt tới `http://127.0.0.1:<APP_PORT>/`, chạy Flask trên `127.0.0.1` với `threaded=True`.

- [ ] **Step 1: Viết test thất bại** (Flask test client, `INPUT_DIR` và `DATA_DIR` trỏ vào `tmp_path`, `probe` được mock)

```python
def test_media_supports_range(client, source):
    r = client.get("/media/a.mov", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.data) == 10

@pytest.mark.parametrize("name", ["../token.json", "%2e%2e%2ftoken.json", "/etc/hosts", "sub/../../x.mov", "notes.txt"])
def test_media_refuses_anything_outside_input_dir(client, name):
    assert client.get(f"/media/{name}").status_code == 404

def test_bootstrap_shape(client):
    assert set(client.get("/api/bootstrap").json) == {"auth", "defaults", "sources", "session", "jobs", "players"}

def test_put_session_persists_and_validates(client):
    # PUT hợp lệ -> 200 và load_session() khớp; PUT có hai đoạn chồng nhau -> 400 với errors

def test_session_with_missing_source_still_loads(client):
    # phiên tham chiếu "gone.mov" không còn trong INPUT_DIR
    # -> /api/bootstrap 200, sources có mục name "gone.mov" với missing True
    # -> POST /api/jobs cho trận dùng "gone.mov" trả 400

def test_put_session_cannot_change_locked_match(client): ...   # 409
def test_enqueue_then_jobs_lists_it(client): ...
def test_unqueue_conflict_when_uploaded(client): ...           # 409
def test_archive_source_refused_while_matches_pending(client): ...  # 409
def test_archive_source_moves_file_and_drops_it_from_session(client): ...
def test_players_sorted_by_usage(client): ...
def test_auth_endpoint_reports_not_logged_in_without_token(client): ...

# tests/test_main.py
def test_default_command_binds_localhost_only(monkeypatch):
    # chặn Flask.run, gọi main() không tham số -> host == "127.0.0.1", port == config.APP_PORT
```

- [ ] **Step 2: Chạy, xác nhận fail** — Run: `uv run pytest tests/test_server.py tests/test_main.py -q`
- [ ] **Step 3: Viết code.** `/media/<name>` chỉ chấp nhận tên trùng khớp chính xác với một file có đuôi hỗ trợ đang nằm trực tiếp trong `INPUT_DIR` (so với kết quả `utils.scan_videos`), rồi `send_file(media_probe.playback_path(p), conditional=True)`. `archivable` là `True` khi nguồn có ít nhất một trận và mọi trận dùng nó đều có job `done`.
- [ ] **Step 4: Chạy lại** — Run: `uv run pytest -q && uv run ruff check .` — Expected: PASS, sạch.
- [ ] **Step 5: Thử khói** — Run: `uv run main.py &` rồi `curl -s http://127.0.0.1:8765/api/bootstrap | head -c 300` — Expected: JSON có khoá `sources` chứa `ms_Test1vsTest2.mov`. Tắt process sau khi thử.
- [ ] **Step 6: Commit** — `git commit -m "feat: add local web server and JSON API for the match editor"`

---

### Task 9: Logic editor thuần (JS)

**Files:**
- Create: `app/static/js/model.js`, `tests/js/model.test.js`

**Interfaces:**
- Produces (ES module, không đụng DOM). Trục thời gian chung: các nguồn nối tiếp theo thứ tự, `layout = [{name, offset, duration, fps}]`.
  - `buildLayout(sources) -> layout`; `totalDuration(layout)`; `toLocal(layout, t) -> {name, time}`; `toGlobal(layout, name, time) -> t`; `snap(layout, t) -> t` làm tròn về frame của nguồn tại `t`.
  - `createEditor(session, layout) -> state`; `state` gồm `session`, `open` (`{matchId, start}` hoặc `null`), `undo` (ngăn xếp, tối đa 200).
  - Các thao tác trả `state` mới, không sửa `state` cũ: `markIn(state, t)`, `markOut(state, t)`, `newMatch(state, t, idFactory)`, `selectMatch(state, id)`, `deleteSegmentAt(state, t)`, `moveEdge(state, matchId, segIndex, "start"|"end", t)`, `updateMatch(state, id, fields)`, `removeSource(state, name)`, `undo(state)`.
  - `segmentsOnTimeline(state) -> [{matchId, segIndex, start, end, open}]` theo trục chung, dùng để vẽ.
  - `keptDuration(match)`; `previewTitle(match, date)`; `matchProblems(match)` (cùng quy tắc với Python).
  - Tham số `locked: Set<string>`: mọi thao tác sửa một trận đang khoá trả lại `state` cũ.

- [ ] **Step 1: Viết test thất bại** (`node:test`, `node:assert/strict`). Layout mẫu: `a.mov` dài 100 giây, `b.mov` dài 50 giây, cùng 30fps.

```js
test('I rồi O tạo một đoạn của trận đang chọn')            // {source:'a.mov', start:10, end:20}
test('O rồi I giữa trận tạo hai đoạn, khúc giữa bị bỏ')    // I@10 O@20 I@30 O@40 -> 2 đoạn, keptDuration 20
test('đoạn mở chạy qua vạch nối được tách thành hai đoạn liền nhau cùng trận')
                                                           // I@90 O@110 -> a[90,100] + b[0,10]
test('N đóng đoạn đang mở, tạo và chọn trận mới, kế thừa loại trận trước')
test('N khi trận đang chọn chưa có đoạn nào thì không tạo thêm trận rỗng')
test('đoạn mới bị chặn ở mép đoạn kề bên, không chồng lên trận khác')   // m1[10,20]; m2 I@15 -> bắt đầu từ 20
test('I trong một đoạn đã đóng của trận đang chọn dời điểm vào')
test('O trong một đoạn đã đóng của trận đang chọn dời điểm ra')
test('O khi không có đoạn mở và con trỏ ngoài mọi đoạn thì không đổi gì')
test('O trước điểm I thì không tạo đoạn âm')
test('moveEdge kẹp theo đoạn kề bên, theo biên file nguồn, và giữ đoạn dài ít nhất 1 frame')
test('deleteSegmentAt xoá đúng đoạn dưới con trỏ')
test('mọi điểm được làm tròn theo frame')                  // 10.017 -> 10.0333…
test('undo hoàn tác từng thao tác theo thứ tự ngược lại, kể cả updateMatch')
test('thao tác trên trận đang khoá không đổi state')
test('removeSource xoá các đoạn của nguồn đó và bỏ trận rỗng không có tên')
test('previewTitle khớp định dạng Python')                 // 'Nam/Hùng vs Tú/Long | Cafe Game (2026-11-20)'
test('matchProblems báo thiếu tên một bên và chưa có đoạn')
```

- [ ] **Step 2: Chạy, xác nhận fail** — Run: `node --test tests/js/` — Expected: FAIL vì chưa có `model.js`.
- [ ] **Step 3: Viết `model.js`.**
- [ ] **Step 4: Chạy lại** — Run: `node --test tests/js/` — Expected: mọi test PASS.
- [ ] **Step 5: Commit** — `git commit -m "feat: add pure editor model for segments, matches and undo"`

---

### Task 10: Giao diện editor: khung, player, timeline, phím tắt

Chuyển hai mockup thành trang thật. Lấy nguyên CSS và cấu trúc HTML từ mockup làm điểm xuất phát, thay dữ liệu giả bằng dữ liệu từ API.

**Files:**
- Create: `app/static/index.html` (thay trang tạm), `app/static/style.css`, `app/static/js/api.js`, `app/static/js/player.js`, `app/static/js/timeline.js`, `app/static/js/main.js`

**Interfaces:**
- Consumes: `model.js` (Task 9), API (Task 8).
- Produces:
  - `api.js`: một hàm cho mỗi route ở Task 8 (`bootstrap()`, `saveSession(session)`, `listJobs()`, `enqueue(ids)`, `retry(id)`, `unqueue(id)`, `archiveSource(name)`, `authStatus()`, `login()`), ném `Error` kèm `errors` khi server trả 4xx.
  - `player.js`: `createPlayer(container, layout) -> {seek(t), time(), play(), pause(), toggle(), shuttle(dir), step(frames), onTime(cb), setLayout(layout)}` với `t` trên trục chung.
  - `timeline.js`: `createTimeline(container, {onSeek, onMoveEdge, onSelectMatch}) -> {render(state, layout, playhead), zoomBy(delta, anchorX), fit()}`.
  - `main.js`: giữ `state`, nối mọi thứ, xử lý phím, tự lưu; export `getState()` và `dispatch(fn)` cho `matches.js` và `queue.js` ở Task 11.

- [ ] **Step 1: Khung trang và cột nguồn.** Thanh trên, 3 cột như mockup. Cột trái liệt kê nguồn theo giờ quay với thời lượng; tick để thêm vào phiên theo thứ tự quay, số thứ tự ① ② như mockup. Bỏ tick một nguồn đang có đoạn thì hỏi xác nhận rồi gọi `removeSource`. Nguồn `missing` hiện mờ kèm chữ "Không tìm thấy file". Cột phải để trống cho Task 11.
- [ ] **Step 2: Player nhiều nguồn.** Một thẻ `<video>` cho mỗi nguồn trong layout, chỉ hiện thẻ của nguồn đang chứa con trỏ; khi phát qua hết một nguồn thì tự chuyển sang nguồn kế. Timecode `giờ:phút:giây:frame` và nhãn trạng thái ("● ĐANG GIỮ · Trận 2" khi có đoạn mở, ngược lại "○ Không giữ") như mockup. `shuttle`: `L` lần lượt 1×, 2×, 4×, 8×; `K` dừng; `J` lùi bằng cách seek lùi liên tục theo `requestAnimationFrame` (trình duyệt không phát ngược được).
- [ ] **Step 3: Timeline.** Chuyển nguyên hành vi của `mockups/timeline-scrub.html`: thanh tổng quan với khung nhìn, thước chia vạch tự đổi theo mức zoom, zoom neo theo chuột bằng `⌘`/`Ctrl` + cuộn, thanh trượt, nút `+` `−` "Vừa màn hình", rê chuột hiện timecode, bấm giữ và kéo để scrub, tự cuộn khi kéo sát mép, vạch nối giữa các nguồn kèm tên file. Thêm so với mockup: đoạn đang mở vẽ bằng nền sọc kéo dài tới con trỏ; bấm trong vòng 7px quanh mép đoạn là kéo mép (`moveEdge`), ngoài ra là scrub; bấm vào thân đoạn chọn trận đó; timeline tự cuộn theo con trỏ khi đang phát; trận đang khoá vẽ mờ và không kéo mép được. Trong lúc scrub, gọi `player.seek` tối đa một lần mỗi frame hiển thị.
- [ ] **Step 4: Phím tắt và tự lưu.** Đúng bảng phím ở mục 4.3 của spec. Phím không kích hoạt khi tiêu điểm nằm trong ô nhập; `Esc` đưa tiêu điểm về editor. `⌘Z` gọi `undo`. Mọi thay đổi `state.session` được lưu bằng `api.saveSession` sau 1 giây không đổi; ô trạng thái trên thanh trên hiện "Đang lưu…", "Đã lưu", hoặc "Lưu thất bại" kèm lỗi. Bảng phím tắt dưới timeline như mockup, thêm `Delete`.
- [ ] **Step 5: Kiểm tra tự động** — Run: `node --test tests/js/ && uv run pytest -q && uv run ruff check .` — Expected: PASS, sạch.
- [ ] **Step 6: Kiểm tra bằng tay trên Chrome.** Chép `input/ms_Test1vsTest2.mov` thành một file thứ hai trong `input/` để có 2 nguồn (xoá bản chép sau khi thử). Chạy `uv run main.py` và đi hết danh sách sau, ghi kết quả từng dòng vào báo cáo:
  1. Tick 2 nguồn: timeline dài bằng tổng hai file, có vạch nối.
  2. Phát chạy liền qua vạch nối.
  3. `I` / `O` tạo đoạn; `O` rồi `I` tạo khúc bỏ ở giữa; `N` tạo trận mới khác màu.
  4. Giữ một đoạn chạy qua vạch nối: thành hai đoạn liền nhau cùng màu.
  5. Zoom hết cỡ, kéo con trỏ: khung video đổi theo từng frame, timecode khớp.
  6. Kéo mép đoạn: bị chặn ở đoạn kề bên.
  7. `⌘Z` hoàn tác lần lượt các thao tác trên.
  8. Tải lại trang: mọi đoạn và trận còn nguyên.
  9. Console của trình duyệt không có lỗi.
- [ ] **Step 7: Commit** — `git commit -m "feat: add editor UI with multi-source player, zoomable timeline and shortcuts"`

---

### Task 11: Giao diện: thẻ trận, form, hàng đợi

**Files:**
- Create: `app/static/js/matches.js`, `app/static/js/queue.js`
- Modify: `app/static/index.html`, `app/static/style.css`, `app/static/js/main.js`

**Interfaces:**
- Consumes: `getState()`, `dispatch(fn)` từ `main.js`; `updateMatch`, `selectMatch`, `keptDuration`, `previewTitle`, `matchProblems` từ `model.js`; `api.js`.
- Produces: `matches.render(state, {players, locked, recordedDates})`; `queue.render(jobs)`; `queue.startPolling()`.

- [ ] **Step 1: Thẻ trận** như cột phải của `mockups/editor-layout.html`: viền trái theo màu trận, số đoạn và thời lượng sau cắt, 5 nút loại trận, hai ô chip tên, ô giải (mặc định lấy từ `defaults.tournament`), xem trước tiêu đề với ngày quay của nguồn chứa đoạn đầu tiên, cảnh báo lấy từ `matchProblems`. Bấm thẻ chọn trận và làm sáng các đoạn của nó trên timeline. Trận đang khoá hiện ổ khoá và không sửa được. Mỗi thẻ có nút xoá trận (hỏi xác nhận nếu trận có đoạn).
- [ ] **Step 2: Ô chip tên và gợi ý.** `Enter` hoặc `,` thêm chip; `Backspace` ở ô rỗng xoá chip cuối; `Tab` sang đội bên kia; `Esc` về editor. Gợi ý lọc theo tiền tố không phân biệt hoa thường và không phân biệt dấu tiếng Việt (so sánh sau `normalize('NFD')` và bỏ dấu), xếp theo số lần dùng, bỏ tên đã có trong trận, tối đa 5; `↓` `↑` chọn, `Enter` nhận. Phím `Enter` ở editor đưa tiêu điểm vào ô đội 1 của trận đang chọn.
- [ ] **Step 3: Nút upload và hàng đợi.** Nút "Xử lý & upload N trận đã đủ thông tin" đếm các trận không khoá và không có vấn đề; tắt khi N = 0 hoặc chưa đăng nhập YouTube. Bấm thì lưu phiên ngay rồi gọi `api.enqueue`. Hàng đợi poll `api.listJobs()` mỗi giây khi còn job chưa `done`, mỗi 10 giây khi không còn. Mỗi dòng: tiêu đề trận, nhãn bước bằng tiếng Việt kèm phần trăm cho `encode` và `upload`, thanh tiến độ; `done` hiện "✓ Xong · mở YouTube" là link; `error` hiện thông báo lỗi, nút "Thử lại" và "Đưa về chỉnh sửa"; `waiting_quota` hiện "Chờ quota YouTube, sẽ tự thử lại" và nút "Thử lại"; `queued` có nút "Đưa về chỉnh sửa".
- [ ] **Step 4: Thanh trên và lưu trữ nguồn.** Ô trạng thái YouTube: "● YouTube đã đăng nhập" kèm tên kênh, hoặc nút "Đăng nhập YouTube" gọi `api.login()` rồi poll `api.authStatus()`. Ô mặc định hiện `defaults.tournament` và `defaults.privacy` (chỉ đọc). Nguồn có `archivable` hiện nút "Lưu trữ" ở cột trái.
- [ ] **Step 5: Kiểm tra tự động** — Run: `node --test tests/js/ && uv run pytest -q && uv run ruff check .` — Expected: PASS, sạch.
- [ ] **Step 6: Kiểm tra bằng tay trên Chrome**, không upload thật: chạy app với `token.json` tạm đổi tên để ở trạng thái chưa đăng nhập, ghi kết quả từng dòng vào báo cáo:
  1. Nhập tên có dấu ("Tú", "Hùng"), gõ "tu" thấy gợi ý "Tú".
  2. Xem trước tiêu đề đổi theo từng chip và theo loại trận.
  3. Trận thiếu tên hiện cảnh báo và không được đếm vào nút upload.
  4. Chưa đăng nhập: nút upload tắt, thanh trên hiện nút đăng nhập.
  5. Tải lại trang: tên, loại trận, giải còn nguyên.
  6. Phím tắt editor không kích hoạt khi đang gõ tên; `Esc` trả lại phím tắt.
  7. Console không có lỗi.
  Trả `token.json` về tên cũ sau khi thử.
- [ ] **Step 7: Commit** — `git commit -m "feat: add match cards, player name suggestions and upload queue UI"`

---

### Task 12: Tài liệu và chạy thử đầu cuối

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `env.template`

- [ ] **Step 1: Cập nhật tài liệu.** `CLAUDE.md` và `README.md` mô tả kiến trúc mới: một lệnh `uv run main.py`, các lệnh `auth` và `rethumbnail`, sơ đồ pipeline ở mục 5 của spec, danh sách file chính theo mục File Structure của plan này, lệnh test gồm cả `node --test tests/js/`. Xoá mọi nhắc tới Temporal, worker, 3 terminal, `list`, `select`, quy ước đặt tên file.
- [ ] **Step 2: Rà soát lần cuối**

Run: `grep -rniE "temporal|thumbnail_ranking|web_selector|parse_filename" --include='*.py' --include='*.md' --include='*.toml' --include='*.template' . | grep -v -E "^./(\.venv|docs/superpowers|openspec)/"`
Expected: không có kết quả.

Run: `uv run pytest -q && node --test tests/js/ && uv run ruff check . && uv run ruff format --check .`
Expected: PASS, sạch.

- [ ] **Step 3: Commit** — `git commit -m "docs: describe the match editor architecture and workflow"`

- [ ] **Step 4: Chạy thử đầu cuối với chủ project.** Điều phối viên nhờ chủ project chạy đúng kịch bản ở mục 10 của spec với video thật và `VIDEO_PRIVACY_STATUS=private`: một video dài 3 trận cộng một trận tách làm 2 file, một trận có bỏ khúc giữa, tắt app giữa lúc upload rồi mở lại. Đối chiếu 6 tiêu chí hoàn thành; ghi lại tiêu chí nào đạt và tiêu chí nào chưa.
