# Toggle Dev / Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chọn Dev (upload `private`) hoặc Production (upload `public`) bằng toggle trên editor, và chỉ còn một file `.env`.

**Architecture:** Mode hiện tại lưu ở `DATA_DIR/mode.json`. Khi bấm upload, trình duyệt gửi mode đang hiển thị; server ghi mode vào `job.json` của từng trận, và bước upload lấy privacy từ mode của job đó. Hai mode không khác nhau ở bất kỳ điểm nào khác.

**Tech Stack:** Python 3 + Flask, pytest; JS thuần (ES modules), `node --test`.

**Spec:** `docs/superpowers/specs/2026-11-20-mode-toggle-design.md`

## Global Constraints

- `config.MODES = {"dev": "private", "production": "public"}`; mode mặc định ở mọi chỗ thiếu/hỏng là `"dev"`.
- Hai mode chỉ khác nhau privacy. Không thêm khác biệt nào khác (thư mục, tên thư mục lưu trữ, gợi ý tên, số frame).
- Không bao giờ gọi YouTube thật: không `POST /api/jobs`, không `POST /api/auth/login`, không `main.py auth` khi kiểm tra tay. Test luôn mock YouTube.
- Không sửa, chuyển hay xoá file trong `INPUT_DIR`.
- Không chạy app với `DATA_DIR` thật (chủ kênh có thể đang chạy). Kiểm tra tay dùng lệnh ở Task 3, Step 7.
- Chuỗi hiển thị cho người dùng viết tiếng Việt có dấu; comment và docstring tiếng Anh như code hiện có.
- Sau mỗi task: `uv run pytest`, `node --test tests/js/`, `uv run ruff check .`, `uv run ruff format .` đều sạch.
- Giữa Task 1 và Task 3 nút upload trên trình duyệt sẽ bị server từ chối (thiếu `mode`); đó là trạng thái trung gian có chủ ý.

## Review Focus

1. Tab cũ còn mở sau khi nâng cấp gửi `POST /api/jobs` không có `mode` → 400, không trận nào vào hàng đợi (test ở Task 1).
2. `job.json` cũ không có `mode`, hoặc có giá trị lạ như `"prod"` → job được coi là `dev`, upload `private` (test ở Task 1).
3. `mode.json` là JSON hợp lệ nhưng sai nội dung (`{"mode": "x"}`, `[]`) → về `dev`, file hỏng được giữ lại dạng `.corrupt-*` (test ở Task 2).
4. `PUT /api/mode` thất bại (mất kết nối) → toggle và chữ trên nút upload vẫn ở mode cũ, không lệch với server (test ở Task 3).
5. Người dùng theo thói quen chạy `APP_ENV=production uv run main.py` → app vẫn chạy với `.env`, in cảnh báo rằng `APP_ENV` không còn tác dụng (test ở Task 4).

---

### Task 1: Privacy đi theo mode của từng trận

**Files:**
- Modify: `config.py` (thêm `MODES`, `DEFAULT_MODE`; bỏ `VIDEO_PRIVACY_STATUS`)
- Modify: `app/models.py` (`Job.mode`)
- Modify: `uploader.py` (`_insert_request`, `upload`, `upload_video_with_idempotency`)
- Modify: `app/pipeline.py:91-102` (`_upload`)
- Modify: `app/jobs.py:89-127` (`JobQueue.enqueue`)
- Modify: `app/server.py` (`parse_match_ids` hoặc hàm mới cạnh nó, `enqueue`, `bootstrap`)
- Test: `tests/test_models.py`, `tests/test_uploader.py`, `tests/test_pipeline.py`, `tests/test_jobs.py`, `tests/test_server.py`

**Interfaces:**
- Produces:
  - `config.MODES: dict[str, str] = {"dev": "private", "production": "public"}`, `config.DEFAULT_MODE = "dev"`
  - `Job.mode: str = config.DEFAULT_MODE` (trường cuối cùng của dataclass, có giá trị mặc định để các chỗ dựng `Job(...)` hiện có không phải sửa)
  - `JobQueue.enqueue(matches: list[Match], mode: str) -> list[Job]`
  - `uploader.upload_video_with_idempotency(video_path, heartbeat_callback=None, *, privacy_status: str = "private")`
  - `POST /api/jobs` body: `{"match_ids": [...], "mode": "dev" | "production"}`
  - Mỗi job trả về cho trình duyệt (`GET /api/jobs`, bootstrap) có thêm khoá `"mode"`.

