"""Flask server for web-based thumbnail selection."""
import base64
import threading
import webbrowser
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request, send_file, render_template_string
from temporalio.exceptions import ApplicationError
from werkzeug.serving import make_server

from logger import get_logger
from utils import get_selected_candidate_path

logger = get_logger(__name__)


class ThumbnailSelectorServer:
    """Flask server for thumbnail selection UI."""

    def __init__(self, video_path: Path, port: int = 8765):
        self.video_path = video_path.resolve()
        self.port = port
        self.app = Flask(__name__, template_folder="templates")
        self.selection_event = threading.Event()
        self.selected_image_data: Optional[bytes] = None
        self.server_thread: Optional[threading.Thread] = None
        self.server = None
        self.shutdown_event = threading.Event()

        self._setup_routes()

    def _setup_routes(self) -> None:
        """Set up Flask routes."""

        @self.app.route("/")
        def index():
            from web_selector.templates import SELECT_HTML
            return render_template_string(SELECT_HTML)

        @self.app.route("/video")
        def video():
            suffix = self.video_path.suffix.lower()
            mime_types = {
                ".mov": "video/quicktime",
                ".mp4": "video/mp4",
                ".avi": "video/x-msvideo",
                ".webm": "video/webm",
            }
            mime_type = mime_types.get(suffix, "video/quicktime")
            return send_file(str(self.video_path), mimetype=mime_type)

        @self.app.route("/select", methods=["POST"])
        def select():
            try:
                data = request.get_json()
                if not data or "image" not in data:
                    return jsonify({"error": "Missing image data"}), 400

                image_data_str = data["image"]
                if not isinstance(image_data_str, str):
                    return jsonify({"error": "Invalid image data format"}), 400

                if image_data_str.startswith("data:image"):
                    base64_data = image_data_str.split(",")[1]
                else:
                    base64_data = image_data_str

                try:
                    image_bytes = base64.b64decode(base64_data)
                except Exception as e:
                    logger.error(f"Failed to decode base64 image: {e}")
                    return jsonify({"error": "Invalid base64 data"}), 400

                if len(image_bytes) > 10 * 1024 * 1024:
                    return jsonify({"error": "Image too large (max 10MB)"}), 400

                self.selected_image_data = image_bytes
                self.selection_event.set()

                return jsonify({"status": "success"})
            except Exception as e:
                logger.error(f"Error processing selection: {e}")
                return jsonify({"error": str(e)}), 500


    def start(self) -> None:
        """Start the Flask server in a separate thread."""
        self.server_thread = threading.Thread(
            target=self._run_server, daemon=False
        )
        self.server_thread.start()

        import time

        time.sleep(0.5)

        url = f"http://127.0.0.1:{self.port}/"
        logger.info(f"Opening browser to {url}")
        webbrowser.open(url)

    def _run_server(self) -> None:
        """Run Flask server using make_server for proper shutdown."""
        try:
            self.server = make_server(
                host="127.0.0.1",
                port=self.port,
                app=self.app,
                threaded=True,
            )
            self.server.serve_forever()
        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(
                    f"Port {self.port} is already in use. "
                    f"Please close the conflicting process or set THUMBNAIL_SELECTOR_PORT to a different port."
                )
            raise
        except Exception as e:
            logger.error(f"Flask server error: {e}")
            raise

    def wait_for_selection(self, timeout: float = 3600.0) -> bytes:
        """Wait for user selection with timeout."""
        if not self.selection_event.wait(timeout=timeout):
            raise ApplicationError(
                "Thumbnail selection cancelled or timed out",
                type="ThumbnailSelectionTimeout",
                non_retryable=False,
            )

        if self.selected_image_data is None:
            raise ApplicationError(
                "No image data received",
                type="ThumbnailSelectionError",
                non_retryable=False,
            )

        return self.selected_image_data

    def shutdown(self) -> None:
        """Shutdown the Flask server."""
        self.shutdown_event.set()

        if self.server:
            try:
                self.server.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down server: {e}")

        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=5)
            if self.server_thread.is_alive():
                logger.warning("Server thread did not stop within timeout")


def save_selected_image(image_data: bytes, video_path: Path) -> None:
    """Save selected image to file."""
    output_path = get_selected_candidate_path(video_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        f.write(image_data)

    logger.info(f"Saved selected thumbnail to {output_path}")


def select_thumbnail_web(
    video_path: Path, port: int = 8765
) -> None:
    """Run web-based thumbnail selection activity."""
    server = None
    try:
        server = ThumbnailSelectorServer(video_path, port=port)
        server.start()

        image_data = server.wait_for_selection(timeout=3600.0)

        save_selected_image(image_data, video_path)
        logger.info(f"Selected thumbnail saved for {video_path.name}")
    except Exception as e:
        logger.error(f"Error in thumbnail selection: {e}")
        raise
    finally:
        if server:
            server.shutdown()
