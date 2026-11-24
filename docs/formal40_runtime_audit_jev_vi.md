# Audit hai runtime Formal40 với JEV

> Các lệnh/config dưới đây là baseline audit JEV trước handoff/recovery mới.
> Tài liệu runtime/harness hiện hành ngày 2026-11-20 ở
> [Harness và luồng thông tin](formal_proof_harness_information_flow_vi.md);
> profile final và state/protocol ở
> [State và protocol](formal_proof_state_protocol_vi.md). Gate audit vẫn hữu ích,
> nhưng launcher gốc không hỗ trợ SOL type `llm`; wrapper SOL cần explicit
> packet selection, không tự áp dụng bộ lọc `runtime_audit`.

Hai cấu hình audit dùng bank formal40_pythagoras_v1_20261118 hiện tại:

| Config | Lean | Packet |
|---|---|---:|
| formal40_audit_lean48_jev.yaml | 4.8.0-rc1 | 30 |
| formal40_audit_lean422_jev.yaml | 4.22.0-rc4 | 10 |

Cả hai dùng typesafe/jev-1.13 làm router, Pythagoras-Prover-4B:featherless-ai
làm executor, budget 12, seed 42, một worker và đầy đủ 7 role cùng STOP.
Giữ nguyên packet, tool protocol, prompt và evaluator của shared environment.

Chọn packet dựa vào trường toolchain trong public/execution_contract.json.
Tên packet và provenance dataset không tham gia quyết định chọn runtime.
Entry point run_formal_runtime_audit.py kiểm tra số lượng packet, manifest,
Lean binary, toolchain/dependency lock và Mathlib checkout trước khi chuyển
danh sách packet vào shared runner qua các cờ --packet. Danh sách thực chạy
được shared runner lưu trong resolved_config.json. Không chạy trực tiếp
run_shared_environment.py với hai config audit: script đó không lọc runtime_audit.

Đây là audit hai nhóm đề khác nhau, không phải A/B cùng đề trên hai phiên bản.
Không suy ra tác động riêng của runtime từ chênh lệch accuracy giữa hai nhóm.
Mục tiêu là xem backbone có sử dụng được context, công cụ và feedback của mỗi
môi trường để tiến triển, hay thường mắc kẹt vì tên lemma/API, thiếu tài nguyên,
contract hoặc infrastructure. Khi đọc kết quả, phân biệt lỗi proof thông thường,
lỗi contract/tool, lỗi dịch vụ và lỗi tương thích phiên bản.

Chạy từ root repo, với OPENROUTER_API_KEY và HF_TOKEN trong môi trường hoặc .env.

```powershell
python scripts/run_formal_runtime_audit.py --config config/shared_environment/formal40_audit_lean48_jev.yaml --run-id formal40_audit_jev_pythagoras_lean48_b12
python scripts/run_formal_runtime_audit.py --config config/shared_environment/formal40_audit_lean422_jev.yaml --run-id formal40_audit_jev_pythagoras_lean422_b12
```

Đánh giá độc lập sau khi hai run hoàn tất:

```powershell
python scripts/evaluate_shared_environment.py runs/formal40_audit_jev_pythagoras_lean48_b12
python scripts/evaluate_shared_environment.py runs/formal40_audit_jev_pythagoras_lean422_b12
```

Thêm --check-only vào entry point audit để chỉ kiểm tra cấu hình, packet và
runtime; không tạo run hoặc gọi model. Có thể dùng --resume theo quy tắc của
shared runner: source/config phải khớp, workspace dang dở không tự động reset.
