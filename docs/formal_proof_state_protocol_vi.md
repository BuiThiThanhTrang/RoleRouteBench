# Formal40 hiện hành: state, artifact và executor protocol

Đối chiếu code và cấu hình ngày **2026-11-22**. Tài liệu này mô tả implementation
hiện tại của Formal40, không thay thế cấu hình đã lưu của các run lịch sử.
Phần harness, visibility và luồng thông tin nằm trong
[Formal40: harness và luồng thông tin](formal_proof_harness_information_flow_vi.md).
Trạng thái đóng gói: [Chuẩn bị release kết hợp](formal40_release_preparation_vi.md).

## 1. Phạm vi và phiên bản

Bank hiện dùng: `data/RoutingBench/formal40_pythagoras_v1_20261118`, gồm 8 MiniF2F,
20 LeanDojo, 10 APRIL và 2 Putnam. Adapter là `formal_proof.lean4.v2`.
Không dùng mô tả bank 30 packet/Goedel/budget 8 của năm 2026-11-01 làm cấu hình
cho Formal40.

| Thành phần | Giá trị của profile final hiện tại |
|---|---|
| Cấu hình | `config/shared_environment/formal40_final_v3_input12k_b12/{lean48,lean422}_{jev,sol,drex,pplx}.yaml` |
| Executor | `Pythagoras-LM/Pythagoras-Prover-4B:featherless-ai`, provider `huggingface` |
| Role cards | `config/shared_environment/formal40_inspector_roles.json` |
| Executor protocol | `artifact_first_v2` |
| Parser | `presentation_v1` |
| Handoff | `bounded_artifact_handoff_v2` |
| Candidate identity | `lean_tokens_layout_v1` |
| Inspector | `tactic_state_v1` |
| Budget / workers / seed | 12 role calls / 1 / 42 |
| Rejection guard | `false`; full 7 role + STOP |

Đây là tên các lớp khác nhau: **adapter v2**, **executor protocol v2**, và
**profile recovery v3** không phải ba cách gọi cùng một phiên bản. Profile v3
bổ sung parser và identity trên protocol/handoff v2; profile input12k bổ sung
giới hạn tài nguyên. Các profile cũ vẫn có thể chạy với cấu hình riêng.

## 2. State authoritative và public observation

`FormalProofAdapter.materialize()` chỉ copy các file được khai báo public và
kiểm tra hash. Workspace có `public/Main.lean`, execution contract, initial
proof state và `_runtime/state.json`. Private reference/witness và fixtures
không tự materialize vào workspace hoặc đi vào prompt.

`_runtime/state.json` lưu các map/list `artifacts`, `artifact_history`, `events`,
`snapshots`; `latest_execution` và `role_results` được thêm khi phát sinh.
`public/Main.lean` là source hiện tại. Artifact candidate là bản nộp đã được
chấp nhận về edit scope; điều đó **chưa chứng minh Lean đúng**.

`FormalProofV2Adapter.public_observation()` công bố:

| Trường | Ý nghĩa |
|---|---|
| `source_hash`, `candidate_hash` | SHA-256 của source thực và candidate đã đăng ký; candidate có thể chưa tồn tại |
| `artifacts` | Metadata, freshness và nội dung được phép công bố của artifact hiện tại theo từng key |
| `public_execution_contract` | Toolchain, edit scope, target, allowed axioms, forbidden dependencies và các quy tắc của packet |
| `initial_proof_state` | Goal/local context do Lean ghi lúc chuẩn bị packet; không phải state cập nhật tại từng tactic |
| `edit_contract` | Context/statement bất biến, dạng output được nhận, allowed axioms |
| `latest_execution` | Compiler result gần nhất và input versions tương ứng; có thể thuộc source cũ |
| `latest_tool_feedback` | Tool/status/error gần nhất trong adapter events; không thay thế artifact lỗi đầy đủ |
| `terminal` | Có verification fresh với nội dung `passed=true` |
| `source_identity` | Fingerprint trình bày và trạng thái lexer |
| `latest_generation_failure` | Lỗi generation gần nhất đã được ghi vào adapter, input versions và freshness; có thể là lỗi lịch sử |
| `role_progress` | Kết quả role gần nhất và các bộ đếm theo role, trong phạm vi các lượt actor ghi nhận |

Router nhận state này qua `observation.current_state`. Router không được tự
nhúng toàn bộ `Main.lean` hay raw candidate output. Artifact `candidate` và
`rejected_candidate` chỉ có metadata trong observation; inspection hiện hành
công bố report có goal/type/diagnostics. Các đoạn goal/error có thể chứa biểu
thức Lean công khai, khác với quyền đọc toàn bộ source.

