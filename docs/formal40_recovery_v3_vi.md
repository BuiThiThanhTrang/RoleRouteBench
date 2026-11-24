# Profile recovery v3: chuẩn hóa trình bày và candidate trùng

> Cập nhật dẫn chiếu 2026-11-20: phần pilot ban đầu dưới đây dùng input 8192;
> profile input12k và batch final dùng 12288. Đặc tả đầy đủ theo code hiện tại:
> [State và protocol](formal_proof_state_protocol_vi.md),
> [Harness, runtime và luồng thông tin](formal_proof_harness_information_flow_vi.md).

V3 là profile thử mới, tiếp tục dùng `artifact_first_v2` và
`bounded_artifact_handoff_v2`, thêm hai cờ opt-in:

- executor.formal_protocol.parser_policy: presentation_v1
- runtime.formal_candidate_identity: lean_tokens_layout_v1

Không đổi packet, role cards, backbone Pythagoras, JEV, sampling/thinking,
runtime Lean/Mathlib hoặc budget so với profile recovery v2. Profile và run v2
giữ nguyên để đối chiếu; source freeze yêu cầu run ID mới khi đổi source.

## Implementation plan và kết quả

1. Thống nhất prompt/parser với adapter: proof term, theorem declaration hoặc
   full source, plain Lean hoặc code fence hoàn chỉnh. Parser chỉ chuyển nội
   dung sang adapter hiện tại, không xóa/chèn Lean hay thử nhiều proof để chọn
   proof pass. Adapter tiếp tục kiểm tra immutable statement/context, command
   policy; compiler/kernel/dependency gate giữ nguyên. Fence chưa đóng, output
   bị cắt hoặc bị phát hiện lặp không được cứu thành proof.
2. Diagnosis giữ cùng năm nhãn và nội dung. Cho phép số thứ tự, bullet,
   Markdown bold trước nhãn, không suy diễn nhãn/điền trường thiếu. Các trường
   xung đột bị từ chối. Raw response vẫn nguyên trong trajectory. Giới hạn
   trường, partial status và quy tắc xử lý lỗi mạng của v2 giữ nguyên.
3. Tạo fingerprint từ token Lean: bỏ comment lồng nhau, blank lines và spacing
   trong dòng; giữ string/char/raw-string/quoted-identifier literals nguyên vẹn.
   Giữ indentation và ranh giới dòng vì Lean có cú pháp phụ thuộc layout.
   Input có comment/literal chưa đóng dùng exact-source fallback. Đây là nhận
   diện trình bày bảo thủ, không chứng minh hai proof tương đương về toán học.
4. Giữ raw SHA-256 và thêm source_identity/candidate presentation identity.
   Trong profile mới, candidate_changed phản ánh fingerprint; source_changed
   trong role_progress phản ánh raw bytes. Candidate chỉ khác comment/spacing
   có duplicate_candidate=true và bộ đếm trùng theo role. Router và executor
   nhìn thấy cùng các trường này, còn source raw và artifact không bị sửa.
5. Semantic delta so sánh fingerprint candidate và nội dung evidence, bỏ qua
   ID, counters, raw hash và thay đổi freshness đơn thuần do trình bày. Terminal
   status vẫn là thay đổi thực. Freshness compiler/verifier tiếp tục dựa trên
   exact source hash: source mới vẫn cần compile/verify. Không dùng fingerprint
   làm cache kết quả kiểm chứng, không tự bỏ call, đổi role hay STOP.
6. Replay các lỗi format đã ghi trong pilot: ba full-source response và hai
   numbered-diagnosis response. Kiểm tra cả negative cases: sửa statement,
   context, string literal, indentation, dangling fence, truncation. Đối chiếu
   cặp candidate sample 16 chỉ khác comment; kiểm tra call accounting/action
   space và handoff đến router/executor. Không gọi model để replay.

Parser không diễn giải code Lean thuần như văn xuôi khi phát hiện lặp paragraph;
trần output và detector recursive-open-tactic vẫn giữ nguyên. Proof được nhận
chỉ có nghĩa có thể đi tiếp tới checker, không đồng nghĩa proof đúng.

## Lệnh chạy lại đúng 6 sample

PowerShell; dùng Python Formal đã kiểm định. Cần HF_TOKEN và OPENROUTER_API_KEY
như các run trước. Budget vẫn 12 role calls; proof 4096, diagnosis/retrieval
1024, input 8192 tokens.

```powershell
$repo = (Resolve-Path '.').Path
$py = (Get-Command python).Source
$config = "$repo/config/shared_environment/formal40_recovery_v3_lean48_jev.yaml"

& $py "$repo/scripts/run_formal_runtime_audit.py" `
  --config $config `
  --run-id formal40_jev_recovery_v3_lean48_pilot6_b12 `
  --packet formal40-09-leandojo --packet formal40-10-leandojo `
  --packet formal40-12-leandojo --packet formal40-13-leandojo `
  --packet formal40-15-leandojo --packet formal40-16-leandojo
