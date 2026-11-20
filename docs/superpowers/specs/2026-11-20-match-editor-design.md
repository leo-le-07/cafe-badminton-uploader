# Match Editor: cắt, ghép, đặt tên và upload trong một màn hình

Ngày: 2026-11-20
Trạng thái: chờ duyệt

## 1. Mục đích

Đây là hobby project để đưa video cầu lông lên YouTube. Chủ project muốn tốn ít thời gian tay nhất có thể cho mỗi buổi quay.

Hiện tại project chỉ tự động hoá phần sau khi đã có file đặt tên đúng (metadata, thumbnail, overlay, upload, archive). Phần tốn thời gian thật sự nằm ở trước đó và vẫn làm tay:

1. Cắt video dài thành nhiều trận bằng LosslessCut.
2. Cắt bỏ các đoạn thừa giữa trận bằng CapCut (chậm nhất).
3. Thỉnh thoảng ghép 2 recording của cùng một trận (quay bị ngắt giữa chừng).
4. Đặt tên file theo quy ước `md_AzBvsCzD_tournament`.
5. Bỏ file vào `INPUT_DIR`.
6. Mở 3 terminal (Temporal server, worker, CLI) để chạy upload.

Thiết kế này thay cả 6 bước bằng một web app chạy local: mở video, đánh dấu trận bằng phím tắt, nhập tên người chơi, bấm một nút.

## 2. Mục tiêu, ngoài phạm vi, điều phải tránh

**Mục tiêu**

- Một lệnh duy nhất (`uv run main.py`) mở trình duyệt vào editor.
- Đánh dấu bằng tay nhanh nhất có thể: thao tác chính chỉ dùng bàn phím.
- Một cơ chế chung cho cả ba việc: tách video dài, bỏ đoạn giữa, ghép nhiều recording.
- Cắt chính xác tới từng frame.
- Không còn đặt tên file. Thông tin trận nhập qua form.
- Xử lý và upload chạy nền, tiến độ hiện trên trang, tắt mở lại vẫn chạy tiếp, không upload trùng.
- Bỏ Temporal và code thumbnail ranking không còn dùng.

**Ngoài phạm vi (bản này)**

- Tự động phát hiện ranh giới trận hoặc đoạn thừa. Chủ project muốn làm tốt thao tác tay trước.
- Chọn thumbnail bằng tay trong editor. Lệnh `rethumbnail` hiện có vẫn giữ để thay thumbnail sau.
- Hiệu ứng, chuyển cảnh, chỉnh màu, chỉnh âm thanh.
- Chạy trên máy khác hoặc nhiều người dùng. Chỉ macOS, chỉ localhost.
- Tương thích với cách đặt tên file cũ.

**Điều phải tránh**

- Làm xong toàn bộ rồi mới phát hiện UI không hợp. UI đã được chốt qua mockup (mục 4); người làm bám theo mockup, không tự thiết kế lại.
- Upload trùng một trận lên YouTube.
- Mất các điểm đánh dấu khi tắt trình duyệt hoặc tắt app.
- Xoá hoặc sửa file video gốc trong lúc xử lý.

## 3. Các cách làm đã cân nhắc

| Cách | Mô tả | Đánh đổi |
|---|---|---|
| **A. Web app local thay toàn bộ chuỗi công cụ** (đã chọn) | Editor trên trình duyệt, Flask phục vụ, hàng đợi chạy nền trong cùng process | Xoá được cả 6 bước tay. Phần editor là code mới, lớn nhất project |
| B. Giữ LosslessCut, chỉ tự động hoá phần sau | Theo dõi folder export, form nhỏ nhập tên, tự upload | Ít việc, nhưng vẫn cần CapCut cho đoạn giữa, ghép vẫn làm tay, vẫn nhảy giữa nhiều công cụ |
| C. App desktop native | Viết lại bằng Swift hoặc Tauri | Mượt hơn một chút, nhưng bỏ hết code Python đang chạy tốt |

Chủ project chọn A vì đây là cách duy nhất xoá được mọi bước tay.

