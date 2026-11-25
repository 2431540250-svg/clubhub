# Sơ đồ cho slide – Nhóm 9 · WEB 6 ClubHub

> Copy từng khối `mermaid` dán vào https://mermaid.live → **Actions → PNG/SVG** để chèn vào slide.
> GitHub và VS Code (extension *Markdown Preview Mermaid*) cũng hiển thị trực tiếp.

## T1 – ERD (sơ đồ thực thể liên kết)

```mermaid
erDiagram
  ROLES ||--o{ MEMBERS : "có"
  DEPARTMENTS ||--o{ MEMBERS : "gồm"
  MEMBERS ||--o{ REGISTRATIONS : "đăng ký"
  EVENTS ||--o{ REGISTRATIONS : "có"
  DEPARTMENTS ||--o{ EVENTS : "phụ trách"
  EVENTS |o--o{ FUNDS : "gắn với"
  MEMBERS ||--o{ FUNDS : "ghi"
  MEMBERS ||--o{ TASKS : "được giao"
  DEPARTMENTS ||--o{ TASKS : "thuộc"
  EVENTS |o--o{ TASKS : "phục vụ"
  DEPARTMENTS |o--o{ ANNOUNCEMENTS : "nhận"
  MEMBERS ||--o{ ANNOUNCEMENTS : "đăng"
  MEMBERS ||--o{ AI_DRAFTS : "tạo/duyệt"
  MEMBERS ||--o{ MEETINGS : "lập"

  ROLES {
    int id PK
    string code UK
    string name
  }
  DEPARTMENTS {
    int id PK
    string name UK
    string description
  }
  MEMBERS {
    int id PK
    string student_id UK
    string full_name
    string email UK
    string password_hash
    int role_id FK
    int department_id FK
    bool is_active
  }
  EVENTS {
    int id PK
    string title
    datetime start_time
    datetime end_time
    int capacity
    string checkin_token UK
    bool checkin_open
    int department_id FK
  }
  REGISTRATIONS {
    int id PK
    int event_id FK
    int member_id FK
    string ticket_code UK
    datetime checked_in_at
    string checkin_method
  }
  FUNDS {
    int id PK
    string type
    int amount
    string category
    date txn_date
    int event_id FK
    int created_by FK
  }
  TASKS {
    int id PK
    string title
    int assignee_id FK
    int assigner_id FK
    int department_id FK
    string status
    string priority
    date deadline
  }
  ANNOUNCEMENTS {
    int id PK
    string title
    text content
    int department_id FK
    bool is_ai_generated
  }
  MEETINGS {
    int id PK
    string title
    text raw_notes
    text summary
  }
  AI_DRAFTS {
    int id PK
    string kind
    text output_text
    string status
    int created_by FK
    int reviewed_by FK
  }
```

## T2 – Sơ đồ Thành viên – Ban – Vai trò

```mermaid
flowchart LR
  subgraph CLB["Câu lạc bộ"]
    direction TB
    P["👑 Chủ nhiệm<br/>(president)"]
    T["💰 Thủ quỹ<br/>(treasurer)"]
    subgraph B1["Ban Chuyên môn"]
      H1["Trưởng ban (head)"] --> M1["Thành viên (member)"]
    end
    subgraph B2["Ban Truyền thông"]
      H2["Trưởng ban (head)"] --> M2["Thành viên (member)"]
    end
    subgraph B3["Ban Sự kiện / Đối ngoại / Hậu cần"]
      H3["Trưởng ban (head)"] --> M3["Thành viên (member)"]
    end
    P --> H1 & H2 & H3
    P --> T
  end
  A["🛠 Admin hệ thống"] -. quản trị .-> CLB
```

### Ma trận quyền (RBAC)

| Quyền | Admin | Chủ nhiệm | Trưởng ban | Thủ quỹ | Thành viên |
|---|:-:|:-:|:-:|:-:|:-:|
| Xem danh sách thành viên | ✔ | ✔ | ✔ (ban mình) | ✔ | |
| Thêm/sửa/xóa thành viên, gán ban & vai trò | ✔ | ✔ | | | |
| Import thành viên CSV | ✔ | ✔ | | | |
| Quản lý ban | ✔ | ✔ | | | |
| Tạo/sửa sự kiện | ✔ | ✔ | ✔ (ban mình) | | |
| Quét QR điểm danh | ✔ | ✔ | ✔ | ✔ | |
| Xem sổ thu chi | ✔ | ✔ | | ✔ | |
| Ghi thu/chi | ✔ | | | ✔ | |
| Giao việc | ✔ | ✔ | ✔ (ban mình) | | |
| Đăng thông báo | ✔ | ✔ | ✔ (ban mình) | | |
| Xem & xuất báo cáo | ✔ | ✔ | | ✔ | |
| Dùng trợ lý AI | ✔ | ✔ | ✔ | | |
| Duyệt bản nháp AI | ✔ | ✔ | | | |
| Đăng ký sự kiện, vé QR, tự check-in, việc của tôi, xem thông báo | ✔ | ✔ | ✔ | ✔ | ✔ |

