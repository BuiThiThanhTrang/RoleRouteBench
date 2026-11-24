# Single-agent baseline cho bốn domain

## Contract chung

Mỗi domain chỉ có một role generalist. Router `single_agent` dispatch lại đúng agent đó cho đến khi trường công khai `current_state.terminal` bằng `true`, sau đó chọn `STOP`. Router không gọi model routing và không đọc private evaluator.

Role card dùng `tool_access: all_domain_tools`. Adapter chuyển quyền này thành hợp của toàn bộ tool mà các specialist trong cùng domain đang sở hữu. Tool validator, state precondition, public error và terminal contract không thay đổi; generalist vẫn có thể chọn sai tool hoặc gọi tool sai thời điểm và phải tự phục hồi từ feedback công khai.

Agent nhận cùng task, public state, artifact, recent tool feedback và execution contract như executor trong dynamic routing. Agent không nhận private reference, gold answer hay oracle-valid action.

## Cấu hình

| Domain | Agent | Backbone | Budget | Config |
|---|---|---:|---:|---|
| Database migration | Database Migration Agent | Qwen 3.5 9B | 8 | `database_single_agent_qwen9b.yaml` |
| Code debugging | Code Debugging Agent | Gemini 2.5 Flash | 8 | `code_single_agent_gemini25flash.yaml` |
| Formal proof | Formal Proof Agent | Goedel Prover V2 32B | 8 | `formal_single_agent_goedel32b.yaml` |
| Structured data / Table QA | Table QA Agent | Qwen 3.5 9B | 12 | `table_qa_single_agent_qwen9b.yaml` |

Backbone, packet root, runtime, budget và executor limits được giữ giống cấu hình dynamic/predefined tương ứng. Chỉ agent pool và router policy thay đổi.

## Lệnh chạy

Chạy từ thư mục `RoleRouteBench`:

```powershell
python scripts/run_shared_environment.py --config config/shared_environment/database_single_agent_qwen9b.yaml --run-id database_single_agent_qwen9b
python scripts/run_shared_environment.py --config config/shared_environment/code_single_agent_gemini25flash.yaml --run-id code_single_agent_gemini25flash
python scripts/run_shared_environment.py --config config/shared_environment/formal_single_agent_goedel32b.yaml --run-id formal_single_agent_goedel32b
python scripts/run_shared_environment.py --config config/shared_environment/table_qa_single_agent_qwen9b.yaml --run-id table_qa_single_agent_qwen9b
```

Baseline này đo khả năng backbone tự lập kế hoạch và tự chọn tool khi không có router phân vai. Khi so sánh với dynamic routing, cần giữ nguyên các config executor và chỉ thay config router/role card như các file trên.