Một quan sát làm A rẻ hơn tưởng tượng: bước overlay hiện tại (`video_overlay.py`) vốn đã encode lại toàn bộ video. Cắt và ghép gộp vào chính lần encode đó thì không tốn thêm thời gian máy và chính xác tới frame, không bị lệch keyframe như cắt lossless.

## 4. Giao diện (đã chốt)

Hai mockup đã được chủ project duyệt, lưu cạnh tài liệu này:

- `mockups/editor-layout.html`: bố cục tổng thể 3 cột, form trận, hàng đợi.
- `mockups/timeline-scrub.html`: timeline có zoom và kéo con trỏ. Phần timeline của bản này thay phần timeline trong bản bố cục.

Mở trực tiếp hai file trong trình duyệt để xem. Người làm giữ đúng bố cục, màu sắc và hành vi trong mockup.

### 4.1 Bố cục

- **Thanh trên:** tên app, trạng thái đăng nhập YouTube, giá trị mặc định (giải, chế độ hiển thị), trạng thái tự lưu.
- **Cột trái, nguồn:** danh sách video trong `INPUT_DIR` kèm thời lượng và giờ quay. Tick nhiều file thì chúng nối thành một timeline liên tục theo thứ tự quay.
- **Giữa:** khung video, timecode `giờ:phút:giây:frame`, nhãn trạng thái (đang giữ hay không, trận nào), timeline, bảng phím tắt.
- **Cột phải:** danh sách trận, nút "Xử lý & upload", hàng đợi.

### 4.2 Timeline

- Thanh mỏng phía trên luôn hiện cả timeline. Khung trắng là vùng đang phóng to; bấm vào thanh để nhảy tới chỗ khác.
- Vùng chi tiết bên dưới có thước thời gian, các đoạn tô màu theo trận, phần không thuộc đoạn nào hiện sọc xám (bị bỏ).
- Vạch phân cách và tên file ở chỗ nối giữa hai nguồn.
- **Cột vàng là con trỏ phát.** Khung video luôn hiện đúng frame tại vị trí cột vàng.
- **Zoom:** thanh trượt, nút `+` / `−`, phím `+` / `−`, hoặc giữ `⌘`/`Ctrl` và cuộn chuột. Zoom neo theo vị trí chuột. Mức nhỏ nhất vừa cả timeline; mức lớn nhất mỗi frame rộng khoảng 12px. Nút "Vừa màn hình" đưa về mức nhỏ nhất.
- **Kéo con trỏ (scrub):** bấm giữ chuột trái trên timeline rồi kéo thì cột vàng chạy theo chuột và khung video cập nhật theo, như CapCut. Kéo sát mép trái hoặc phải thì timeline tự cuộn.
- **Rê chuột** hiện vạch mờ kèm timecode tại vị trí chuột.
- **Chỉnh điểm cắt:** hai mép trắng của mỗi đoạn kéo được. Bấm đúng mép là chỉnh điểm cắt; bấm chỗ khác là kéo con trỏ.
- Khi đang phát, timeline tự cuộn theo con trỏ.

### 4.3 Phím tắt

| Phím | Tác dụng |
|---|---|
| `I` | Bắt đầu giữ: mở một đoạn mới của trận đang chọn tại con trỏ |
| `O` | Ngừng giữ: đóng đoạn đang mở tại con trỏ |
| `N` | Sang trận mới: đóng đoạn đang mở (nếu có), tạo trận mới và chọn nó |
| `Space` | Phát / dừng |
| `J` `K` `L` | Lùi / dừng / tới. Bấm `L` nhiều lần tăng tốc 2×, 4×, 8× |
| `←` `→` | Lùi / tới 1 giây |
| `⇧←` `⇧→` | Lùi / tới 10 giây |
| `,` `.` | Lùi / tới 1 frame |
| `+` `−` | Zoom timeline |
| `⌘Z` | Hoàn tác |
| `Enter` | Nhảy vào ô tên người chơi của trận đang chọn |
| `Delete` | Xoá đoạn nằm dưới con trỏ |