- [ ] **Step 1: Viết test hỏng cho `Job.mode`** trong `tests/test_models.py`

```python
def test_job_mode_round_trips():
    d = _job_dict()            # helper: a valid job dict as the file's other tests build it
    d["mode"] = "production"
    assert Job.from_dict(d).mode == "production"
    assert Job.from_dict(d).to_dict()["mode"] == "production"


@pytest.mark.parametrize("stored", [None, "prod", "", 3])
def test_job_without_a_known_mode_is_dev(stored):
    d = _job_dict()
    if stored is None:
        d.pop("mode", None)
    else:
        d["mode"] = stored
    assert Job.from_dict(d).mode == "dev"
```

- [ ] **Step 2: Chạy** `uv run pytest tests/test_models.py -k mode -v` — mong đợi FAIL (`Job` chưa có `mode`).

- [ ] **Step 3: Thêm `MODES`, `DEFAULT_MODE` vào `config.py`; thêm trường `mode` vào `Job`**; `Job.from_dict` nhận `d.get("mode")` nếu nó là khoá của `config.MODES`, ngược lại `config.DEFAULT_MODE`. Xoá `VIDEO_PRIVACY_STATUS` khỏi `config.py`.

- [ ] **Step 4: Viết test hỏng cho uploader** trong `tests/test_uploader.py`, theo cách các test hiện có mock client YouTube:

```python
@pytest.mark.parametrize("privacy", ["private", "public"])
def test_upload_sends_the_given_privacy(privacy, ...):
    upload_video_with_idempotency(str(video), privacy_status=privacy)
    body = client.videos().insert.call_args.kwargs["body"]
    assert body["status"]["privacyStatus"] == privacy


def test_upload_is_private_when_no_privacy_is_given(...):
    upload_video_with_idempotency(str(video))
    body = client.videos().insert.call_args.kwargs["body"]
    assert body["status"]["privacyStatus"] == "private"
```

- [ ] **Step 5: Truyền `privacy_status` xuyên suốt `uploader.py`**: `upload_video_with_idempotency(..., *, privacy_status="private")` → `upload(..., *, privacy_status)` → `_insert_request(youtube_client, video_path, metadata, privacy_status)` (cả hai chỗ gọi ở dòng 157 và 172). Không còn chỗ nào đọc `config.VIDEO_PRIVACY_STATUS`.

- [ ] **Step 6: Viết test hỏng cho pipeline** trong `tests/test_pipeline.py` (cạnh `fake_upload` hiện có ở dòng ~97):

```python
@pytest.mark.parametrize("mode,privacy", [("dev", "private"), ("production", "public")])
def test_upload_step_uses_the_privacy_of_the_jobs_mode(mode, privacy, monkeypatch, ...):
    seen = {}
    def fake_upload(video_path, progress=None, *, privacy_status):
        seen["privacy"] = privacy_status
    monkeypatch.setattr(uploader, "upload_video_with_idempotency", fake_upload)
    job = _job(); job.mode = mode
    # make processed.mov exist as the neighbouring upload test does
    pipeline.run_step(job, "upload", lambda p: None)
    assert seen["privacy"] == privacy
```

- [ ] **Step 7: Sửa `_upload` trong `app/pipeline.py`** để gọi `uploader.upload_video_with_idempotency(str(vp), progress, privacy_status=config.MODES[job.mode])`. Sửa các `fake_upload` hiện có trong `tests/test_pipeline.py` cho nhận keyword này.

- [ ] **Step 8: Viết test hỏng cho hàng đợi và server**

`tests/test_jobs.py`:
```python
def test_enqueue_stamps_the_mode_on_each_job(...):
    jobs = queue.enqueue([match_a, match_b], "production")
    assert [j.mode for j in jobs] == ["production", "production"]
    assert store.load_job(match_a.id).mode == "production"


def test_retry_keeps_the_jobs_mode(...):
    # a production job put in "error", then queue.retry(id)
    assert store.load_job(id).mode == "production"
```

