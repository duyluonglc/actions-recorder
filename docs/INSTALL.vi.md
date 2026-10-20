# Cài đặt Actions Recorder

[English](INSTALL.md)

Tải tệp phù hợp với máy của bạn tại **[bản phát hành mới nhất](https://github.com/OWNER/actions-recorder/releases/latest)**:

| Máy | Tệp |
|---|---|
| Windows 10 / 11 (64-bit) | `ActionsRecorder-<phiên bản>-Windows-x64.zip` |
| Mac chip Apple (M1, M2, M3, M4 …) | `ActionsRecorder-<phiên bản>-macOS-AppleSilicon.dmg` |
| Mac chip Intel | `ActionsRecorder-<phiên bản>-macOS-Intel.dmg` |

Không biết Mac của mình loại nào? Menu Apple  → **Giới thiệu về máy Mac** → xem dòng *Chip* (Apple) hay *Bộ xử lý* (Intel).

> **Vì sao có cảnh báo?** Actions Recorder miễn phí. Muốn hết cảnh báo khi mở lần đầu thì phải mua chứng
> chỉ ký ứng dụng của Apple và Microsoft, nên app được phát hành không ký chính thức (macOS: chữ ký ad-hoc).
> Cảnh báo bên dưới chỉ xuất hiện **một lần**; làm theo các bước để mở app.
> Luôn tải app từ trang Releases chính thức ở trên.

---

## Windows

1. **Giải nén** tệp vừa tải: chuột phải → **Extract All…** (Giải nén tất cả) → *Extract*. Không chạy app khi còn nằm trong tệp zip.
2. Mở thư mục vừa giải nén, nhấp đúp **Actions Recorder.exe**.
3. Nếu hiện **"Windows protected your PC"** (SmartScreen): bấm **More info** (Thông tin thêm) → **Run anyway** (Vẫn chạy).

   Chỉ cần làm lần đầu.
4. Xong — Windows không cần cấp thêm quyền.
   - Muốn tự động hoá chương trình đang chạy **bằng quyền quản trị**, hãy chạy Actions Recorder bằng quyền quản trị
     (chuột phải → *Run as administrator*); Windows không cho chương trình thường điều khiển cửa sổ có quyền cao hơn.

**Antivirus cảnh báo hoặc tệp .exe biến mất?** Công cụ ghi bàn phím và điều khiển chuột dễ bị một số phần mềm
diệt virus nghi là phần mềm gián điệp. Actions Recorder chỉ lưu mọi thứ trên máy bạn (xem [Quyền riêng tư](#quyền-riêng-tư)). Bạn có thể:
- khôi phục tệp khỏi khu cách ly và thêm thư mục vào danh sách loại trừ (Windows Security → Virus & threat
  protection → Manage settings → Exclusions), hoặc
- kiểm tra tệp tải về trên [VirusTotal](https://www.virustotal.com/), hoặc tự build từ mã nguồn.

**Cập nhật:** xoá thư mục cũ và giải nén tệp zip mới. Cài đặt và macro của bạn vẫn được giữ.

---

## macOS

### 1. Cài đặt

Mở tệp `.dmg`, kéo **Actions Recorder** vào thư mục **Applications**.

### 2. Mở lần đầu

macOS chặn các app chưa được Apple công chứng (notarize):

**macOS 15 Sequoia trở lên**
1. Nhấp đúp Actions Recorder. Thông báo Apple không thể xác minh app → bấm **Done / Xong**
   (**không** chọn *Chuyển vào Thùng rác*).
2. Mở **System Settings → Privacy & Security** (Cài đặt hệ thống → Quyền riêng tư & Bảo mật), kéo xuống mục *Bảo mật*.
3. Cạnh dòng *"Actions Recorder" đã bị chặn…* bấm **Open Anyway / Vẫn mở**, xác nhận bằng mật khẩu hoặc Touch ID,
   rồi bấm **Open Anyway** thêm lần nữa.

**macOS 14 Sonoma trở về trước:** chuột phải (hoặc Control-click) vào app → **Open / Mở** → **Open / Mở**.

**"Actions Recorder bị hỏng và không thể mở" (damaged)** — đây là cờ cách ly của tệp tải từ Internet, không phải
app bị hỏng thật. Mở **Terminal** và chạy:

```bash
xattr -dr com.apple.quarantine "/Applications/Actions Recorder.app"
```

### 3. Cấp quyền

Lần mở đầu tiên, cửa sổ **Chào mừng** liệt kê các quyền kèm trạng thái ✅ / ❌ cập nhật trực tiếp. Với mỗi quyền,
bấm **Cho phép…** — Cài đặt hệ thống mở đúng trang — rồi bật công tắc **Actions Recorder**:

| Quyền | Ở đâu | Dùng để |
|---|---|---|
| **Accessibility** (Trợ năng) | Privacy & Security → Accessibility | phát lại click và phím |
| **Input Monitoring** (Giám sát đầu vào) | Privacy & Security → Input Monitoring | ghi thao tác, phím tắt toàn cục (F9 / F10) |
| **Screen Recording** (Ghi màn hình) | Privacy & Security → Screen & System Audio Recording | tìm ảnh, OCR, bước AI nhìn màn hình (không bắt buộc) |

Sau đó bấm **Khởi động lại app** — macOS chỉ áp dụng quyền Input Monitoring và Screen Recording sau khi mở lại.
Có thể mở lại cửa sổ này bất cứ lúc nào ở **Trợ giúp → Quyền truy cập…**.

Nếu không thấy Actions Recorder trong danh sách: bấm **+**, chọn *Applications → Actions Recorder*, rồi bật lên.

### 4. Phím F trên MacBook

Mặc định các phím F điều chỉnh độ sáng/âm lượng. Hãy bấm **fn + F9** / **fn + F10**, hoặc bật
*System Settings → Keyboard → Keyboard Shortcuts… → Function Keys → "Use F1, F2, etc. keys as standard function keys"*.
Bạn cũng có thể đổi phím tắt trong **Tuỳ chọn → Phím tắt**.

### Cập nhật trên macOS

Thay app trong *Applications* bằng bản mới. Vì app không ký bằng Apple Developer ID, macOS có thể coi bản mới là
một app khác và vẫn hiện ❌ dù công tắc đang bật. Cách sửa: trong từng danh sách quyền, chọn **Actions Recorder**,
bấm **−** để xoá, rồi bấm **Cho phép…** lại trong cửa sổ Chào mừng (Trợ giúp → Quyền truy cập…).

---

## Kiểm tra bản cài đặt

Chạy chức năng tự kiểm tra và đính kèm kết quả khi [báo lỗi](https://github.com/OWNER/actions-recorder/issues):

- Windows (Command Prompt, trong thư mục app):
  `"Actions Recorder.exe" --self-test report.txt` → rồi mở `report.txt`
- macOS (Terminal):
  `"/Applications/Actions Recorder.app/Contents/MacOS/Actions Recorder" --self-test`

## Quyền riêng tư

Macro, cài đặt và ảnh chụp màn hình chỉ nằm trên máy bạn. Không có gì được gửi đi, ngoại trừ nội dung/ảnh của
**bước AI** — chỉ khi bạn tự thêm bước đó và tự cấu hình nhà cung cấp AI (hoặc dùng mô hình chạy trên máy như
Ollama để mọi thứ vẫn ngoại tuyến).

## Chạy từ mã nguồn

```bash
git clone https://github.com/OWNER/actions-recorder.git
cd actions-recorder
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip ...
.venv/bin/python run.py
```

Khi chạy từ mã nguồn trên macOS, hãy cấp quyền cho **Terminal** (hoặc IDE) mà bạn dùng để chạy app.
