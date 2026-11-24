# Baseline Structured Table QA

Hai cấu hình dùng cùng 40 packet, Qwen 3.5 9B, budget 12 và một tool call cho mỗi lượt executor.

## Single-agent

Router chỉ dispatch `Table QA Agent` cho đến khi public verification đạt, sau đó chọn `STOP`. Agent luôn nhận đủ bảy tool và tự quyết định thao tác tiếp theo. Tool gọi sai thời điểm trả lỗi công khai qua cùng contract mà các router khác nhận khi chọn một role chưa đủ precondition.

Baseline này đo khả năng Qwen tự lập kế hoạch và sử dụng tool khi không có router phân vai.

## Predefined trajectory

Policy chạy một sequence specialist cố định khai báo trực tiếp trong YAML. Sequence hiện tại là inspect, resolve header, select evidence, analyze, verify, diagnose/compose và một vòng select/analyze/verify dự phòng. Policy không đổi nhánh theo state và vẫn tiến sang bước kế tiếp nếu action bị precondition reject.

Ngoại lệ duy nhất là dừng ngay khi trường công khai `current_state.terminal` đã đạt. Nếu hết sequence mà terminal chưa đạt, policy chọn `STOP` và runner ghi `PREMATURE_STOP`.

Baseline này đo kết quả của một workflow được xác định trước và không gọi model router.

## So sánh

Hai cấu hình giữ nguyên packet, executor, budget, tool implementation, public state và trusted evaluator. Khác biệt nằm ở quyền chọn thao tác. Single-agent giao quyền chọn tool cho Qwen. Predefined trajectory giao quyền chọn specialist cho policy cố định.
