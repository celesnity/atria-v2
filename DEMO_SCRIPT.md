# Maintenance Copilot — Kịch bản Demo trên Atria

**Đối tượng:** Trung tâm Kiểm soát Bảo dưỡng (MCC) + Đội Kỹ thuật
**Thời lượng:** ~20 phút
**Bối cảnh:** Người dùng **gõ câu hỏi tự nhiên trong khung chat Atria**. Agent tự
nhận diện skill `maintenance_copilot`, chạy công cụ tra cứu phía sau (RAG trên
AMM/MEL/CDL/TSM + knowledge graph), rồi trả lời **có trích dẫn nguồn**.
**Người dùng không gõ lệnh CLI.**

**Thông điệp xuyên suốt:** *Copilot tra cứu, đối chiếu, kiểm tra chéo — nhưng kỹ
sư có chứng chỉ vẫn ký duyệt mọi quyết định dispatch. Mọi câu trả lời đều dẫn nguồn.*

---

## Điều kiện tiên quyết (làm trước khi demo)

1. **Hạ tầng chạy OK.** 4 dịch vụ nền phải sẵn sàng và tài liệu đã được index:
   ```bash
   cd modules/maintenance_copilot/scripts
   python copilot.py health         # cả 4 → "ok"
   python copilot.py ingest         # {"documents": 4, "chunks": N}
   python copilot.py graph build    # {"chunks": N, "nodes": .., "edges": ..}
   ```
   Bộ tài liệu: **AMM Rev-42**, **MEL Rev-18**, **CDL Rev-07**, **TSM Rev-31**.

2. **Skill có "runbook" để agent biết cách gọi CLI.** `SKILL.md` hiện tại mới là
   *concept brief*; cần bổ sung phần hướng dẫn agent chạy `copilot.py query /
   recommend-refs / validate / check / graph` và **luôn trả lời kèm trích dẫn +
   miễn trừ tư vấn**. (Xem mục "Ghi chú kỹ thuật" ở cuối.)

---

## Luồng demo — Người dùng gõ trên Atria → Output kỳ vọng

Mỗi kịch bản gồm 3 phần: **① Người dùng gõ** · **② Hậu trường (agent làm gì)** ·
**③ Atria hiển thị**.

### 1. Tra cứu quy trình bằng ngôn ngữ tự nhiên

**① Người dùng gõ:**
> "Càng đáp không thu được sau khi cất cánh thì tra quy trình nào?"

**② Hậu trường:** agent chạy `copilot.py query "gear fails to retract after takeoff" --k 3`.

**③ Atria hiển thị:**
- Nêu lỗi **TSM 32-3101 (Gear Fails to Retract)** và mục AMM về càng đáp liên quan.
- **Mỗi ý đều kèm trích dẫn**: tên tài liệu + revision + mục (vd `TSM ... Rev-31 · tsm_ata32#..`).
- **Không** kết luận "được/không được dispatch" — chỉ trình bày quy trình có nguồn.

---

### 2. Hỏi điều kiện dispatch (câu trả lời tổng hợp, có dẫn nguồn)

**① Người dùng gõ:**
> "Anti-skid hỏng thì có những điều kiện (proviso) gì để được dispatch?"

**② Hậu trường:** `copilot.py query "...anti-skid inoperative provisos..." --synthesize`.

**③ Atria hiển thị:**
- Câu trả lời ngắn gọn **chỉ dựa trên** MEL **32-40-01 (Anti-Skid, Category C,
  thời hạn sửa 10 ngày)** — không bịa thêm kiến thức ngoài tài liệu.
- Kèm danh sách **trích dẫn** và **cờ "cần rà soát"** nếu bằng chứng chưa đủ mạnh.
- Kèm dòng **miễn trừ**: *chỉ mang tính tư vấn, kỹ sư quyết định cuối cùng.*

---

### 3. Gợi ý tài liệu cho một mô tả hỏng hóc

**① Người dùng gõ:**
> "Đèn 'gear disagree' màu hổ phách, LGCIU kênh 2 báo lỗi — nên tham chiếu tài liệu nào?"

**② Hậu trường:** `copilot.py recommend-refs "amber gear disagree light, LGCIU channel 2 flagged" --k 4`.

**③ Atria hiển thị:**
- Danh sách xếp hạng, mỗi mục có **điểm tin cậy (confidence)**.
- Kỳ vọng **MEL 32-33-01 (LGCIU Channel)** và **TSM 32-3302 (LGCIU Channel
  Disagree)** ở gần đầu.
