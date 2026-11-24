# Formal recovery protocol v2

> Tài liệu này giữ profile/pilot v2 lịch sử (input 8192, chưa bật parser và
> presentation identity của v3). Batch final hiện dùng v3/input12k; tham khảo
> [State và protocol hiện hành](formal_proof_state_protocol_vi.md) và
> [Harness và luồng thông tin hiện hành](formal_proof_harness_information_flow_vi.md).

Profile thử nghiệm: `formal40_recovery_v2_lean48_jev.yaml` và
`formal40_recovery_v2_lean422_jev.yaml`. Không sửa packet hoặc cấu hình v1.
Hai profile tương ứng hai nhóm task khác nhau, không phải so sánh cùng task giữa runtime.

## Thay đổi

- `artifact_first_v2`, `bounded_artifact_handoff_v2` là opt-in; protocol v1 còn dùng được.
- Sampling chung: temperature 0.6, top_p 0.95. Diagnostician/Retriever gửi
  `extra_body.chat_template_kwargs.enable_thinking=false`; Synthesizer/Repair giữ
  mặc định provider. Không tự đổi mode khi endpoint từ chối tham số.
- Budget giữ 12 role calls; output proof 4096, diagnosis/retrieval 1024,
  input 8192. Trần executor tổng vẫn 16384. Không thêm request sửa format ngầm.
- Diagnosis: năm dòng ngắn Observed error / Location / Likely cause /
  Repair constraint / Uncertainty; cho phép unknown, tối đa 450 ký tự mỗi trường.
  Parser chỉ nhận trường đúng nhãn. Nếu length/repetition dừng response, chỉ giữ
  dòng đã kết thúc, có ít nhất Observed error và Location. Artifact ghi partial,
  generation_failure và unverified_assessment; raw response giữ nguyên để audit.
  Không cứu partial diagnosis khi lỗi mạng; không nộp proof bị cắt hoặc lặp.
- Feedback tool ưu tiên lỗi và lý do verifier từ chối trước warning. Structured
  critical chứa failed checks, dependency bị cấm, lỗi đầu tiên, hoặc focused
  proof state. Các trường này giữ được khi excerpt tiếp tục bị rút ngắn bởi
  input budget. Raw artifact vẫn nguyên, có checksum và read_ref.
- Router/executor cùng thấy role_progress: artifact tạo ra, candidate thay đổi
  hay trùng, generation failure, số lần lỗi liên tiếp của từng role. Không
  ép chọn role, không tự STOP, không bỏ tính phí call khi source trùng.
- latest_generation_failure giữ code, role, token count và mẫu lặp ngắn khi có;
  gắn input_versions/freshness và nhãn nội dung model chưa kiểm chứng. Không
  biến raw analysis hoặc proof dở dang thành lời giải hay diagnosis đã xác nhận.
- Semantic progress bỏ qua counters và artifact ID mới nếu nội dung không đổi.
  Success của write_source không được coi là compile/verification pass.

Đường gọi thực tế và trajectory đều ghi đúng sampling/thinking được gửi.
`thinking_requested=false` chỉ chứng minh request đã yêu cầu tắt; không khẳng
định biết trạng thái nội bộ của provider. Pythagoras public chat_template.jinja
có nhánh enable_thinking=false; Featherless công bố chat_template_kwargs:
https://huggingface.co/Pythagoras-LM/Pythagoras-Prover-4B/blob/main/chat_template.jinja
https://featherless.ai/docs/chat-template-kwargs

## Kiểm tra và chạy

PowerShell, dùng Python Formal đã kiểm định để tránh xung đột tokenizers với
Transformers cũ trong roleroutebench_env. Cần HF_TOKEN và OPENROUTER_API_KEY; runner
đọc .env của repo. Luôn dùng output/run ID mới.

```powershell
$repo = (Resolve-Path '.').Path
$py = (Get-Command python).Source
$config = "$repo/config/shared_environment/formal40_recovery_v2_lean48_jev.yaml"

& $py "$repo/scripts/run_formal_runtime_audit.py" --config $config --check-only

# Pilot 6 packet: có first-shot control, generation loop, compile failure và verifier rejection.
& $py "$repo/scripts/run_formal_runtime_audit.py" --config $config --run-id formal40_jev_recovery_v2_lean48_pilot6_b12 --packet formal40-09-leandojo --packet formal40-10-leandojo --packet formal40-12-leandojo --packet formal40-13-leandojo --packet formal40-15-leandojo --packet formal40-16-leandojo

# Chạy đủ 30 packet Lean 4.8: bỏ các cờ --packet, dùng run ID khác.
& $py "$repo/scripts/run_formal_runtime_audit.py" --config $config --run-id formal40_jev_recovery_v2_lean48_b12
```

