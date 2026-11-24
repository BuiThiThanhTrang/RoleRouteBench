# Sửa tối thiểu inspection revisit

Ngày 2026-11-22. Adapter được bổ sung5 dòng trong execute_tool.

Khi inspect_table trả lại một artifact đã có, adapter kiểm tra artifact đó có
trong public observation trước thao tác không. Nếu đang bị khuất, current.inspection
trỏ về artifact đó và tool trả success vì state đã khôi phục thông tin cho lượt sau.
History và nội dung artifact cũ được giữ nguyên. Một cached inspection đang hiện
diện vẫn trả no_progress với state giữ nguyên.

Đây là sửa trường hợp slice bị khuất, giữ cách projection hiện có: current,
ba inspection tạo gần nhất và các dependency của answer. Chỉ khi khôi phục slice
bị khuất, current đưa thêm đúng slice được yêu cầu vào view.

## Kiểm chứng

- Hai regression test mới thất bại trên code cũ và pass sau sửa.
- Stress offsets0,12,24,36,0,0: khôi phục slice cũ, giữ4 artifact gốc, không tạo
  progress khi đọc lại slice đang hiện diện; đủ7 role nhận slice qua context.
- Handoff qua shared runner:5 inspection, Evidence Selector, Numerical Analyst,
  Evidence Verifier và STOP; task WTQ nu-10 đạt trusted gold với8 executor calls.
- Tổng20 test pass, gồm all40 reference paths, shared router protocol, predefined
  workflow và single-agent policy.
- Replay sáu full run: JEV, SOL, DREX, PPLX, single-agent và predefined. So sánh
  public states, preconditions, toàn bộ ToolResult và final state.

Evidence cuối ở runs/structured_data_inspection_fix_20261122/report.json và
replay_report.json. Logs trước/sau và adapter_change.patch được giữ cùng thư mục.
Raw historical runs và packet bank được giữ nguyên.

## Diễn giải replay

Nếu sáu run đều tương đương, không cần gọi model chạy lại chỉ để xử lý lỗi này.
Replay xác nhận những state/tool calls thực tế đã ghi; không tái sinh quyết định
model và không gán source hash mới cho run cũ. Future runs dùng source snapshot
sau sửa; resume vẫn phải tuân thủ source freeze của runner.