```

Profile tương ứng Lean 4.22 cũng có tại
`config/shared_environment/formal40_recovery_v3_lean422_jev.yaml`.

## Kiểm định

`tests/test_formal_presentation.py` kiểm tra parser, raw preservation, identity,
freshness, số calls, 8 lựa chọn routing và replay từ pilot đã hoàn tất.
`tests/test_formal_handoff.py` kiểm tra regression v1/v2.

Preflight toàn bank:

```powershell
& $py "$repo/scripts/check_formal_executor_protocol.py" --profile-prefix formal40_recovery_v3 --output "$repo/runs/formal_recovery_v3_preflight_user01" --real-lean
```

Native smokes dùng witness test double để kiểm tra đường full-source/parser/
adapter/checker; không phải kết quả model, không đo recovery hoặc ranking router.

Kết quả thực hiện 2026-11-19: 61 test pass (1 native test mặc định skip, được
kiểm tra riêng bằng smoke); 40 packet/280 context qua gate. Kiểm tra bổ sung 41
context executor đã lưu xác nhận source vẫn đủ và lý do verifier từ chối không
bị mất khi thêm metadata identity. Offline replay nhận 5/5 output từng bị chặn
format và nhận đúng cặp candidate sample 16 chỉ khác comment; raw không đổi.

Lượt preflight native đầu bị Inspector timeout 180 giây ở sample 09, dù
compile/kernel đã pass. Chạy lại cùng cấu hình đã qua Inspector và evaluator
trên cả hai runtime; không tăng timeout hay budget. Evidence:

- runs/formal_recovery_v3_preflight_20261119/context_report.json
- runs/formal_recovery_v3_replay_20261119/report.json
- runs/formal_recovery_v3_native_retry_20261119/lean48_report.json
- runs/formal_recovery_v3_native_retry_20261119/lean422_report.json
- runs/formal_recovery_v3_implementation_20261119/report.json

Không chạy trajectory JEV mới hoặc gọi model trong kiểm định này. Lệnh pilot ở
trên là bước đo performance tiếp theo, dùng run ID mới và cùng 6 task của v2.

## Profile input 12k và compile Lean 300 giây

Theo yêu cầu tiếp theo, profile riêng
`formal40_recovery_v3_input12k_lean48_jev.yaml` chỉ tăng
`executor.formal_protocol.input_max_tokens` lên 12288 và thêm
`runtime.compile_timeout_seconds: 300`. Mặc định 180 giây vẫn áp dụng cho các
profile cũ không khai báo timeout. Tham số runtime này dùng cho compile_proof,
kernel probe và các phép lookup gọi cùng compiler. Inspector vẫn dùng timeout
cũ; HTTP timeout model vẫn 300 giây. Không thêm warm-up hoặc retry tự động.
Budget vẫn 12 role calls, proof output 4096 và diagnosis/retrieval 1024 token.
Giới hạn preview source 8000 ký tự chưa thay đổi trong profile này.

Kiểm tra resource profile: `tests/test_formal_resource_limits.py` xác nhận
đúng hai thay đổi, forwarding timeout cho Main.lean/assumptions.lean, giữ
default 180 cho profile cũ và dựng lại context cuối sample 16 dưới cap 12k.
Không gọi model hoặc chạy warm-up trong kiểm tra này.

Chạy lại riêng hai sample 09 và 16, dùng run ID mới:

```powershell
& (Get-Command python).Source `
  '<ROLE_ROUTEBENCH_ROOT>\scripts\run_formal_runtime_audit.py' `
  --config '<ROLE_ROUTEBENCH_ROOT>\config\shared_environment\formal40_recovery_v3_input12k_lean48_jev.yaml' `
  --run-id formal40_jev_recovery_v3_input12k_lean48_pilot2_b12 `
  --packet formal40-09-leandojo --packet formal40-16-leandojo
```

## Profile Lean 4.22 và batch final bốn router

Profile resource tương ứng là
`config/shared_environment/formal40_recovery_v3_input12k_lean422_jev.yaml`:
input 12288, compile timeout 300 giây, Inspector 180 giây, budget 12. Pilot
Lean 4.22 đã chạy với sample APRIL 29, 33, 36, 38 ở run
`formal40_jev_recovery_v3_input12k_lean422_pilot4_b12`.

Batch full hiện dùng tám config trong
`config/shared_environment/formal40_final_v3_input12k_b12/`, mỗi router có một
config Lean 4.8 (30 packet) và một config Lean 4.22 (10 packet). Các setting
ngoài router và thông tin cohort giống nhau. `artifact_first_v2`,
`bounded_artifact_handoff_v2`, `presentation_v1`, `lean_tokens_layout_v1` và
`tactic_state_v1` đều được bật; proof 4096, diagnosis/retrieval 1024. Model calls
dùng temperature 0.6/top_p 0.95; chỉ hai role auxiliary yêu cầu tắt thinking.

Batch này dùng wrapper `scripts/run_shared_environment_sol.py` cho cả bốn
router để hỗ trợ SOL type `llm`. Phải truyền explicit `--packet` selection;
wrapper/shared runner không tự lọc `runtime_audit`. Các run có prefix
`formal40_final_v3_input12k_b12_`; không suy setting từ prefix, đọc
`resolved_config.json` và `runtime.json` để xác nhận.

Xem tài liệu harness hiện hành để phân biệt Success/ProofPass, API errors,
compile timeout, giới hạn chuyển tiếp transport feedback và quy tắc chạy lại
attempt lỗi dịch vụ. Không coi mọi lỗi được đánh dấu infrastructure là nhiễu
môi trường hoặc bằng chứng model yếu.