Phím tắt không kích hoạt khi đang gõ trong ô nhập; `Esc` thoát ô nhập về lại editor.

### 4.4 Quy tắc đánh dấu

- Một **trận** là danh sách **đoạn** theo thứ tự thời gian. Mỗi đoạn là `(file nguồn, điểm vào, điểm ra)`.
- Phần timeline không thuộc đoạn nào thì bị bỏ.
- Bỏ một khúc giữa trận: `O` ở đầu khúc thừa, `I` ở cuối khúc thừa. Trận đó có 2 đoạn.
- Ghép 2 recording: tick cả hai file, đánh dấu các đoạn của cùng một trận ở hai bên vạch nối.
- Một đoạn đang mở mà chạy qua vạch nối giữa hai file thì tự tách thành hai đoạn liền nhau, vẫn thuộc cùng trận.
- Bấm vào một trận ở cột phải (hoặc một đoạn của nó trên timeline) để chọn trận đó. `I` / `O` sau đó thêm đoạn vào trận đang chọn. Nhờ vậy thêm được đoạn vào một trận đã đánh dấu trước đó.
- Các đoạn không được chồng lên nhau, kể cả giữa các trận khác nhau. Thao tác nào gây chồng thì bị chặn ở mép đoạn kề bên.
- `I` khi con trỏ nằm trong một đoạn đã đóng của trận đang chọn: dời điểm vào của đoạn đó tới con trỏ. `O` tương tự với điểm ra.
- Mọi thao tác thay đổi đoạn hoặc trận đều hoàn tác được.

### 4.5 Form một trận

- **Loại trận:** 5 nút MS, MD, WS, WD, XD. Trận mới lấy loại của trận trước đó.
- **Hai đội:** mỗi bên một ô nhập tên dạng chip. Gõ tên rồi `Enter` hoặc `,` để thêm; `Tab` sang đội bên kia.
- **Gợi ý tên:** lấy từ các tên đã dùng trước đây, lọc theo chữ đang gõ, tên dùng nhiều xếp trước. Lần chạy đầu, lịch sử tên được nạp từ các `metadata.json` đã có trong `COMPLETED_DIR`.
- **Giải:** mặc định "Cafe Game", sửa được.
- **Xem trước tiêu đề YouTube** ngay trong thẻ trận.
- Thẻ trận hiện số đoạn và tổng thời lượng sau khi cắt.
- Trận chưa đủ thông tin (thiếu tên ở một bên, hoặc chưa có đoạn nào) hiện cảnh báo và không được đưa vào hàng đợi.

### 4.6 Upload và hàng đợi

- Nút "Xử lý & upload N trận đã đủ thông tin" đưa mọi trận đủ điều kiện vào hàng đợi.
- Trận đã vào hàng đợi thì khoá, không sửa được trong lúc đang chạy.
- Trận đang chờ hoặc đang lỗi, và chưa có video ID trên YouTube, có nút "Đưa về chỉnh sửa": gỡ trận khỏi hàng đợi, xoá workspace dở dang, mở khoá để sửa đoạn và thông tin. Trận đã có video ID thì không đưa về được.
- Mỗi dòng trong hàng đợi hiện tên trận, bước đang chạy và phần trăm (encode, upload). Xong thì có link mở YouTube.
- Trận lỗi hiện thông báo lỗi và nút "Thử lại".
- Vẫn tiếp tục đánh dấu các trận khác trong lúc hàng đợi chạy.

## 5. Kiến trúc

```
Trình duyệt (editor, JS thuần, không build step)
      │  HTTP, chỉ 127.0.0.1
Flask server ── phục vụ trang, stream video gốc (HTTP Range), API JSON
      │
      ├─ Lưu phiên làm việc (JSON)        các nguồn đã chọn, trận, đoạn
      ├─ Lịch sử tên người chơi (JSON)
      └─ Hàng đợi: một luồng nền, chạy từng trận một
             │
             └─ Pipeline một trận:
                metadata → chọn thumbnail → vẽ thumbnail
                → encode (cắt + ghép + overlay, một lần ffmpeg)
                → upload → đặt thumbnail → dọn dẹp
```