*Nguồn trong code: `clubhub/auth.py` → `ROLE_PERMISSIONS`. Trang `/permissions` hiển thị bảng này trực tiếp từ code.*

## T3 – Lưu đồ check-in QR

```mermaid
flowchart TD
  S([Bắt đầu]) --> R[Thành viên đăng ký sự kiện]
  R --> G["Hệ thống sinh vé: ticket_code<br/>→ hiển thị QR 'CLUBHUB:mã'"]
  G --> D{Ngày diễn ra sự kiện}
  D --> C1[Cách 1: BTC mở trang Quét QR<br/>quét vé của thành viên]
  D --> C2[Cách 2: BTC mở tự check-in<br/>chiếu QR sự kiện lên màn hình]
  C2 --> SC[Thành viên quét bằng điện thoại<br/>→ mở /checkin/token]
  SC --> L{Đã đăng nhập?}
  L -- Chưa --> LG[Đăng nhập] --> O
  L -- Rồi --> O{Check-in đang mở?}
  O -- Không --> E1[Báo: chưa mở check-in] --> X
  O -- Có --> V
  C1 --> F{Mã hợp lệ?}
  F -- Không --> E2[Báo lỗi: mã sai / vé sự kiện khác] --> X
  F -- Có --> V{Đã check-in trước đó?}
  V -- Rồi --> E3[Báo: đã điểm danh lúc hh:mm] --> X
  V -- Chưa --> OK[Ghi checked_in_at + phương thức<br/>cập nhật số người có mặt] --> X([Kết thúc])
```

## T4 – Sơ đồ luồng thu chi và giao việc

```mermaid
flowchart LR
  subgraph THU_CHI["Luồng thu chi"]
    direction TB
    a1[Phát sinh khoản thu/chi<br/>hội phí, tài trợ, chi sự kiện] --> a2[Thủ quỹ ghi sổ:<br/>loại, số tiền, danh mục, ngày, sự kiện]
    a2 --> a3[(Bảng funds)]
    a3 --> a4[Sổ quỹ: tồn quỹ, lọc theo tháng,<br/>biểu đồ cơ cấu chi]
    a3 --> a5[Báo cáo tháng]
    a5 --> a6[/Xuất Excel · PDF/]
    a4 --> a7[Chủ nhiệm xem & giám sát]
  end
  subgraph GIAO_VIEC["Luồng giao việc"]
    direction TB
    b1[Chủ nhiệm / Trưởng ban tạo việc] --> b2{AI gợi ý người phù hợp?}
    b2 -- Có --> b3[AI chấm điểm thành viên<br/>khối lượng, hoàn thành, kinh nghiệm] --> b4
    b2 -- Không --> b4[Chọn người thực hiện, hạn, ưu tiên]
    b4 --> b5[(Bảng tasks)] --> b6[Kanban: Chưa làm → Đang làm → Hoàn thành]
    b6 --> b7[Thống kê tiến độ theo ban<br/>trong báo cáo tháng]
  end
```

## T5 – Lưu đồ "AI soạn nháp rồi duyệt"

```mermaid
flowchart TD
  S([Bắt đầu]) --> I[Người dùng nhập yêu cầu<br/>chủ đề thông báo / ghi chép họp]
  I --> K{Có API key LLM?}
  K -- Có --> L[Gọi Gemini / OpenAI qua REST API]
  L --> Q{Gọi thành công?}
  Q -- Không --> R
  K -- Không --> R[Bộ xử lý nội bộ:<br/>template / tóm tắt trích xuất + từ khóa]
  Q -- Có --> D
  R --> D[Lưu bản nháp ai_drafts<br/>status = draft]
  D --> E[Người dùng xem & chỉnh sửa]
  E --> A{Chủ nhiệm duyệt?}
  A -- Từ chối --> RJ[status = rejected] --> X([Kết thúc])
  A -- Duyệt --> AP[status = approved<br/>ghi người duyệt, thời gian]
  AP --> T{Loại bản nháp}
  T -- Thông báo --> P1[Tạo announcement<br/>gắn nhãn AI] --> X
  T -- Biên bản --> P2[Lưu meeting kèm tóm tắt] --> X
```
