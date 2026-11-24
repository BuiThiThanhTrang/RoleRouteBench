# Formal40 fixed baseline với Pythagoras, budget 12

Ngày 2026-11-22. Baseline này dùng cùng môi trường với batch
`formal40_final_v3_input12k_b12`, thay duy nhất phần chọn role bằng policy
`predefined_workflow` hiện có. Đây là chuỗi cố định, không phải router LLM hay
policy tự chọn nhánh theo compiler feedback.

## Kiến trúc và phạm vi thay đổi

- `run_formal_runtime_audit.py`: kiểm định packet/runtime lock, lọc cohort theo
  public toolchain rồi gọi shared runner với selection cụ thể.
- `run_shared_environment.py`: dùng factory hiện có để tạo
  `PredefinedWorkflowPolicy`; không cần wrapper SOL.
- `SharedTrajectoryRunner`: giữ nguyên budget, precondition, STOP và logging.
- `FormalRoleActor` + `FormalProofV2Adapter`: giữ nguyên context, handoff,
  generation, parser, candidate identity, công cụ và evidence của dynamic runs.
- `evaluate_shared_environment.py`: dùng cùng independent checker sau run.

Audit report đã được sửa để router không có model dùng tên policy ở trường
`router`, tránh KeyError với predefined workflow. Không thêm model routing.

## Hai cấu hình

| Config trong `config/shared_environment` | Lean | Packet |
|---|---|---:|
| `formal40_fixed_lean48_pythagoras_b12.yaml` | 4.8.0-rc1 | 30 |
| `formal40_fixed_lean422_pythagoras_b12.yaml` | 4.22.0-rc4 | 10 |

Mỗi config khớp hoàn toàn các trường ngoài `router` với config JEV cùng cohort
trong `formal40_final_v3_input12k_b12/`:

- Bank `formal40_pythagoras_v1_20261118`, đủ pool 7 role, private reference ẩn.
- Executor `Pythagoras-LM/Pythagoras-Prover-4B:featherless-ai` qua Hugging Face.
- Budget 12 role calls, worker 1, seed 42.
- Protocol `artifact_first_v2`, parser `presentation_v1`, handoff v2,
  identity `lean_tokens_layout_v1`, Inspector `tactic_state_v1`.
- Input 12288; proof output 4096; diagnosis/retrieval 1024; ceiling 16384.
- Temperature 0.6/top_p 0.95; chỉ Diagnostician/Retriever yêu cầu tắt thinking.
- Compile timeout 300 giây, HTTP timeout 300 giây; Inspector vẫn 180 giây.

## Sequence và accounting

```text
Synthesizer → Compiler → Verifier
→ Diagnostician → Repair → Compiler → Verifier
→ Diagnostician → Repair → Compiler → Verifier
→ STOP
```

Tổng 11 bước non-STOP, gồm đường chính và hai vòng recovery, trong trần 12.
`stop_on_terminal=true`: khi verifier pass và evidence fresh, policy dừng ngay,
thường sau bước 3, 7 hoặc 11. Nếu hết sequence mà chưa terminal, policy STOP và
runner ghi `PREMATURE_STOP`; không tự sinh vòng thứ ba. Budget cap không bắt
buộc phải dùng hết 12 calls.

Policy luôn chạy đúng thứ tự trên, kể cả APRIL đã có initial candidate. Nó không
đổi sequence theo nguồn task, không tự thêm Inspector/Retriever, không bỏ qua
Diagnosis theo độ dễ của lỗi. Executor vẫn nhận đủ public evidence của role.

**Precondition giữ nguyên semantics của chuỗi cứng:** nếu Compiler fail thì
Verifier kế tiếp bị reject và vẫn tiêu thụ một role call. Policy tiếp tục sang
Diagnosis, không sửa lựa chọn hay bỏ qua bước giúp baseline. Rejected action
không gọi backbone. Vì vậy đây là control cho literal fixed sequence, chưa phải
baseline theo quy tắc có gating theo trạng thái. Khi báo cáo lợi ích dynamic,
cần tách số call tiết kiệm do tránh rejection khỏi lợi ích chọn reviewer/phương
pháp phục hồi phù hợp; không diễn giải nó như đã thắng mọi fixed pipeline.

