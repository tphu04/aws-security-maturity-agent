# Diagrams — Hướng dẫn quản lý sơ đồ báo cáo

Thư mục này chứa source code các sơ đồ kỹ thuật của báo cáo, dùng kèm với các file `.tex` ở `components/contents/`.

## Quy ước file

| Đuôi | Loại | Cách render |
|---|---|---|
| `*.tex` | TikZ — render trực tiếp khi compile LaTeX | `\input{components/diagrams/<tên>}` trong file chương |
| `*.puml` | PlantUML — sequence/activity diagram | `plantuml file.puml -tpng` → đặt PNG vào `Images/` |
| `*.drawio` | draw.io / diagrams.net | Mở bằng [diagrams.net](https://app.diagrams.net) → Export PNG → đặt vào `Images/` |
| `*.mmd` | Mermaid (chưa dùng, để dự phòng) | `mmdc -i file.mmd -o file.png` |

## Danh sách sơ đồ

### Đã có (TikZ — `\input` trực tiếp)

| File | Vai trò trong báo cáo | ID kế hoạch |
|---|---|---|
| `architecture_3layer.tex` | Sơ đồ kiến trúc 3 lớp Frontend ↔ Backend ↔ Services | B1 |
| `langgraph_topology.tex` | Sơ đồ luồng LangGraph 13 node + 3 conditional edge | B2 |

### Đã có (PlantUML — cần render thành PNG)

| File | Vai trò trong báo cáo | ID kế hoạch |
|---|---|---|
| `persistence_sequence.puml` | Sequence Persistence + HITL Resume | B5 |

### Cần bổ sung (theo `REVISION_PLAN.md`)

| Vai trò | Phương án đề xuất | ID |
|---|---|---|
| Multi-Query RAG flow (Q1+Q2+Q3 + control mappings) | TikZ | B3 |
| Langfuse dashboard | Screenshot | B6 |
| Frontend screenshots (Chat/Timeline/Evidence/Settings) | Screenshot từ UI thật | C2 |
| Frontend component tree | TikZ hoặc draw.io | C2 |
| Chatbot API sequence (start_run → daemon → resume) | PlantUML | C3 |
| Report 5-step pipeline (data_builder → ... → exporters) | TikZ | C5 |

## Workflow render PlantUML → PNG

```bash
# Cài plantuml (chỉ 1 lần)
# Windows: choco install plantuml  hoặc tải plantuml.jar
# Linux:   sudo apt install plantuml

# Render 1 file
plantuml components/diagrams/persistence_sequence.puml -tpng -o ../../Images/

# Render tất cả
plantuml components/diagrams/*.puml -tpng -o ../../Images/
```

Sau khi render xong, dùng trong `.tex`:

```latex
\begin{figure}[H]
  \centering
  \includegraphics[width=0.9\textwidth]{Images/persistence_sequence.png}
  \caption{...}
  \label{fig:persistence_sequence}
\end{figure}
```

## Workflow dùng TikZ (đơn giản nhất)

Trong file chương (ví dụ `Approach.tex`), chỉ cần:

```latex
\input{components/diagrams/langgraph_topology}
```

Khi compile `main.tex`, TikZ sẽ render trực tiếp thành vector trong PDF — không cần file ảnh trung gian.

**Lưu ý**: phải có các tikzlibrary sau trong preamble của `main.tex`:

```latex
\usetikzlibrary{arrows.meta, positioning, shapes.geometric, fit, calc, backgrounds}
```

Báo cáo hiện tại đã có `\usetikzlibrary{arrows,snakes,backgrounds,calc}`, **cần bổ sung** `arrows.meta, positioning, shapes.geometric, fit` cho 2 sơ đồ TikZ mới.

## Ưu/nhược của từng phương án

### TikZ
- ✅ Vector chất lượng cao trong PDF, không bị mờ khi zoom
- ✅ Đồng bộ font với báo cáo
- ✅ Không cần file ảnh ngoài, dễ version control
- ❌ Code dài, sửa visual không trực quan
- ❌ Compile chậm hơn nếu có nhiều TikZ

### PlantUML
- ✅ Sequence diagram cực nhanh, code ngắn
- ✅ Style mặc định đẹp, đồng bộ
- ❌ Cần render thành PNG, mất 1 bước
- ❌ Tùy biến giao diện hạn chế

### draw.io
- ✅ GUI trực quan, có sẵn icon AWS/Cloud
- ✅ Phù hợp sơ đồ phức tạp nhiều màu sắc
- ❌ Phụ thuộc tool ngoài
- ❌ Khó version control diff (XML rối)

### Screenshot
- ✅ Cách duy nhất cho UI / dashboard thật
- ❌ Phải có hệ thống chạy được, capture đúng kích thước
- ❌ Bị lỗi thời khi UI thay đổi

## Khi nào dùng phương án nào?

| Loại sơ đồ | Phương án tối ưu |
|---|---|
| Graph có node + cạnh tuyến tính | TikZ |
| Block diagram nhiều layer | TikZ |
| Sequence diagram | PlantUML |
| Activity / state machine đơn giản | TikZ hoặc PlantUML |
| Sơ đồ phức tạp >15 node, nhiều icon | draw.io |
| UI screenshot, dashboard | Screenshot |
