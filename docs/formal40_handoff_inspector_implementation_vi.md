# Formal40: handoff artifact, Inspector và output có giới hạn

> **Phạm vi lịch sử:** các profile handoff/Inspector v1 bên dưới dùng input 8192
> và `artifact_first_v1` / `bounded_artifact_handoff_v1`. Không lấy chúng làm
> thông số của batch final recovery v3/input12k. Xem thiết kế hiện hành ngày
> 2026-11-20: [State và protocol](formal_proof_state_protocol_vi.md),
> [Harness và luồng thông tin](formal_proof_harness_information_flow_vi.md).

Ngày 2026-11-19. Các thay đổi được bật bằng cấu hình; bank 40 packet và dữ liệu
run cũ không bị sửa. Đây là thay đổi protocol của run, cần run ID mới.

## Cấu hình

| Profile | Cấu hình Lean 4.8 | Cấu hình Lean 4.22 |
|---|---|---|
| Handoff và output mới | formal40_handoff_lean48_jev.yaml | formal40_handoff_lean422_jev.yaml |
| Handoff, output và Inspector mới | formal40_inspector_lean48_jev.yaml | formal40_inspector_lean422_jev.yaml |

Các file ở config/shared_environment. Router là typesafe/jev-1.13, executor là
Pythagoras-LM/Pythagoras-Prover-4B:featherless-ai. Budget vẫn 12 role calls,
seed 42, một worker, pool đủ 7 role và STOP, rejection guard tắt.
Profile Inspector dùng role card phản ánh công cụ Inspector mới. Profile chỉ
handoff giữ role card cũ. Cùng profile áp dụng cùng cơ chế cho mọi router.

Giới hạn output thực tế theo role:

| Role | max_tokens mỗi response |
|---|---:|
| Tactic Synthesizer / Proof Repair Specialist | 4096 |
| Formal Failure Diagnostician | 1024 |
| Premise and Lemma Retriever | 1024 |
| Inspector / Compiler / Verifier | Công cụ deterministic; không gọi model |

Trần executor chung vẫn 16384; các role sinh nội dung dùng giới hạn thấp hơn
ở trên. Input tối đa 8192 token theo tokenizer đã pin, gồm phần dự phòng cho
chat framing. Token input và token output là hai giới hạn riêng.

## Handoff

runtime.formal_context_policy = bounded_artifact_handoff_v1.

Executor nhận source hiện tại, compiler feedback, verification, diagnosis,
premises và inspection gần nhất. Mỗi artifact có ID, hash, producer, input
versions, freshness, loại evidence, độ dài và ref đọc bản gốc. Diagnosis được
đánh dấu là nhận định agent, không phải fact đã kiểm chứng. Evidence stale
được đánh dấu thuộc input cũ. Nội dung được đưa tự động, không cần một lượt
read_artifact để thấy chẩn đoán hoặc kết quả tra lemma.

Mỗi loại evidence có quota riêng. Critical status của compiler/verifier nằm
trong các trường structured ngoài preview. Nếu toàn request vượt input budget,
preview dài được thu hẹp theo quy tắc cố định, giữ metadata và critical status.
Phần còn lại vẫn đọc được qua read_artifact. Nếu metadata và phần tối thiểu
vẫn vượt giới hạn, trả context_budget_exceeded trước khi gửi request; phân loại
là lỗi môi trường để không tính như lỗi giải proof của model.

Diagnosis có thể dùng projection loại đoạn văn trùng sau chuẩn hóa khoảng trắng.
Code fence, kể cả fence chưa đóng, được giữ nguyên. Bản gốc và hash không đổi.
Offsets của projection không phải offsets của raw artifact; read_ref luôn trỏ
đến bản gốc, các source spans mô tả phép chiếu. Nội dung evidence được render
trong các section nguyên văn, tránh JSON-escape thêm một lớp. Không dùng thêm LLM tóm tắt.

Request log lưu executor_payload và delivered_evidence sau bước giới hạn input.
Đây là bằng chứng nội dung đã được cung cấp, không khẳng định model đã sử dụng.
Handoff không truy cập reference, không tự tạo lemma/proof và không chọn role.

## Output và streaming