`--packet` chỉ lọc trong cohort đã kiểm định Lean/Mathlib, không bỏ gate runtime.
Đổi tên config thành `formal40_recovery_v2_lean422_jev.yaml` để chạy 10 packet
Lean 4.22, với run ID riêng.

## Calibration cùng context

`calibrate_formal_executor.py` đọc request của episode đã hoàn tất, tạo lại
handoff v2 từ public artifacts theo đúng metadata/freshness trong request cũ,
không dùng source cuối episode để thay source tại lượt đó. Source run chỉ đọc.
Mỗi mode dùng cùng messages/input cap/output cap, không có router.

- greedy: temperature 0, không override thinking.
- sampled: temperature 0.6/top_p 0.95, không override thinking.
- aux_no_think: cùng sampling, chỉ tắt thinking Diagnosis/Retriever.
- all_no_think: thêm tắt thinking Synthesizer/Repair; chỉ bật khi cần ablation.

Script chọn context đầu tiên mỗi role/packet theo vòng Diagnosis, Repair,
Synthesis. Mặc định 8 context và 3 mode = tối đa 24 requests. Không diễn giải
artifact_eligible là task pass. `--check-proofs` compile/verify candidate hợp lệ
trong workspace riêng bằng checker hiện tại; không đọc private witness.
Không đánh giá recovery trajectory hoặc ranking router bằng công cụ này.

```powershell
& $py "$repo/scripts/calibrate_formal_executor.py" --config $config --run "$repo/runs/formal40_jev_handoff_inspector_lean48_b12" --output "$repo/runs/formal_recovery_v2_calibration_user01" --packet formal40-12-leandojo --packet formal40-13-leandojo --packet formal40-15-leandojo --packet formal40-16-leandojo --max-contexts 8 --check-proofs
```

Thêm `--check-only` chỉ render/context-check, không gọi model. Report giữ raw
response, finish reason, token usage khi provider trả về, generation settings,
hash của source trace, hash messages và native checker outputs nếu được yêu cầu.
So sánh nhiều lần trước khi chốt mode; không chọn profile theo router nào tăng điểm.

## Phạm vi kiểm định

Unit/regression test kiểm tra chính xác request ghi trong trace, partial diagnosis,
không cứu proof bị cắt, error-first handoff sau warning dài, goal/context ưu tiên,
candidate trùng và failure counters đến cả router/executor, và semantic progress.
`check_formal_executor_protocol.py --profile-prefix formal40_recovery_v2` kiểm tra
40 packet/280 role contexts; `--real-lean` thêm hai witness-backed integration
smoke qua native checker/evaluator. Witness smokes chỉ đo harness, không phải
performance của Pythagoras. Dùng run mới vì source freeze có thể từ chối resume v1.

## Pilot đã thực hiện, 2026-11-19

`runs/formal_recovery_v2_provider_pilot_network_20261119/report.json` chứa 6 request
thật trên 2 context của sample 12. Messages giống nhau giữa các mode của cùng
context; source trajectory giữ nguyên checksum. Kết quả Diagnosis: greedy và
sampled đều bị cắt ở 1024 token; aux_no_think trả đủ 5 trường trong 76 token,
trích đúng lỗi unknown constant IsEquiv.symm. Đây mới là một context.

Repair greedy bị chặn lặp; sampled tạo candidate 1067 token nhưng compile lỗi;
lượt aux_no_think cũng bị chặn lặp. Ở Repair, sampled và aux_no_think dùng cùng
tham số nên khác biệt này là biến thiên sampling, không phải tác động tắt thinking.
Không có proof pass từ pilot, không có kết quả JEV trajectory mới. Không suy ra
recovery rate hay quyết định tắt thinking mọi role từ thử nghiệm này.

Preflight 40/40 packet và 280/280 role context pass; native witness-backed
integration trên Lean 4.8 và 4.22 qua compile, kernel/dependency gate và evaluator
độc lập. Kết quả ở `runs/formal_recovery_v2_preflight_20261119/report.json`.
Lần gọi model đầu trong môi trường mạng hạn chế chỉ gặp lỗi kết nối, không dùng
để đo chất lượng executor; pilot network ở trên mới chứa response model thật.