`tests/test_server.py`:
```python
@pytest.mark.parametrize("body", [
    {"match_ids": ["m1"]},
    {"match_ids": ["m1"], "mode": "prod"},
    {"match_ids": ["m1"], "mode": None},
])
def test_enqueue_without_a_valid_mode_is_refused(body, ...):
    res = client.post("/api/jobs", json=body, headers=EDITOR)
    assert res.status_code == 400
    assert res.get_json()["errors"] == ["Chế độ upload không hợp lệ, hãy tải lại trang"]
    assert queue.snapshot() == []


def test_enqueue_passes_the_mode_to_the_queue(...):
    res = client.post("/api/jobs", json={"match_ids": ["m1"], "mode": "production"}, headers=EDITOR)
    assert res.get_json()[0]["mode"] == "production"
```
Sửa mọi lời gọi `queue.enqueue([...])` và `POST /api/jobs` hiện có trong hai file test cho có mode `"dev"`. Trong `tests/test_server.py:205` bỏ `"privacy"` khỏi `defaults` mong đợi.

- [ ] **Step 9: Sửa `JobQueue.enqueue(matches, mode)`** (ghi `mode` vào `Job`; `ValueError` nếu `mode not in config.MODES`) **và `app/server.py`**: `enqueue()` đọc `mode` từ body, kiểm tra trước mọi việc khác sau khi parse id, `ApiError(400, ["Chế độ upload không hợp lệ, hãy tải lại trang"])` nếu sai; `bootstrap()` bỏ `"privacy"` khỏi `defaults`.

- [ ] **Step 10: Chạy** `uv run pytest && uv run ruff check . && uv run ruff format .` — mong đợi tất cả PASS; `grep -rn VIDEO_PRIVACY_STATUS --include="*.py" .` (trừ `.venv`) không còn kết quả.

- [ ] **Step 11: Commit** — `feat: upload privacy follows each job's mode`

---

### Task 2: Lưu mode hiện tại và API đổi mode

**Files:**
- Modify: `app/store.py` (`MODE_FILE`, `load_mode`, `save_mode`)
- Modify: `app/server.py` (`bootstrap`, route mới `PUT /api/mode`)
- Test: `tests/test_store.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `config.MODES`, `config.DEFAULT_MODE` (Task 1)
- Produces:
  - `store.load_mode() -> str`, `store.save_mode(mode: str) -> None`; file `DATA_DIR/mode.json` chứa `{"mode": "dev"}`
  - `GET /api/bootstrap` có thêm `"mode": "dev" | "production"` và `"modes": {"dev": "private", "production": "public"}`
  - `PUT /api/mode` body `{"mode": ...}` → 200 `{"mode": ...}`; 400 `{"errors": ["Chế độ không hợp lệ"]}` nếu sai

- [ ] **Step 1: Viết test hỏng** trong `tests/test_store.py`

```python
def test_mode_defaults_to_dev_when_nothing_is_stored():
    assert store.load_mode() == "dev"


def test_mode_round_trips():
    store.save_mode("production")
    assert store.load_mode() == "production"


@pytest.mark.parametrize("content", ['{"mode": "x"}', "[]", '{"mode": 3}', "not json"])
def test_unusable_mode_file_falls_back_to_dev_and_is_kept(content):
    path = config.DATA_DIR / "mode.json"
    path.write_text(content)
    assert store.load_mode() == "dev"
    assert not path.exists()
    assert list(config.DATA_DIR.glob("mode.json.corrupt-*"))


def test_save_mode_refuses_an_unknown_mode():
    with pytest.raises(ValueError):
        store.save_mode("prod")
```

- [ ] **Step 2: Chạy** `uv run pytest tests/test_store.py -k mode -v` — mong đợi FAIL.

- [ ] **Step 3: Viết `load_mode` / `save_mode` trong `app/store.py`** dùng `_load` và `_write_json` sẵn có; hàm parse raise `ValueError` khi nội dung không phải `{"mode": <khoá của config.MODES>}`, nhờ đó `_load` tự đổi tên file hỏng.

- [ ] **Step 4: Viết test hỏng** trong `tests/test_server.py`

```python
def test_bootstrap_reports_mode_and_modes(...):
    data = client.get("/api/bootstrap").get_json()
    assert data["mode"] == "dev"
    assert data["modes"] == {"dev": "private", "production": "public"}


