"""Local Flask server for the match editor: page, media streaming and JSON API.

Every JSON error has the shape {"errors": ["..."]}, plus a machine-readable
"code" where the client must react to it (a stale session revision).
Requests that read and then write the stored session (or enqueue from it)
hold one lock, so concurrent requests on Flask's threaded server cannot
interleave.
"""

import subprocess
import threading
from dataclasses import replace
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file
from werkzeug.exceptions import HTTPException

import auth_service
import config
import media_probe
import utils
from app import store
from app.jobs import JobQueue
from app.models import Match, Session, match_problems, validate_session
from cleanup import archive_source
from logger import get_logger

logger = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
SIGNED_OUT_MESSAGE = (
    "Chưa đăng nhập YouTube hoặc phiên đăng nhập đã hết hạn. Hãy đăng nhập rồi thử lại."
)

# Every mutating API request must carry this header (app/static/js/api.js
# sends it). A page on another site can send a "simple" cross-origin POST to
# 127.0.0.1 without it, but not one with a custom header.
EDITOR_HEADER = "X-Cafe-Editor"
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MISSING_HEADER_MESSAGE = (
    f"Yêu cầu bị từ chối: chỉ editor của ứng dụng mới được thay đổi dữ liệu "
    f"(thiếu header {EDITOR_HEADER})"
)

HTTP_ERROR_MESSAGES = {
    400: "Yêu cầu không hợp lệ",
    404: "Không tìm thấy địa chỉ này",
    405: "Phương thức không được hỗ trợ cho địa chỉ này",
    413: "Dữ liệu gửi lên quá lớn",
    500: "Lỗi máy chủ, xem log của ứng dụng để biết chi tiết",
}


STALE_REVISION_MESSAGE = "Phiên đã được thay đổi ở tab khác. Tải lại trang để tiếp tục."
STALE_REVISION_CODE = "stale_revision"


class ApiError(Exception):
    def __init__(self, status: int, errors: list[str], code: str | None = None):
        super().__init__(errors)
        self.status = status
        self.errors = errors
        self.code = code


# ---- request parsing ------------------------------------------------------------


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _check_match_shape(m) -> bool:
    if not isinstance(m, dict):
        return False
    if not all(isinstance(m.get(k), str) for k in ("id", "match_type", "tournament")):
        return False
    if not (_is_str_list(m.get("team1")) and _is_str_list(m.get("team2"))):
        return False
    segments = m.get("segments")
    return isinstance(segments, list) and all(
        isinstance(s, dict)
        and isinstance(s.get("source"), str)
        and _is_number(s.get("start"))
        and _is_number(s.get("end"))
        for s in segments
    )


def _check_open_shape(point) -> bool:
    return point is None or (
        isinstance(point, dict)
        and isinstance(point.get("match_id"), str)
        and isinstance(point.get("source"), str)
        and _is_number(point.get("time"))
    )


def parse_session(body) -> tuple[Session, int | None]:
    """The session in a PUT body and the revision it was based on (None when
    the body has none); ApiError(400) if its shape is wrong."""
    ok = (
        isinstance(body, dict)
        and _is_str_list(body.get("sources"))
        and isinstance(body.get("matches"), list)
        and all(_check_match_shape(m) for m in body["matches"])
        and (
            body.get("selected_match_id") is None
            or isinstance(body["selected_match_id"], str)
        )
        and _check_open_shape(body.get("open"))
        and (
            body.get("revision") is None
            or (type(body["revision"]) is int and body["revision"] >= 0)
        )
    )
    if not ok:
        raise ApiError(400, ["Dữ liệu phiên làm việc không đúng định dạng"])
    return Session.from_dict({**body, "revision": 0}), body.get("revision")


def parse_match_ids(body) -> list[str]:
    ids = body.get("match_ids") if isinstance(body, dict) else None
    if not ids or not _is_str_list(ids):
        raise ApiError(400, ["Cần danh sách mã trận (match_ids) không rỗng"])
    if len(set(ids)) != len(ids):
        raise ApiError(400, ["Danh sách mã trận bị trùng"])
    return ids


def parse_mode(body) -> str:
    mode = body.get("mode") if isinstance(body, dict) else None
    if not isinstance(mode, str) or mode not in config.MODES:
        raise ApiError(400, ["Chế độ upload không hợp lệ, hãy tải lại trang"])
    return mode


# ---- sources --------------------------------------------------------------------


def _disk_sources() -> dict[str, Path]:
    """Supported videos directly in INPUT_DIR, by exact file name."""
    return {path.name: path for path in utils.scan_videos(config.INPUT_DIR)}


def _probe_all() -> dict[str, media_probe.SourceInfo | None]:
    """Probe every source on disk; None for a file ffprobe cannot read."""
    infos: dict[str, media_probe.SourceInfo | None] = {}
    for name, path in _disk_sources().items():
        try:
            infos[name] = media_probe.probe(path)
        except Exception as e:
            logger.warning(f"Cannot read source {name}: {e!r}")
            infos[name] = None
    return infos