## 3. Artifact, version và freshness

Các key chính: `candidate`, `compilation`, `verification`, `diagnosis`, `premises`,
`inspection`, `inspection_trace`, `rejected_candidate`. Không bắt buộc mọi
episode phải có đủ các key này.

Mỗi lần lưu tạo file mới `_runtime/artifacts/NNNN_<key>.txt`, cùng `artifact_id`,
`version`, `sha256`, `path`, `input_versions`, `input_refs`, `producer_tool`,
`producer_event`, `visibility`. Map `artifacts` trỏ bản mới nhất của từng key;
`artifact_history` giữ metadata các bản trước. `fresh` được tính khi quan sát:
các input versions phải khớp hiện tại và các input refs phải còn đúng hash.

Candidate của adapter v2 không phụ thuộc diagnosis/rejected artifact. Vì vậy,
ghi diagnosis hay từ chối một candidate mới không tự làm mất candidate đã nhận.
Compilation/verification vẫn gắn với exact source/candidate hash. Source đổi
comment hoặc whitespace vẫn phải có evidence compile/verify fresh.

`initial_candidate=true` của APRIL đăng ký source lỗi ban đầu thành candidate
khi materialize, với event `origin=environment` và giữ byte/hash gốc. Các task
proof-hole khác không tự có candidate. Router không cần biết dataset nguồn để
thấy sự khác nhau này; nó đọc state và contract.

## 4. Role và tool contract

| Role | Thực thi | Có gọi backbone? |
|---|---|---|
| Proof State Inspector | `inspect_proof` | Không |
| Premise and Lemma Retriever | `write_premises`, có thể `read_artifact` trước | Có |
| Tactic Synthesizer | `write_source`, có thể `read_artifact` trước | Có |
| Proof Repair Specialist | `write_source`, có thể `read_artifact` trước | Có |
| Lean Compiler Executor | `compile_proof` | Không |
| Kernel and Assumption Verifier | `verify_proof` | Không |
| Formal Failure Diagnostician | `write_diagnosis`, có thể `read_artifact` trước | Có |

Compiler cần candidate tồn tại. Verifier cần lần compilation thành công khớp
đúng versions hiện tại. Các precondition được kiểm tra **sau** lựa chọn router,
không dùng để loại action khỏi pool. Inspector được phép quan sát source ban đầu.

Retriever gửi JSON tool call với **1–8 symbol names**; harness dùng imports/context
gốc để chạy `#check` trên runtime đã pin. Đây là kiểm tra các tên model đề xuất,
không phải công cụ tự tìm kiếm toàn bộ Mathlib hay tự suy ra lemma thay thế.
Lookup loại tên target bị cấm trong contract. Symbol được tìm thấy chưa có
nghĩa áp dụng được vào goal hoặc proof đã đúng; phải đọc `lookup.returncode`.

### Proof output

Parser hiện nhận proof term, theorem/lemma declaration hoặc full source ở dạng
plain Lean hay Lean code fence đã đóng. Actor yêu cầu một artifact hoàn chỉnh,
không plan/skeleton, rồi `<END_ARTIFACT>` trên một dòng riêng. Marker giúp dừng
stream sớm; response kết thúc bình thường bằng provider `stop` cũng có thể được
nhận nếu format hợp lệ, không bắt buộc marker để proof đúng.

Nếu có nhiều Lean block hoàn chỉnh, codec hiện chọn block cuối và ghi metadata;
không compile từng phương án để chọn block pass. Fence chưa đóng, output bị cắt
hoặc bị phát hiện lặp không được cứu thành proof hợp lệ.

Adapter luôn ghép proof vào context gốc. Repeated declaration được chuẩn hóa tên
về tên packet nhưng phải giữ các token statement khác; full source phải giữ
token context. Không được thêm imports, sửa giả thiết/kết luận hay thêm top-level
commands. V2 còn chặn host IO/runtime metaprogramming theo policy. Candidate sai
edit scope bị từ chối; output được nhận vẫn cần compiler và verifier.

### Diagnosis output

Năm nhãn: `Observed error`, `Location`, `Likely cause`, `Repair constraint`,
`Uncertainty`, mỗi trường tối đa 450 ký tự. `presentation_v1` nhận bullet/số thứ
tự, Markdown bold và nhãn không phân biệt hoa thường; không tự điền trường thiếu
hoặc chọn giữa các trường có nội dung xung đột. Diagnosis mang nhãn
`unverified_assessment=true`, không phải kết luận của checker.

Khi output bị truncation/repetition, chỉ được giữ partial diagnosis nếu đã có
các dòng hoàn chỉnh của ít nhất `Observed error` và `Location`; artifact giữ
`status=partial` và `generation_failure`. Không cứu partial khi lỗi mạng, không
áp dụng cơ chế này để cứu proof bị cắt.