## Chạy

Dùng Python Formal đã kiểm định, `HF_TOKEN` lấy từ environment/.env như các run
trước. Policy fixed không cần OpenRouter credential. Kiểm định không gọi model:

```powershell
$project = '<ROLE_ROUTEBENCH_ROOT>'
$py = (Get-Command python).Source
foreach ($runtime in @('lean48', 'lean422')) {
    & $py "$project\scripts\run_formal_runtime_audit.py" `
        --config "$project\config\shared_environment\formal40_fixed_${runtime}_pythagoras_b12.yaml" `
        --check-only
    if ($LASTEXITCODE -ne 0) { throw "Preflight failed: $runtime" }
}
```

Chạy đủ 40 packet, tuần tự hai cohort và chấm độc lập sau mỗi run:

```powershell
$project = '<ROLE_ROUTEBENCH_ROOT>'
$py = (Get-Command python).Source
foreach ($runtime in @('lean48', 'lean422')) {
    $config = "$project\config\shared_environment\formal40_fixed_${runtime}_pythagoras_b12.yaml"
    $runId = "formal40_fixed_${runtime}_pythagoras_b12"

    & $py "$project\scripts\run_formal_runtime_audit.py" --config $config --run-id $runId
    if ($LASTEXITCODE -ne 0) { throw "Run failed: $runId" }

    & $py "$project\scripts\evaluate_shared_environment.py" "$project\runs\$runId"
    if ($LASTEXITCODE -ne 0) { throw "Evaluation failed: $runId" }
}
```

Chỉ chọn subset để pilot bằng các cờ `--packet` lặp lại; audit vẫn kiểm định
toàn cohort trước khi lọc. Dùng run ID khác cho pilot và full run. Không chạy
trực tiếp shared runner với config audit mà bỏ selection: shared runner không
tự áp dụng `runtime_audit`.

## Kiểm tra và so sánh

Trước khi giao lệnh đã đối chiếu equality ngoài router, kiểm tra mọi role trong
sequence thuộc pool, trần calls, thứ tự chính xác, terminal short circuit, runtime
lock/tokenizer cho cả 30/10 packet. Không gọi hosted model trong bước cấu hình.

Sau run đọc `freeze_verification.json`, `resolved_config.json`, `runtime.json`,
`evaluation_report.json` và trajectory. `metrics.token_usage` chứa usage provider
trả về; xem thêm `responses_without_provider_usage` và
`provider_token_usage_complete`, không coi usage thiếu là zero.

So sánh Success/ProofPass/recovery cùng executor tokens và calls. Token savings
trên shared-success packets phải báo kèm số packet và Success trên toàn bộ tập;
sampling vẫn tạo biến thiên giữa dynamic và fixed, không suy lợi ích routing
chỉ từ một response dài/ngắn. Baseline fixed có zero model calls cho routing,
nhưng vẫn có inference calls của executor.

Kết quả hiện tại: fixed đã hoàn tất40 packet, 11 success, gồm recovery APRIL36.
Số liệu hiện hành nằm trong [bảng cuối đủ40 packet](../report/formal40_final_results.md):
recovery1/28, không còn infrastructure ở cả5 phương pháp; không dùng bảng cohort nhỏ cũ.
Xem [Nhận xét router/fixed cho release](formal40_router_fixed_release_observations_vi.md)
và [Chuẩn bị release kết hợp](formal40_release_preparation_vi.md).

Tài liệu liên quan: [State/protocol](formal_proof_state_protocol_vi.md),
[Harness và luồng thông tin](formal_proof_harness_information_flow_vi.md),
[Các predefined workflows lịch sử](predefined_domain_workflows_vi.md).