def _job_status(queue: JobQueue) -> dict[str, str]:
    return {job["match"]["id"]: job["status"] for job in queue.snapshot()}


def _matches_using(session: Session, name: str) -> list[Match]:
    return [m for m in session.matches if any(s.source == name for s in m.segments)]


def _archivable(session: Session, name: str, status: dict[str, str]) -> bool:
    using = _matches_using(session, name)
    return bool(using) and all(status.get(m.id) == "done" for m in using)


def list_sources(session: Session, queue: JobQueue) -> list[dict]:
    infos = _probe_all()
    status = _job_status(queue)
    entries = []
    for name, info in infos.items():
        entry = info.to_dict() if info else {"name": name}
        entry.update(missing=False, unreadable=info is None)
        entries.append(entry)
    for name in session.sources:
        if name not in infos:
            entries.append({"name": name, "missing": True, "unreadable": False})
    for entry in entries:
        entry["archivable"] = _archivable(session, entry["name"], status)
    return sorted(
        entries,
        key=lambda e: (
            e["missing"] or e["unreadable"],
            e.get("recorded_at", ""),
            e["name"],
        ),
    )


# ---- session checks -------------------------------------------------------------


def _check_locks(new: Session, old: Session, locked: set[str]) -> None:
    old_matches = {m.id: m for m in old.matches}
    new_matches = {m.id: m for m in new.matches}
    errors = []
    for id in sorted(locked):
        before, after = old_matches.get(id), new_matches.get(id)
        if before is None and after is not None:
            errors.append(f"Mã trận {id} đã được dùng cho một trận đã vào hàng đợi")
        elif before is not None and after is None:
            errors.append(f"Trận {id} đang trong hàng đợi, không xoá được")
        elif before is not None and before.to_dict() != after.to_dict():
            errors.append(f"Trận {id} đang trong hàng đợi, không sửa được")
    for name in old.sources:
        if name in new.sources:
            continue
        users = [m.id for m in _matches_using(old, name) if m.id in locked]
        if users:
            errors.append(
                f"File nguồn {name} có đoạn của trận {', '.join(users)} "
                "đang trong hàng đợi, không bỏ chọn được"
            )
    if errors:
        raise ApiError(409, errors)


def _check_content(new: Session, old: Session, locked: set[str]) -> None:
    infos = _probe_all()
    errors = [
        f"File nguồn {name} không có trong thư mục input"
        for name in new.sources
        if name not in infos and name not in old.sources
    ]
    if len(set(new.sources)) != len(new.sources):
        errors.append("Danh sách file nguồn bị trùng")
    durations = {name: info.duration for name, info in infos.items() if info}

    # Segments on a missing or unreadable file cannot be checked; they are
    # kept as they are so the session stays saveable. Locked matches are
    # frozen, so their segments on an archived file are skipped too.
    def checkable(match: Match, source: str) -> bool:
        if source in durations:
            return True
        return source not in new.sources and match.id not in locked

    errors += validate_session(
        Session(
            sources=new.sources,
            matches=[
                replace(m, segments=[s for s in m.segments if checkable(m, s.source)])
                for m in new.matches
            ],
            selected_match_id=new.selected_match_id,
            open=new.open,
        ),
        durations,
    )
    if errors:
        raise ApiError(400, errors)


def _enqueue_errors(ids: list[str], session: Session, locked: set[str]) -> list[str]:
    infos = _probe_all()
    matches = {m.id: m for m in session.matches}
    errors = []
    for id in ids:
        m = matches.get(id)
        if m is None:
            errors.append(f"Không tìm thấy trận {id} trong phiên làm việc")
            continue
        if id in locked:
            errors.append(f"Trận {id} đã có trong hàng đợi")
            continue
        open_id = session.open.match_id if session.open else None
        errors += [f"Trận {id}: {p}" for p in match_problems(m, open_id)]
        unusable = []
        for name in dict.fromkeys(s.source for s in m.segments):
            if name not in infos:
                unusable.append(
                    f"Trận {id}: file nguồn {name} không còn trong thư mục input"
                )
            elif infos[name] is None:
                unusable.append(f"Trận {id}: không đọc được file nguồn {name}")
        errors += unusable
        if not unusable:
            # Segments saved while their file was missing were never range-checked.
            durations = {n: i.duration for n, i in infos.items() if i}
            errors += validate_session(Session(session.sources, [m], None), durations)
    return errors


def _drop_source(session: Session, name: str) -> Session:
    sources = [s for s in session.sources if s != name]
    matches = [
        m
        for m in session.matches
        if not m.segments or any(s.source in sources for s in m.segments)
    ]
    ids = {m.id for m in matches}
    selected = session.selected_match_id
    if selected not in ids:
        selected = None
    open = session.open
    if open is not None and (open.source == name or open.match_id not in ids):
        open = None
    return Session(
        sources=sources,
        matches=matches,
        selected_match_id=selected,
        open=open,
        revision=session.revision,
    )


def _save_next(session: Session, base: Session) -> int:
    """Store `session` as the revision after `base`'s; returns it."""
    revision = base.revision + 1
    store.save_session(replace(session, revision=revision))
    return revision