## 5. Token, sampling và lỗi generation

| Giới hạn của profile final | Giá trị |
|---|---:|
| Input executor | 12.288 token, đo bằng tokenizer đã pin |
| Trần output chung | 16.384 token/response |
| Output Synthesizer/Repair thực tế | 4.096 token/response |
| Output Diagnostician/Retriever thực tế | 1.024 token/response |
| Tool steps trong một lượt role sinh nội dung | Tối đa 3, gồm bounded reads và work product |

Một lượt role có thể có nhiều model requests nếu đọc artifact trước khi nộp sản
phẩm; cap output là **mỗi response**, không phải tổng token của cả episode.
Compiler/Verifier/Inspector không sinh token backbone nhưng vẫn tốn role call.

Sampling chung `temperature=0.6`, `top_p=0.95`. Chỉ Diagnostician/Retriever gửi
`chat_template_kwargs.enable_thinking=false`; Synthesizer/Repair giữ mặc định
provider. Metadata `thinking_requested` chỉ xác nhận tham số đã yêu cầu, không
đo suy nghĩ nội bộ của provider. Không tự đổi mode nếu provider từ chối tham số.

Streaming phát hiện các paragraph prose dài lặp, chu kỳ suffix prose và chuỗi
12 tactic mở giống nhau với indentation tăng liên tiếp. Nó dừng sinh và ghi
`repetition_detected`, không sửa Lean. `output_truncated`, `artifact_format`,
`diagnosis_format`, `generation_incomplete` cũng là các kết quả khác nhau, không
nên gom thành một lỗi toán học. Raw response nhận được giữ trong trajectory.

Tokenizer có SHA-256 pin trong cấu hình; bản thư viện đã kiểm định là
`tokenizers==0.22.2`. Không thay tokenizer bằng cách đếm ký tự. Dùng environment
Formal phù hợp; tránh nâng tại chỗ environment Transformers cũ yêu cầu
`tokenizers<0.20`. Token usage provider thiếu khi stream đóng sớm phải được giữ
là thiếu; `observed_completion_tokens` không phải số token tính phí đã xác nhận.

## 6. Candidate trùng và tiến triển

`lean_tokens_layout_v1` bỏ comments, blank lines và spacing trong dòng, giữ
literals, ranh giới dòng có token và indentation. Input lexer không xử lý an
toàn được dùng exact-source fallback. Đây là nhận diện trình bày bảo thủ,
không chứng minh hai proof tương đương về ngữ nghĩa.

`role_progress.last_result` có status, artifact được tạo, hashes trước/sau,
`source_changed` theo raw hash, `candidate_changed` theo fingerprint,
`duplicate_candidate`, `generation_failure`, `partial_diagnosis`. `by_role`
đếm calls đã ghi nhận, lỗi generation liên tiếp và candidate trùng theo role.
Các bộ đếm này có ở cả public observation và executor context.

`semantic_delta` dùng projection tiến triển: fingerprint source/candidate,
terminal và hashes của evidence; không coi ID/counter mới hoặc freshness đổi
đơn thuần do trình bày là tiến triển. Đây không phải nhãn human về action đúng.
Nội dung evidence đổi vẫn có thể tạo delta mà chưa tiến gần lời giải.
Không tự bỏ lượt, đổi role, giữ cache kiểm chứng theo fingerprint hay STOP.

**Giới hạn ghi nhận:** precondition rejection và các exception thoát actor rồi
bị runner bắt không đi qua `record_role_result`. Vì vậy, `role_progress.calls`
không phải tổng accounting của runner; bộ đếm generation failure không đếm đủ
mọi lỗi API. Xem `decisions.jsonl` và `trajectory.jsonl` để audit đầy đủ.

## 7. Nguồn code và tài liệu liên quan

- [State, tool và immutable edit scope](../routing_benchmark/v4/execution/adapters/formal_proof.py).
- [Adapter v2, role progress và dependency gate](../routing_benchmark/v4/execution/adapters/formal_proof_v2.py).
- [Executor protocol, parser và streaming](../routing_benchmark/v4/execution/formal_actor.py).
- [Candidate presentation identity](../routing_benchmark/v4/execution/formal_identity.py).
- [Chuẩn bị packet và provenance](formal40_packet_preparation_vi.md).
- [Lịch sử recovery v3 và profile input12k](formal40_recovery_v3_vi.md).

Thông số của một run cụ thể phải lấy từ `resolved_config.json`, `role_cards.json`,
`runtime.json` từng episode và source hashes tương ứng, không suy từ tên run.