executor.formal_protocol.version = artifact_first_v1.

Proof role được yêu cầu trả một proof term bắt đầu bằng by hoặc một Lean code
fence chứa proof term đó, sau đó một dòng <END_ARTIFACT>. Diagnosis trả năm mục
ngắn: Observed failure, Location, Suspected cause, Repair constraints, Uncertainty.
Vẫn được gọi read_artifact khi cần thêm evidence.

Streaming kết thúc khi gặp marker trên một dòng riêng hoặc một vòng lặp rõ ràng:

- Đoạn prose dài ít nhất 80 ký tự lặp ít nhất 4 lần, tổng vùng lặp ít nhất 600 ký tự.
- Chu kỳ suffix prose dài 16–160 lexical tokens lặp 4 lần.
- 12 dòng tactic mở giống nhau, tăng indentation liên tục.

Không cấm lặp các identifier hoặc dòng tactic bình thường. Không xóa hoặc sửa
proof để vượt kiểm chứng. Nếu repetition_detected, output_truncated,
generation_incomplete, artifact_format hay stream_interrupted thì không nộp
work product hoặc ghi đè candidate trước. Khi response kết thúc đầy đủ, giữ codec
v2 sẵn có: nhận proof term/declaration hoặc block Lean hoàn chỉnh cuối cùng;
ghi selected_lean_block, không compile nhiều phương án để chọn cái pass. Response
có fence chưa đóng bị từ chối để tránh chọn skeleton đứng trước. Lượt thử provider
thực tế cho thấy model vẫn có thể trả plan/skeleton dù được yêu cầu artifact-first;
giữ codec này tránh tạo thêm rào cản định dạng. Lỗi được đưa vào observation kế tiếp;
router tự quyết định bước phục hồi.

Raw response đã nhận, nguyên nhân dừng và trạng thái provider được lưu.
Stream bị gián đoạn sau khi có nội dung không tự gọi model lại; ghi là lỗi
dịch vụ. Retry transport trước khi nhận nội dung dùng policy hiện tại.
Không tạo thêm semantic retry hoặc điều phối ngầm.

Khi đóng stream sớm, usage tổng từ provider có thể chưa có. Khi đó usage=null,
usage_available=false; observed_completion_tokens chỉ đếm nội dung nhận được
bằng tokenizer, không đại diện chính xác cho token tính phí. Evaluator giữ
reported token usage tách biệt và đánh dấu coverage thiếu.

## Inspector

runtime.formal_inspection_policy = tactic_state_v1.

Collector Lean ở routing_benchmark/v4/execution/lean/InspectProof.lean dùng
frontend và InfoTree của đúng runtime, elaborate file public/Main.lean hiện tại.
Nó không chèn tactic, thử lời giải, gọi oracle hoặc sửa source.

Artifact inspection gồm diagnostics, source hash, placeholder locations,
goal/local context trước và sau tactic, expected/actual type khi có, vị trí
1-based và trạng thái complete/partial/unavailable. Ưu tiên các span hẹp quanh
lỗi đầu tiên; full trace công khai nằm ở inspection_trace và đọc được bằng tool.
Collector giới hạn 512 tactic states, 1024 term entries; cờ capped được công bố.
Kết quả cache theo source, driver và runtime profile. Chỉ chạy khi role Inspector
được chọn. Source thay đổi làm inspection cũ stale.

Inspection không ghi compilation/verification evidence. Zero goals và không có
elaboration error chưa chứng minh proof đúng: sorry và dependency bị cấm vẫn
phải được Compiler/Verifier kiểm tra. Public router observation nhận structured
inspection, không được bổ sung toàn bộ raw proof source.

## Chuẩn bị và chạy

Chạy từ root repo. Dependencies Formal ở requirements-formal-environment.txt.
Requirements chung không ép phiên bản tokenizers cho các domain khác. Nếu đang
dùng roleroutebench_env với transformers 4.43.4, giữ tokenizers 0.19.1 trong env đó;
chạy Formal bằng Python riêng đã kiểm định hoặc một environment Formal riêng.
Không cài requirements Formal vào env có Transformers yêu cầu tokenizers<0.20.
Tokenizer chỉ tải vào cache repo, có SHA-256 bắt buộc; không tải model weights.
Môi trường đã kiểm định dùng tokenizers==0.22.2. Script prepare kiểm tra cả việc
decode tokenizer, không chỉ checksum, và in sys.executable cùng phiên bản thư viện.
Nếu thấy lỗi ModelWrapper, dùng đúng Python đã chuẩn bị hoặc cài dependency trong
chính environment chạy audit. Không đổi tokenizer hoặc chuyển sang đếm ký tự.