# ---- app ------------------------------------------------------------------------


def create_app(queue: JobQueue) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
    app.json.ensure_ascii = False
    app.url_map.merge_slashes = False
    session_lock = threading.Lock()
    login = auth_service.BackgroundLogin()

    def auth_payload() -> dict:
        return {**auth_service.auth_status(), "login": login.state()}

    def visible_jobs(session: Session) -> list[dict]:
        ids = {m.id for m in session.matches}
        return [
            job
            for job in queue.snapshot()
            if job["status"] != "done" or job["match"]["id"] in ids
        ]

    @app.errorhandler(ApiError)
    def api_error(e: ApiError):
        if e.code:
            return jsonify(errors=e.errors, code=e.code), e.status
        return jsonify(errors=e.errors), e.status

    @app.errorhandler(HTTPException)
    def http_error(e: HTTPException):
        if request.path.startswith("/api/"):
            message = HTTP_ERROR_MESSAGES.get(e.code, f"Lỗi {e.code}")
            return jsonify(errors=[message]), e.code
        return e

    @app.before_request
    def require_editor_header():
        if (
            request.path.startswith("/api/")
            and request.method in MUTATING_METHODS
            and request.headers.get(EDITOR_HEADER) != "1"
        ):
            return jsonify(errors=[MISSING_HEADER_MESSAGE]), 403
        return None

    @app.after_request
    def no_store(response):
        if request.path == "/" or request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/media/<path:name>")
    def media(name: str):
        path = _disk_sources().get(name)
        if path is None:
            abort(404)
        return send_file(media_probe.playback_path(path), conditional=True)

    @app.get("/api/bootstrap")
    def bootstrap():
        session = store.load_session()
        players = store.load_players()
        return jsonify(
            auth=auth_payload(),
            defaults={"tournament": config.DEFAULT_TOURNAMENT},
            sources=list_sources(session, queue),
            session=session.to_dict(),
            jobs=visible_jobs(session),
            players=sorted(players, key=lambda n: (-players[n], n.casefold())),
        )

    @app.get("/api/sources")
    def sources():
        return jsonify(list_sources(store.load_session(), queue))

    @app.put("/api/session")
    def put_session():
        new, based_on = parse_session(request.get_json(silent=True))
        with session_lock:
            old = store.load_session()
            if based_on != old.revision:
                # Another tab saved since this one loaded: never overwrite.
                raise ApiError(409, [STALE_REVISION_MESSAGE], code=STALE_REVISION_CODE)
            locked = queue.locked_match_ids()
            _check_locks(new, old, locked)
            _check_content(new, old, locked)
            revision = _save_next(new, old)
        return jsonify(ok=True, revision=revision)

    @app.get("/api/jobs")
    def jobs():
        return jsonify(visible_jobs(store.load_session()))

    @app.post("/api/jobs")
    def enqueue():
        body = request.get_json(silent=True)
        ids = parse_match_ids(body)
        mode = parse_mode(body)
        if not auth_service.auth_status()["ok"]:
            raise ApiError(409, [SIGNED_OUT_MESSAGE])
        with session_lock:
            session = store.load_session()
            errors = _enqueue_errors(ids, session, queue.locked_match_ids())
            if errors:
                raise ApiError(400, errors)
            by_id = {m.id: m for m in session.matches}
            try:
                created = queue.enqueue([by_id[id] for id in ids], mode)
            except ValueError as e:
                raise ApiError(400, [str(e)])
            except (OSError, subprocess.CalledProcessError) as e:
                logger.warning(f"Cannot enqueue {ids}: {e!r}")
                raise ApiError(400, ["Không đọc được file nguồn của trận"])
        return jsonify([job.to_dict() for job in created])

    def job_action(action, match_id: str):
        try:
            action(match_id)
        except KeyError:
            raise ApiError(404, [f"Không tìm thấy trận {match_id} trong hàng đợi"])
        except ValueError as e:
            raise ApiError(409, [str(e)])
        return jsonify(ok=True)

    @app.post("/api/jobs/<match_id>/retry")
    def retry(match_id: str):
        return job_action(queue.retry, match_id)

    @app.post("/api/jobs/<match_id>/unqueue")
    def unqueue(match_id: str):
        with session_lock:
            return job_action(queue.unqueue, match_id)

    @app.post("/api/sources/<name>/archive")
    def archive(name: str):
        with session_lock:
            session = store.load_session()
            on_disk = name in _disk_sources()
            if not on_disk and name not in session.sources:
                raise ApiError(404, [f"Không tìm thấy file nguồn {name}"])
            if not _archivable(session, name, _job_status(queue)):
                raise ApiError(
                    409,
                    [
                        f"File nguồn {name} còn trận chưa upload xong hoặc chưa có trận nào"
                    ],
                )
            if on_disk:
                archive_source(name)
            _save_next(_drop_source(session, name), session)
        return jsonify(ok=True)

    @app.get("/api/auth")
    def auth():
        return jsonify(auth_payload())

    @app.post("/api/auth/login")
    def start_login():
        login.start()
        return jsonify(ok=True), 202

    return app