def test_put_mode_stores_it(...):
    res = client.put("/api/mode", json={"mode": "production"}, headers=EDITOR)
    assert res.status_code == 200 and res.get_json() == {"mode": "production"}
    assert client.get("/api/bootstrap").get_json()["mode"] == "production"


@pytest.mark.parametrize("body", [{"mode": "prod"}, {}, None, []])
def test_put_mode_refuses_an_unknown_mode(body, ...):
    res = client.put("/api/mode", json=body, headers=EDITOR)
    assert res.status_code == 400
    assert res.get_json()["errors"] == ["Chế độ không hợp lệ"]
    assert store.load_mode() == "dev"


def test_put_mode_needs_the_editor_header(...):
    assert client.put("/api/mode", json={"mode": "production"}).status_code == 403


def test_changing_mode_does_not_change_queued_jobs(...):
    # enqueue m1 with mode "dev", then PUT /api/mode production
    assert store.load_job("m1").mode == "dev"
```

- [ ] **Step 5: Thêm route `PUT /api/mode` và hai khoá mới của bootstrap** trong `app/server.py`.

- [ ] **Step 6: Chạy** `uv run pytest && uv run ruff check . && uv run ruff format .` — mong đợi PASS.

- [ ] **Step 7: Commit** — `feat: store the current mode and expose it over the API`

---

### Task 3: Toggle trên editor

**Files:**
- Create: `app/static/js/mode.js`
- Modify: `app/static/js/api.js` (`setMode`, `enqueue`)
- Modify: `app/static/js/queue.js` (chữ nút upload, nhãn privacy của từng dòng, gửi mode)
- Modify: `app/static/js/main.js:107` và `:480-496` (nối toggle, bỏ dòng "Mặc định")
- Modify: `app/static/index.html:14` (thay `#defaults-pill` bằng `<span class="mode" id="mode"></span>`)
- Modify: `app/static/style.css`
- Test: `tests/js/mode.test.js` (mới), `tests/js/queue.test.js`

**Interfaces:**
- Consumes: bootstrap `mode`, `modes`; `PUT /api/mode`; `POST /api/jobs` cần `mode`; job có `mode` (Task 1, 2)
- Produces:
  - `api.setMode(mode)` → `PUT /api/mode`; `api.enqueue(ids, mode)` gửi `{ match_ids: ids, mode }`
  - `mode.js`: `createModeState(initial, save)` → `{ get(), set(mode) }`; `set` gọi `await save(mode)`, thành công thì đổi và trả `true`, `save` ném lỗi thì giữ nguyên mode cũ và trả `false`; gọi `set` khi một lần `set` khác chưa xong trả `false` ngay, không gọi `save`.
  - `mode.js`: `createModeToggle(el, { modes, state, onChange })` vẽ hai nút vào `el` và gọi `onChange()` sau mỗi lần đổi thành công.
  - `queue.js`: `export function goLabel(n, privacy)`, `export function jobPrivacy(job, modes)`; `createQueue` nhận thêm `deps.getMode()` và `deps.modes`.

- [ ] **Step 1: Viết test hỏng** `tests/js/mode.test.js`

```js
import test from 'node:test';
import assert from 'node:assert/strict';
import { createModeState } from '../../app/static/js/mode.js';

test('đổi mode thành công thì lưu rồi mới đổi', async () => {
  const saved = [];
  const s = createModeState('dev', async (m) => { saved.push(m); });
  assert.equal(await s.set('production'), true);
  assert.equal(s.get(), 'production');
  assert.deepEqual(saved, ['production']);
});

test('lưu mode thất bại thì vẫn ở mode cũ', async () => {
  const s = createModeState('dev', async () => { throw new Error('mất kết nối'); });
  assert.equal(await s.set('production'), false);
  assert.equal(s.get(), 'dev');
});

test('đang lưu thì không nhận thêm lần đổi khác', async () => {
  let release;
  let calls = 0;
  const s = createModeState('dev', () => { calls += 1; return new Promise((r) => { release = r; }); });
  const first = s.set('production');
  assert.equal(await s.set('dev'), false);
  release();
  assert.equal(await first, true);
  assert.equal(calls, 1);
});

test('chọn lại mode đang dùng thì không gọi server', async () => {
  let calls = 0;
  const s = createModeState('dev', async () => { calls += 1; });
  assert.equal(await s.set('dev'), true);
  assert.equal(calls, 0);
});
```