- Nhấn mạnh: **đây là gợi ý, kỹ sư chọn.**

---

### 4. Kiểm tra tham chiếu kỹ sư đã ghi (bắt lỗi trích dẫn sai)

**① Người dùng gõ:**
> "Phiếu hỏng NWS ghi tham chiếu MEL 32-31-01 và MEL 99-99-99 — kiểm giúp có đúng không?"

**② Hậu trường:** `copilot.py validate '{"defect":"NWS inop","cited_refs":["MEL 32-31-01","MEL 99-99-99"]}'`.

**③ Atria hiển thị:**
- **MEL 32-31-01 (Nose Wheel Steering)** → **PASS**, kèm đoạn tài liệu hỗ trợ.
- **MEL 99-99-99** → **FAIL** (không có trong tài liệu đã duyệt) → **bắt được lỗi**.

---

### 5. Rà soát tính nhất quán của phiếu hỏng hóc (điểm nhấn)

**① Người dùng gõ:**
> "Phiếu: anti-skid inop, dẫn MEL 32-40-01, ghi dispatch 3 ngày, phân loại B —
> có gì bất nhất không?"

**② Hậu trường:** `copilot.py check '{"defect":"anti-skid inop","cited_mel":"MEL 32-40-01","dispatch_condition":"dispatch 3 days","classification":"B"}'`.

**③ Atria hiển thị:**
- Cờ mâu thuẫn mức **MEDIUM**: phân loại ghi **B** ≠ category **C** của MEL 32-40-01.
- Khuyến cáo thêm về placard / dụng cụ / thời hạn (từ knowledge graph).
- **Không phán quyết** — chỉ cảnh báo để kỹ sư sửa trước khi ký.

**Đối chứng (nếu còn thời gian):**
- Ghi đúng phân loại **C** → *không có mâu thuẫn*.
- Dẫn **MEL 32-99-99** (không tồn tại) → cờ mức **HIGH**: không tìm thấy trong tài liệu đã duyệt.

---

### 6. Đối chiếu chéo qua Knowledge Graph

**① Người dùng gõ:**
> "Cho xem những gì liên quan tới hệ thống báo vị trí càng đáp (ATA 32)."

**② Hậu trường:** `copilot.py query "landing gear position indicating" --ata 32 --graph`
rồi `copilot.py graph show 32 --hops 1`.

**③ Atria hiển thị:**
- Đoạn tài liệu có trích dẫn **kèm** khối "thực thể liên quan" từ đồ thị.
- Các liên kết do máy suy ra được gắn nhãn **chưa xác minh (unverified)** cho tới khi kỹ sư xác nhận.
- (Tùy chọn) Kỹ sư xác nhận một liên kết → chuyển **engineer_confirmed**.

---

### 7. Truy vết Audit (phục vụ tuân thủ)

**① Người dùng gõ:**
> "Cho xem lại nhật ký các thao tác vừa rồi."

**② Hậu trường:** `copilot.py audit --limit 10`.

**③ Atria hiển thị:**
- Danh sách sự kiện theo thời gian (query / recommend / validate / check), mỗi
  sự kiện gắn với trích dẫn đã dùng — **hồ sơ truy vết phục vụ pháp lý.**

---

## Các nguyên tắc bảo vệ (nói rõ khi demo)

- **Luôn có con người trong vòng lặp** — output chỉ là tư vấn; kỹ sư ký. Dispatch không tự động hoàn toàn.
- **Luôn có trích dẫn** — tài liệu + revision + trang/mục cho mọi tham chiếu.
- **Nhận biết revision** — tra cứu lọc theo `current`; trang đã thay thế bị gắn cờ.
- **Nêu rõ độ bất định** — kết quả tin cậy thấp và cạnh đồ thị chưa xác minh đều được gắn nhãn để rà soát tay.

---

## Ghi chú kỹ thuật (cho người vận hành demo)

- Người dùng **chỉ gõ tiếng Việt/tiếng Anh tự nhiên**; agent lo phần gọi CLI.
- Nếu agent **chưa** tự chạy `copilot.py`, cần bổ sung "runbook" vào `SKILL.md`
  (liệt kê các lệnh query/recommend-refs/validate/check/graph, và bắt buộc trả
  lời kèm trích dẫn + miễn trừ tư vấn). Tôi có thể viết phần này nếu bạn muốn.
- Reset giữa các lần chạy: `python copilot.py reset` và `python copilot.py graph reset`.
- Nếu một dịch vụ nền lỗi, `health` trả `error: <thông báo>` — khắc phục trước khi mời khách vào.
