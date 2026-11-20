# Toggle Dev / Production trên editor, gộp về một env

## Vì sao

Hiện phải chọn env bằng `APP_ENV` lúc chạy (`.env.dev` mặc định, `.env.production`). Chủ kênh hay quên, nên có lúc mở nhầm thư mục test hoặc upload nhầm chế độ. Hai env còn dùng chung `./data` (chung `session.json`) trong khi `INPUT_DIR` khác nhau, nên chạy nhầm env có thể làm session trỏ sai file.

## Mục tiêu

- Chỉ còn một lệnh `uv run main.py` và một file `.env`.
- Chọn Dev / Production bằng toggle ngay trên editor, luôn nhìn thấy trước khi bấm upload.
- Hai mode chỉ khác nhau đúng một thứ: Dev upload `private`, Production upload `public`. Mọi thứ khác giống hệt nhau.

## Không làm

- Kéo thả video. Vẫn để video vào `INPUT_DIR` như hiện nay.
- Session, hàng đợi, thư mục, tên thư mục lưu trữ hay gợi ý tên riêng cho từng mode.

## Điều tuyệt đối tránh

- Upload `public` khi người dùng tưởng đang ở Dev.

## Các cách đã cân nhắc

1. **Toggle trên UI, mode ghi vào từng trận lúc đưa vào hàng đợi (đã chọn).** Một session, một hàng đợi; gạt toggle không ảnh hưởng trận đã xếp hàng.
2. **Bỏ mode, chỉ chọn public/private trong editor.** Gần như tương đương, nhưng chủ kênh muốn giữ tên Dev / Production để sau này có thể gom thêm config khác.
3. **Giữ hai env, chỉ hiện tên env trên UI.** Vẫn phải nhớ `APP_ENV` lúc chạy, không giải quyết gốc vấn đề.

## Thiết kế

### Config

- `config.py` đọc một file `.env` (không còn `.env.dev` / `.env.production`; `APP_ENV` chỉ còn giá trị `test` cho pytest).
- Mọi biến dùng chung cho cả hai mode: `INPUT_DIR`, `COMPLETED_DIR`, `DATA_DIR`, `APP_PORT`, `CANDIDATE_THUMBNAIL_NUM`, `LOGO_PATH`, `QUOTA_RETRY_HOURS`.
- Bỏ biến `VIDEO_PRIVACY_STATUS`. Privacy theo mode được ghi cứng trong code: `config.MODES = {"dev": "private", "production": "public"}`.
- `.env` của máy này: `INPUT_DIR=~/Downloads/youtube_uploader/new/`, `COMPLETED_DIR=~/Downloads/youtube_uploader/uploaded/`, `CANDIDATE_THUMBNAIL_NUM=500`.

### Mode hiện tại

- Lưu ở `DATA_DIR/mode.json` (ghi atomic qua `app/store.py`). Thiếu hoặc hỏng thì về `dev`.
- `GET /api/bootstrap` trả thêm `mode`.
- `PUT /api/mode` `{"mode": "dev" | "production"}` đổi mode (cần header `X-Cafe-Editor` như mọi request ghi).

### Mode của từng trận

- `POST /api/jobs` gửi kèm `mode` mà UI đang hiển thị; server từ chối (400) nếu không phải `dev`/`production`. Nhờ vậy trận được ghi đúng mode người dùng nhìn thấy lúc bấm.
- `Job` có thêm trường `mode`, lưu trong `job.json`. `job.json` cũ không có trường này được coi là `dev` (thà upload nhầm private còn hơn nhầm public).
- `uploader.py` lấy privacy từ `config.MODES[job.mode]`.
- "Thử lại" giữ mode cũ của trận. Muốn đổi mode thì "Đưa về chỉnh sửa" rồi upload lại.

### Giao diện

- Toggle hai nút `Dev · private` | `Production · public` ở header, thay cho pill "Mặc định: … · private".
- Production có màu nổi bật (đỏ/cam), Dev màu trung tính.
- Nút upload ghi rõ privacy: "Xử lý & upload 3 trận · public".
- Mỗi trận trong hàng đợi có nhãn `private` / `public`.

### Kiểm thử

- pytest: đọc/ghi `mode.json` (thiếu, hỏng → dev); `PUT /api/mode`; enqueue ghi mode vào job; uploader dùng privacy theo mode của job; `job.json` cũ → dev.
- JS: chữ trên nút upload theo mode.
- YouTube API vẫn luôn được mock.

## Để người làm tự quyết

- Tên file/hàm cụ thể, màu chính xác của toggle, cách cập nhật `README.md`, `CLAUDE.md`, `env.template`.

## Các quyết định do Claude tự đề xuất (chủ kênh chưa nói rõ)

- `CANDIDATE_THUMBNAIL_NUM` dùng chung, giá trị 500 như production hiện nay.
- `job.json` cũ không có mode được coi là `dev`.
- Gạt toggle không hỏi xác nhận; an toàn dựa vào màu và chữ trên nút upload.