Thêm vào `tests/js/queue.test.js`:
```js
test('nút upload ghi rõ privacy', () => {
  assert.equal(goLabel(3, 'public'), 'Xử lý & upload 3 trận · public');
  assert.equal(goLabel(0, 'private'), 'Xử lý & upload 0 trận · private');
});

test('nhãn privacy của một trận theo mode của nó, thiếu thì private', () => {
  const modes = { dev: 'private', production: 'public' };
  assert.equal(jobPrivacy({ mode: 'production' }, modes), 'public');
  assert.equal(jobPrivacy({ mode: 'dev' }, modes), 'private');
  assert.equal(jobPrivacy({}, modes), 'private');
  assert.equal(jobPrivacy({ mode: 'prod' }, modes), 'private');
});
```

- [ ] **Step 2: Chạy** `node --test tests/js/` — mong đợi FAIL (chưa có `mode.js`, `goLabel`, `jobPrivacy`).

- [ ] **Step 3: Viết `mode.js`, `api.setMode`, `api.enqueue(ids, mode)`, `goLabel`, `jobPrivacy`.** `createModeToggle` vẽ hai `<button type="button">` với chữ `Dev · private` và `Production · public` (privacy lấy từ `modes`), nút đang chọn có `aria-pressed="true"`; cả hai `disabled` trong lúc đang lưu; khi `set` trả `false` do lỗi, đặt `title` của `el` là `Chưa đổi được chế độ, hãy thử lại`. Phần tử `el` mang `data-mode` bằng mode hiện tại để CSS tô màu.

- [ ] **Step 4: Nối vào `queue.js`.** `renderGo` dùng `goLabel(n, deps.modes[deps.getMode()])` thay chuỗi cũ ở dòng 253 (chữ "Đang đưa vào hàng đợi…" giữ nguyên). `enqueue()` lấy `const mode = deps.getMode()` một lần ở đầu hàm và gọi `api.enqueue(ids, mode)`. `rowHtml` thêm `<span class="privacy {privacy}">{privacy}</span>` cho mọi dòng, với `privacy = jobPrivacy(job, deps.modes)`.

- [ ] **Step 5: Nối vào `main.js`, `index.html`, `style.css`.** Trong `main.js`: bỏ dòng 107; tạo `modeState = createModeState(boot.mode, api.setMode)` và `createModeToggle($('mode'), { modes: boot.modes, state: modeState, onChange: () => queue && queue.renderGo() })`; truyền `getMode: () => modeState.get()` và `modes: boot.modes` vào `deps` của `createQueue`. CSS: `.mode[data-mode="production"]` và nhãn `.privacy.public` dùng `var(--danger)` (viền + chữ) để nổi bật; Dev và `.privacy.private` dùng màu `.pill` trung tính.

- [ ] **Step 6: Chạy** `node --test tests/js/ && uv run pytest` — mong đợi PASS.

- [ ] **Step 7: Kiểm tra tay trên server tạm** (không đụng `DATA_DIR` thật, không gọi YouTube, **không bấm nút upload**):

```bash
T=$(mktemp -d) && mkdir -p $T/in $T/done $T/data
APP_ENV=test INPUT_DIR=$T/in COMPLETED_DIR=$T/done DATA_DIR=$T/data APP_PORT=8791 CAFE_NO_BROWSER=1 uv run main.py
```
Ở terminal khác:
```bash
curl -s localhost:8791/api/bootstrap | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['mode'], d['modes'])"
# mong đợi: dev {'dev': 'private', 'production': 'public'}
curl -s -X PUT localhost:8791/api/mode -H 'X-Cafe-Editor: 1' -H 'Content-Type: application/json' -d '{"mode":"production"}'
# mong đợi: {"mode":"production"}
cat $T/data/mode.json   # mong đợi: {"mode": "production"}
```
Mở `http://127.0.0.1:8791/`: header có toggle, Production được chọn và có màu đỏ, nút upload ghi `… · public`; bấm Dev thì nút upload đổi thành `… · private`; tải lại trang vẫn giữ mode vừa chọn. Dừng server và xoá `$T`.