```powershell
python scripts/prepare_formal_executor_resources.py
python scripts/run_formal_runtime_audit.py --config config/shared_environment/formal40_inspector_lean48_jev.yaml --check-only
python scripts/run_formal_runtime_audit.py --config config/shared_environment/formal40_inspector_lean422_jev.yaml --check-only
```

Chạy hai audit đầy đủ sau khi có OPENROUTER_API_KEY và HF_TOKEN:

```powershell
python scripts/run_formal_runtime_audit.py --config config/shared_environment/formal40_inspector_lean48_jev.yaml --run-id formal40_jev_handoff_inspector_lean48_b12
python scripts/run_formal_runtime_audit.py --config config/shared_environment/formal40_inspector_lean422_jev.yaml --run-id formal40_jev_handoff_inspector_lean422_b12
python scripts/evaluate_shared_environment.py runs/formal40_jev_handoff_inspector_lean48_b12
python scripts/evaluate_shared_environment.py runs/formal40_jev_handoff_inspector_lean422_b12
```

Để ablate riêng handoff/output, thay config inspector bằng config handoff và dùng
run ID riêng. Chọn packet theo toolchain trong contract; tên nguồn không tham gia.
Hai audit là các nhóm đề khác nhau, không phải A/B cùng đề giữa các runtime.

## Kiểm định

test_formal_handoff.py kiểm tra handoff không cần read, hash/raw preservation,
freshness, token caps, streaming cancellation, không nộp output lỗi, marker trong
string Lean, feedback đến router và đầy đủ action space. Bật FORMAL_REAL_LEAN=1
để chạy integration test goal/local context/type trên hai Lean runtime.

check_formal_executor_protocol.py kiểm tra 40 packet/280 role contexts; có các
cờ --real-lean, --inspect-all và --replay-run. Các smoke dùng witness test double
để kiểm tra môi trường; chúng không phải performance của model hoặc router.
Replay output cũ cũng không đo hành vi model với prompt mới.

Report tổng hợp ở runs/formal_handoff_implementation_20261119/implementation_report.json.
Native sweep/smoke ở runs/formal_handoff_verified_preflight_20261119; context và
replay theo source cuối ở runs/formal_handoff_context_final_20261119.
Code Debugging regression cần quyền clone repository local;
test bị hạn chế ở lần đầu đã được chạy lại với quyền clone local.

Đã kiểm tra streaming provider bằng một request tối đa 32 token và một lượt
executor tối đa 4096 token trên public packet 09. Lượt executor dùng 769 completion
tokens, vẫn trả plan/skeleton cùng proof; decoder quá chặt ở bản đầu từ chối nó.
Sau khi giữ codec v2, replay nguyên response đó qua decoder cuối đã qua compiler,
kernel, dependency gate và evaluator độc lập, không gọi model thêm. Đây là test
executor/codec, không phải trajectory JEV hoặc kết quả audit đầy đủ.

Kết quả nghiệm thu: 40/40 initial packet inspect được (30 complete, 10 partial
do proof lỗi APRIL), 280/280 role contexts qua gate; hai witness-backed smoke
qua evaluator độc lập. Bộ test mới và regression gồm 55 test đã pass, gồm native
integration trên hai Lean runtime. Offline replay phát hiện vòng lặp trước cap
mới ở 12/15 response cũ; 23656 token prefix được đọc so với 245760 token gốc.
Con số replay này không phải token tiết kiệm đã đo trên một run model mới.

Các run cũ giữ nguyên dữ liệu. Source freeze có thể từ chối resume sau thay đổi
code; dùng run ID mới cho protocol mới. Kết quả cũ và mới cần ghi rõ profile,
không gộp như cùng một điều kiện benchmark.
