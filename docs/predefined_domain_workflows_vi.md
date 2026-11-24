# Predefined workflow cố định cho bốn domain

## Contract

`router.type: predefined_workflow` chạy đúng danh sách `router.sequence` theo thứ tự. Router không chọn role từ trạng thái, không gọi model routing và không đổi nhánh khi một action bị từ chối. Mỗi lần chọn một role sẽ tiến cursor sang bước tiếp theo.

Ngoại lệ duy nhất là `stop_on_terminal: true`: nếu `current_state.terminal` công khai đã bằng `true`, router chọn `STOP` ngay. Đây không phải oracle riêng; dynamic router cũng nhìn thấy cùng trường terminal. Cơ chế này tránh gọi thêm agent sau khi task đã hoàn thành.

Khi hết sequence mà terminal chưa đạt, router chọn `STOP`; runner sẽ ghi `PREMATURE_STOP`. Vì vậy baseline vẫn đo được cả hai phía:

- workflow thiếu bước sẽ dừng sớm;
- workflow có bước dư nhưng task đã xong sẽ không đốt hết budget.

Router vẫn nhận observation đầy đủ theo runner dùng chung, nhưng chỉ đọc `current_state.terminal`. Agent được dispatch vẫn nhận nguyên role card, public state, recent tool feedback và allowed tools như trong dynamic routing. Contract không làm giảm thông tin của executor.

## Cách suy ra workflow

Các chuỗi dưới đây được rút từ transition và trajectory của những episode pass trong các run JEV, SOL, DREX và PPLX hiện có. Mục tiêu là lấy đường đi chung, rồi dành phần ngân sách còn lại cho một vòng recovery cố định; không chọn riêng chuỗi tối ưu cho một router.

### Database migration integrity

```text
Schema Inspector
→ SQL Migration Author
→ Transactional Dry-run Executor
→ Integrity Validator
→ SQL Migration Author
→ Transactional Dry-run Executor
→ Integrity Validator
```

Đường chính `Schema Inspector → SQL Migration Author → Transactional Dry-run Executor → Integrity Validator` là exact sequence phổ biến nhất trong episode pass. Ba bước cuối là một vòng sửa–chạy–kiểm tra nếu vòng đầu chưa terminal.

Config: `config/shared_environment/database_predefined_qwen9b.yaml`.

### Code debugging

```text
Repository Test Reproducer
→ Failure Diagnostician
→ Patch Author
→ Regression Verifier
→ Failure Diagnostician
→ Patch Author
→ Regression Verifier
```

Đây là core path phổ biến nhất của episode pass. `Verified Patch Consumer` và `Patch Finalizer` không được đưa vào vì terminal contract hiện tại chỉ yêu cầu fresh passing candidate validation; chúng là packaging tùy chọn. Nếu lần verify đầu pass, terminal short-circuit dừng ngay. Nếu fail, workflow có một vòng diagnose–patch–verify nữa.

Config: `config/shared_environment/code_predefined_gemini25flash.yaml`.

### Formal proof

```text
Tactic Synthesizer
→ Lean Compiler Executor
→ Kernel and Assumption Verifier
→ Formal Failure Diagnostician
→ Proof Repair Specialist
→ Lean Compiler Executor
→ Kernel and Assumption Verifier
```

`Tactic Synthesizer → Lean Compiler Executor → Kernel and Assumption Verifier` áp đảo trong episode pass. Bốn bước sau tạo một vòng chẩn đoán và repair khi compile hoặc kernel verification chưa đạt.

Config: `config/shared_environment/formal_predefined_goedel32b.yaml`.

Config trên dùng bank/backbone/budget lịch sử. Formal40 dùng Pythagoras và
budget 12 đã có hai config `formal40_fixed_lean48_pythagoras_b12.yaml` và
`formal40_fixed_lean422_pythagoras_b12.yaml`, khớp setting của batch final ngoài
router. Sequence gồm đường chính và hai vòng recovery (11 bước), vẫn giữ
terminal short circuit và precondition-rejection semantics. Dùng runtime audit
launcher để chọn đúng 30/10 packet. Xem [Formal40 fixed baseline](formal40_fixed_baseline_vi.md).

### Structured data / Table QA

```text
Table Inspector
→ Header Resolver
→ Evidence Selector
→ Numerical Analyst
→ Evidence Verifier
→ Failure Diagnoser
→ Answer Composer
→ Evidence Verifier
→ Evidence Selector
→ Numerical Analyst
→ Evidence Verifier
```

Table QA có trajectory đa dạng nhất: lookup trực tiếp thường đi `Table Inspector → Answer Composer → Evidence Verifier`, còn task lọc/tính toán thường đi `Evidence Selector → Numerical Analyst → Evidence Verifier`. Workflow cố định hợp nhất cả hai và thêm `Header Resolver` cho bảng phân cấp. Nếu `Numerical Analyst` chưa submit answer, lần verify đầu có thể bị precondition reject; sequence vẫn tiếp tục tới `Answer Composer`, đúng với semantics fixed workflow.

Config: `config/shared_environment/table_qa_predefined_qwen9b.yaml`.

## Lệnh chạy

Chạy từ thư mục `RoleRouteBench`:

```powershell
python scripts/run_shared_environment.py --config config/shared_environment/database_predefined_qwen9b.yaml --run-id database_predefined_qwen9b
python scripts/run_shared_environment.py --config config/shared_environment/code_predefined_gemini25flash.yaml --run-id code_predefined_gemini25flash
python scripts/run_shared_environment.py --config config/shared_environment/formal_predefined_goedel32b.yaml --run-id formal_predefined_goedel32b
python scripts/run_shared_environment.py --config config/shared_environment/table_qa_predefined_qwen9b.yaml --run-id table_qa_predefined_qwen9b
```

Không nên gọi baseline này là dynamic router. Nó là một control cố định để tách lợi ích của việc chọn nhánh theo state khỏi lợi ích đơn thuần của một pipeline role tốt.