Mọi thứ chạy trong một process Python. Không còn Temporal server và worker.

### 5.1 Tái dùng, thay thế, xoá

| Thành phần | Xử lý |
|---|---|
| `uploader.py`, `auth_service.py` | Giữ. Upload resumable, đặt thumbnail, OAuth |
| `thumbnail_enhancement/` | Giữ nguyên template và cách vẽ |
| `video_overlay.py` | Giữ phần vẽ overlay (CAFE GAME, THANKS FOR WATCHING, logo). Phần gọi ffmpeg mở rộng để nhận danh sách đoạn |
| `video_prep.py` | Giữ tạo tiêu đề, mô tả, tag và chọn thumbnail tự động. Bỏ `parse_filename` |
| `rethumbnail.py` và lệnh `rethumbnail` | Giữ, phải chạy được với cả workspace cũ lẫn mới |
| `cleanup.py` | Viết lại theo cách lưu trữ mới (mục 6.4) |
| `temporal/` | Xoá |
| `thumbnail_ranking/`, `thumbnail_selector.py`, `web_selector/` | Xoá |
| Dependency `temporalio`, `torch`, `torchvision`, `clip`, `imagehash` | Gỡ. Các dependency khác chỉ gỡ sau khi kiểm tra không còn import |
| `main.py` | Không tham số: chạy server và mở trình duyệt. Giữ `auth` và `rethumbnail`. Bỏ `start`, `worker`, `debug`, `test-overlay` |
| Test của các module bị xoá | Xoá theo |
| `CLAUDE.md`, `README.md`, `env.template` | Cập nhật theo kiến trúc mới |

### 5.2 Phát video trong trình duyệt

Video gốc là `.mov` hoặc `.mp4`; file mẫu trong repo là HEVC 10-bit 30fps. Editor phát thẳng file gốc qua HTTP Range, không tạo bản sao.

**Rủi ro lớn nhất của thiết kế:** trình duyệt có phát và kéo mượt được HEVC 10-bit dung lượng lớn hay không. Việc đầu tiên trong plan phải là một phép thử nhỏ: stream một file quay thật (dài hàng chục phút) vào thẻ `<video>` và thử kéo con trỏ. Nếu không phát được hoặc kéo quá giật, phương án dự phòng là tạo một bản proxy H.264 độ phân giải thấp chỉ để xem trong editor; encode cuối cùng vẫn lấy từ file gốc.

Timeline nối nhiều file: mỗi file có khoảng thời gian riêng trên timeline chung, editor đổi nguồn phát khi con trỏ qua vạch nối.

## 6. Hành vi phía sau

### 6.1 Phiên làm việc

- Có đúng một phiên làm việc tại một thời điểm: các file nguồn đang tick, danh sách trận, các đoạn, thông tin form.
- Mọi thay đổi tự lưu xuống đĩa trong vòng vài giây. Mở lại app thì thấy đúng trạng thái cũ.
- Thư mục dữ liệu của app (phiên, lịch sử tên, workspace đang xử lý) nằm ngoài `INPUT_DIR`, đường dẫn cấu hình qua env, có giá trị mặc định trong repo và nằm trong `.gitignore`.
- Bỏ tick một file nguồn đang có đoạn thì phải hỏi xác nhận, vì các đoạn của file đó sẽ bị xoá.

### 6.2 Pipeline một trận

Mỗi trận có một workspace riêng, tên duy nhất. Các bước theo thứ tự, bước nào đã có kết quả trên đĩa thì bỏ qua khi chạy lại:

1. **Metadata:** tạo tiêu đề, mô tả, tag từ form. Giữ định dạng hiện có: `Nam/Hùng vs Tú/Long | Cafe Game (2026-11-20)`.
2. **Chọn thumbnail:** cùng thuật toán chấm điểm hiện có, nhưng chỉ lấy mẫu frame trong các đoạn được giữ của trận.
3. **Vẽ thumbnail:** template hiện có.
4. **Encode:** một lần ffmpeg, cắt từng đoạn từ file gốc, nối lại, chèn overlay và logo, giữ nguyên thiết lập encoder hiện có (`h264_videotoolbox`, lỗi thì dùng `libx264`). Thời điểm overlay tính theo thời lượng sau khi cắt: CAFE GAME 12 giây đầu, THANKS FOR WATCHING 12 giây cuối nếu trận dài hơn 24 giây.
5. **Upload:** resumable như hiện có, ghi `upload.json` ngay khi có video ID.
6. **Đặt thumbnail.**
7. **Dọn dẹp:** xem mục 6.4.

Bước "cập nhật visibility" riêng hiện có thừa, vì upload đã đặt đúng `VIDEO_PRIVACY_STATUS`. Bỏ bước này.

### 6.3 Hàng đợi, lỗi và chạy lại

- Một luồng nền xử lý từng trận một, theo thứ tự đưa vào.
- Trạng thái từng trận (bước hiện tại, lỗi) lưu xuống đĩa. Khởi động app thì các trận dở dang tự chạy tiếp từ bước chưa xong.
- **Chống upload trùng:** nếu workspace đã có `upload.json` với video ID thì không bao giờ upload lại.
- **App bị tắt giữa lúc upload:** địa chỉ phiên upload resumable của YouTube được lưu xuống workspace ngay khi bắt đầu upload. Khởi động lại thì upload tiếp từ phiên đó, không tạo video mới. Chỉ khi YouTube báo phiên đã hết hạn mới upload lại từ đầu.
- **Hết quota YouTube (HTTP 429, hoặc 403 với lý do `quotaExceeded` / `uploadLimitExceeded`):** trận chuyển sang trạng thái "chờ quota" và tự thử lại sau mỗi vài giờ khi app còn chạy, và mỗi lần khởi động app. Các trận sau nó cũng dừng ở bước upload, nhưng vẫn làm trước các bước trước upload.
- **Lỗi khác:** trận dừng ở trạng thái lỗi kèm thông báo; hàng đợi chạy tiếp trận sau. Nút "Thử lại" chạy lại từ bước lỗi.
- **Chưa đăng nhập YouTube hoặc token hết hạn:** thanh trên báo rõ và có nút đăng nhập, dùng luồng OAuth hiện có. Không đưa trận vào bước upload khi chưa đăng nhập.
- Đóng tab trình duyệt không dừng hàng đợi. Tắt process thì dừng, mở lại chạy tiếp.

### 6.4 Lưu trữ sau khi xong

- Workspace của trận (metadata, thumbnail, `upload.json`) chuyển vào `COMPLETED_DIR`, giữ đúng tên file bên trong như hiện tại để `rethumbnail` dùng được.
- File video đã encode bị xoá sau khi upload và đặt thumbnail thành công.
- File nguồn gốc không tự động di chuyển. Khi mọi trận dùng một file nguồn đã upload xong, file đó hiện nút "Lưu trữ" ở cột trái; bấm thì chuyển file sang `COMPLETED_DIR` và gỡ khỏi phiên.
- Danh sách đoạn của mỗi trận được lưu trong workspace, nên luôn tái tạo được video đã encode từ file gốc.

### 6.5 Bảo mật

- Server chỉ lắng nghe trên `127.0.0.1`.
- Endpoint stream video chỉ phục vụ file nằm trong `INPUT_DIR`, không nhận đường dẫn tuỳ ý.

## 7. Các quyết định của người viết spec

Chủ project chưa nói về các điểm dưới đây. Chúng là lựa chọn của người viết, cần được xem lại khi duyệt:

1. **Ngày trong tiêu đề là ngày quay**, lấy từ file nguồn đầu tiên của trận (metadata thời điểm quay, không có thì dùng ngày sửa file). Hiện tại code dùng ngày upload, sẽ sai nếu upload trễ một hôm.
2. **Xoá file đã encode sau khi upload xong** để khỏi tốn gấp đôi dung lượng. File gốc và danh sách đoạn vẫn giữ.
3. **File nguồn chỉ chuyển sang `COMPLETED_DIR` khi bấm "Lưu trữ"**, không tự động, vì có thể còn muốn cắt thêm từ file đó.
4. **Trận đã vào hàng đợi thì khoá**, trừ khi bấm "Đưa về chỉnh sửa" lúc trận chưa lên YouTube. Muốn sửa sau khi đã upload thì sửa trên YouTube.
9. **Chế độ hiển thị video vẫn lấy từ `VIDEO_PRIVACY_STATUS` trong env**, áp dụng cho mọi trận. Ô trên thanh trên chỉ hiện giá trị đó, không sửa được trong editor. Chữ "unlisted" trong mockup chỉ là ví dụ.
10. **Upload bị ngắt thì nối tiếp phiên upload cũ** thay vì upload lại, để không sinh video trùng.
5. **Chưa có chọn thumbnail bằng tay trong editor**; dùng tự động và `rethumbnail` như cũ.
6. **Thêm phím `Delete` để xoá đoạn**, không có trong mockup.
7. **Frontend viết JS thuần, không framework, không build step**, để project vẫn chạy bằng một lệnh `uv run`.
8. **Bỏ các lệnh CLI `start`, `worker`, `debug`, `test-overlay`** cùng với Temporal.

## 8. Để người làm tự quyết

- Cấu trúc module và tên file phía Python, miễn giữ ranh giới: phiên làm việc, pipeline, hàng đợi, server.
- Định dạng cụ thể của các file JSON và hình dạng API.
- Cách đẩy tiến độ lên trang (polling hay SSE).
- Cách dựng lệnh ffmpeg (trim/concat filter hay cách khác), miễn một lần encode và chính xác tới frame. Lưu ý audio hiện đang copy nguyên; khi nối nhiều đoạn thì phải encode lại audio.
- Xử lý trận có các đoạn từ những file khác độ phân giải hoặc fps: đưa về theo đoạn đầu tiên.
- Cách đo phần trăm encode.
- Số bước hoàn tác tối đa.
- Có cần bản proxy hay không, theo kết quả phép thử ở mục 5.2.

## 9. Kiểm thử

- Test tự động (pytest) cho logic thuần: quy tắc đoạn và trận (không chồng, tách ở vạch nối), tạo tiêu đề và mô tả, dựng lệnh ffmpeg từ danh sách đoạn, tính thời điểm overlay, máy trạng thái của hàng đợi (bỏ qua bước đã xong, chống upload trùng, chờ quota, thử lại).
- Một test tích hợp encode thật trên file mẫu ngắn: 2 đoạn từ 1 file và 2 đoạn từ 2 file, kiểm tra thời lượng đầu ra.
- YouTube API luôn được mock trong test.
- Editor kiểm tra bằng tay theo danh sách thao tác ở mục 4, trên Chrome.
- `uv run pytest` và `uv run ruff check .` phải sạch.

## 10. Tiêu chí hoàn thành

Với một video dài chứa 3 trận và một trận bị tách làm 2 file:

1. Chạy `uv run main.py`, trình duyệt mở editor, thấy các file trong `INPUT_DIR`.
2. Chỉ dùng bàn phím và chuột trong editor, đánh dấu 4 trận, trong đó một trận bỏ khúc giữa và một trận nối qua 2 file.
3. Nhập tên người chơi, bấm một nút.
4. Cả 4 video xuất hiện trên YouTube với đúng tiêu đề, thumbnail, overlay, điểm cắt đúng frame đã đánh dấu.
5. Tắt app giữa chừng rồi mở lại: hàng đợi chạy tiếp, không có video nào bị upload hai lần.
6. Không cần mở LosslessCut, CapCut, Finder hay terminal thứ hai ở bất kỳ bước nào.