- [ ] **Step 8: Commit** — `feat: Dev/Production toggle in the editor header`

---

### Task 4: Một file `.env`

**Files:**
- Modify: `config.py:1-25` (nạp env)
- Modify: `env.template`, `.gitignore`, `README.md` (dòng 11, 27-28, 129-142), `CLAUDE.md`
- Create (máy này, không commit): `.env`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.env_file_to_load(app_env: str | None, find: Callable[[str], str] = find_dotenv) -> tuple[str | None, str | None]` trả `(đường dẫn file hoặc None, cảnh báo hoặc None)`.

- [ ] **Step 1: Viết test hỏng** trong `tests/test_config.py`

```python
def test_test_env_loads_no_file():
    assert config.env_file_to_load("test", lambda name: "/x/.env") == (None, None)


def test_dotenv_is_the_only_file_looked_for():
    asked = []
    def find(name):
        asked.append(name)
        return "/x/.env"
    assert config.env_file_to_load(None, find) == ("/x/.env", None)
    assert asked == [".env"]


@pytest.mark.parametrize("app_env", ["production", "dev"])
def test_old_app_env_values_still_start_with_a_warning(app_env):
    path, warning = config.env_file_to_load(app_env, lambda name: "/x/.env")
    assert path == "/x/.env"
    assert warning == (
        f"APP_ENV={app_env} is no longer used: .env is always loaded. "
        "Choose Dev or Production in the editor."
    )


def test_missing_dotenv_explains_what_to_do():
    with pytest.raises(FileNotFoundError) as e:
        config.env_file_to_load(None, lambda name: "")
    assert str(e.value) == "Environment file not found: copy env.template to .env and adjust the values."
```

- [ ] **Step 2: Chạy** `uv run pytest tests/test_config.py -v` — mong đợi FAIL.

- [ ] **Step 3: Viết `env_file_to_load` và dùng nó ở đầu `config.py`**: in cảnh báo (nếu có) rồi `load_dotenv(path, override=True)`. Không còn chỗ nào đọc `.env.dev` / `.env.production`.

- [ ] **Step 4: Cập nhật file đi kèm.**
  - `.gitignore`: thêm dòng `.env` cạnh `.env.*`.
  - `env.template`: dòng đầu thành `# Copy to .env.`; xoá mục `VIDEO_PRIVACY_STATUS` và thay bằng chú thích `# Upload privacy is chosen in the editor: Dev = private, Production = public.`
  - `README.md` và `CLAUDE.md`: bỏ mọi chỉ dẫn `APP_ENV=production` / `.env.dev` / `.env.production` / `VIDEO_PRIVACY_STATUS`; mô tả toggle, `mode.json`, trường `mode` của `job.json`, `PUT /api/mode`, và rằng `APP_ENV` chỉ còn `test`. Trong `CLAUDE.md` sửa cả câu "Privacy comes from `VIDEO_PRIVACY_STATUS`" và dòng `config.py` ở "Key files".

- [ ] **Step 5: Tạo `.env` cho máy này** (không commit; không xoá `.env.dev` / `.env.production`, để chủ kênh tự xoá):

```
INPUT_DIR=/Users/leo/Downloads/youtube_uploader/new/
COMPLETED_DIR=/Users/leo/Downloads/youtube_uploader/uploaded/
CANDIDATE_THUMBNAIL_NUM=500
```
Kiểm tra: `git status --short` không liệt kê `.env`.

- [ ] **Step 6: Chạy** `uv run pytest && node --test tests/js/ && uv run ruff check . && uv run ruff format .` — mong đợi PASS. `grep -rn "env\.dev\|env\.production\|VIDEO_PRIVACY_STATUS" --exclude-dir=.venv --exclude-dir=.git --exclude-dir=docs .` không còn kết quả.

- [ ] **Step 7: Commit** — `feat: load a single .env; APP_ENV no longer selects an environment`
