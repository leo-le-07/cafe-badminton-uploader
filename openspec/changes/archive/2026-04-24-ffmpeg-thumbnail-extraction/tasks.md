## 1. Implement FFmpeg extraction in `video_prep.py`

- [x] 1.1 Add `_get_video_duration_seconds(video_path: str) -> float` using `ffprobe` subprocess to return video duration
- [x] 1.2 Add `_extract_frame_at(video_path: str, timestamp: float) -> np.ndarray` using `ffmpeg` fast input seeking (`-ss` before `-i`), piping JPEG bytes to stdout and decoding with `cv2.imdecode`
- [x] 1.3 Rewrite `auto_select_thumbnail` to: compute candidate timestamps via `_get_video_duration_seconds`, extract and score each frame in memory using `_extract_frame_at` + `score_frame`, and write only the winning frame to `get_selected_candidate_path`
- [x] 1.4 Delete `create_frame_candidates` function and its imports (`shutil`, `config.CANDIDATE_THUMBNAIL_NUM` if no longer used)

## 2. Update tests

- [x] 2.1 Remove tests that mock `create_frame_candidates` (they test a removed function)
- [x] 2.2 Add test for `_get_video_duration_seconds`: mock `subprocess.run` and assert correct float is returned
- [x] 2.3 Add test for `_extract_frame_at`: mock `subprocess.run` with a synthetic JPEG payload and assert a valid numpy array is returned
- [x] 2.4 Add test for `auto_select_thumbnail` end-to-end: mock `_get_video_duration_seconds` and `_extract_frame_at`, assert the sharpest frame is saved to the correct output path

## 3. Documentation

- [x] 3.1 Add `ffmpeg` install instruction to README (e.g. `brew install ffmpeg`)
