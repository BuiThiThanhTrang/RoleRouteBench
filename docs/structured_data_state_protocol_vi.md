# Structured40: state, artifact và executor protocol

Đối chiếu code ngày2026-11-22. Đọc cùng structured_data_harness_information_flow_vi.md
và structured40_release_preparation_vi.md. Các thông số của run lịch sử lấy từ
resolved_config/source_hashes, không suy từ source working tree hiện tại.

## 1. Phạm vi và cấu hình

Bank data/RoutingBench/structured_table_qa_v1_40 có40 packet:22 WTQ,14 HiTab,
4 TableBench. Adapter structured_data.table_qa.v1; generator structured-table-qa-pilot.v1.
Đây là cohort Table QA mới, khác SpreadsheetBench20 với Python workbook transformations.

| Thành phần | Profile Table QA hiện hành |
|---|---|
| Backbone | qwen/qwen3.5-9b qua OpenRouter |
| Budget / seed / workers | 12 attempted role calls /42 /1 |
| Output cap | 16384 token/response |
| Sampling yêu cầu | temperature0; không gửi top_p override |
| Tool call/lượt | Tối đa1 |
| Role cards specialist | config/shared_environment/table_qa_roles.json |
| Action space dynamic | Đủ7 role + STOP; observable rejection guard false |
| Generalist | Table QA Agent, được sử dụng đủ7 tool |
| Minimal fix | Cached inspection chỉ được khôi phục current khi đang bị khuất |

Không có input tokenizer cap12288 hoặc artifact-first Lean protocol của Formal40
trong profile này. API context limit của provider không phải benchmark input cap
đã đo. temperature0 không bảo đảm kết quả provider tái lập tuyệt đối.

## 2. State authoritative

Materialize tạo workspace mới, kiểm tra hash và chỉ copy public/task.json,
public/tables.json. state.json ban đầu chứa current={}, history={}, last_error=null.
Private answer/source không copy vào workspace và không đi vào prompt.

| Trường | Ý nghĩa |
|---|---|
| current | Kind → artifact ID đang được sử dụng |
| history | Artifact ID → kind, data, depends_on; giữ bản cũ |
| last_error | Public tool/contract failure gần nhất theo quy tắc adapter |
| public state_version | Adapter ID, không phải hash toàn bộ engine |
| tables | Table IDs, titles, row counts, columns/header paths; không tự nhúng mọi row |
| artifacts | Projection của current, inspections và dependency chain của answer |
| verification_status | answer_id, artifact_id và not_checked/passed/failed |
| terminal | Public verification fresh/pass |

Kind chính là inspection, headers, selection, calculation, answer, verification,
diagnosis. ID dùng kind cùng chỉ số history toàn cục. Artifact nằm trong history
của state.json; không có một file/hash độc lập cho mỗi version như formal adapter.
Episode archive và file manifest cấp component giữ checksum để audit representation này.

## 3. Freshness và projection

Inspection vẫn fresh khi bảng input bất biến. Các kind khác phải còn là current
của kind đó và mọi depends_on còn fresh. Candidate mới hoặc selection dependency
thay đổi có thể làm calculation/answer/verification cũ không còn fresh.
Diagnosis không chứng minh answer đúng.

Public view gồm current pointers, ba inspection tạo gần nhất và transitive
dependencies của current answer. Inspection hiển thị tối đa12 rows, selection6;
row_count/shown_row_count/rows_truncated thông báo việc rút gọn.

Sau minimal fix: nếu inspect_table trả cached artifact đang ngoài view, current.inspection
trỏ về artifact đó; history/nội dung không đổi và tool báo success vì thông tin
được khôi phục cho lượt sau. View có thể thêm slice được yêu cầu ngoài ba inspection
tạo gần nhất. Đọc lặp slice đã hiện diện giữ nguyên state và no_progress.
Không đổi lịch sử truy cập hoặc pointer của mọi cached read.

Không có generic artifact reader nhận đường dẫn. Có thể đọc tiếp public table
bằng offset/columns của inspect_table; calculation/select làm việc trên bảng gốc,
không tính trên preview bị rút gọn. Preview không phải toàn bộ table.

## 4. Role và tool

| Role | Tool |
|---|---|
| Table Inspector | inspect_table: đọc tối đa12 rows theo offset0-based |
| Header Resolver | resolve_headers: ghi public row/column hierarchy IDs |
| Evidence Selector | select_evidence: row IDs hoặc AND filters, projection columns |
| Numerical Analyst | analyze_table: lookup/count/distinct_count/mode/sum/mean/min/max/argmin/argmax/difference/ratio |
| Answer Composer | submit_answer: typed list và fresh evidence IDs hoặc preview_cells |
| Evidence Verifier | verify_answer: kiểm public evidence và issue do executor chỉ ra |
| Failure Diagnoser | diagnose_failure: problem và bước headers/selection/calculation/answer |

Các role đều dùng backbone để chọn typed arguments; phép đọc/tính/kiểm tra sau đó
do tool Python thực hiện. Verifier không đọc gold. Numerical Analyst có thể submit
ngay khi kết quả đã trả lời question. Không bắt buộc inspector/header/selection
trước direct lookup hoặc answer từ preview.

Verifier cần current answer fresh. Diagnoser cần public last_error. Các precondition
được kiểm tra sau role selection; không dùng để mask action space dynamic.
Generalist nhận union7 tools và tự chọn thao tác mỗi lượt.

## 5. Output và feedback

Executor trả một JSON object có tool và arguments. Chấp nhận JSON trực tiếp hoặc
JSON code fence theo shared actor; không có cơ chế sửa nội dung toán học hoặc
tự chọn tool thay model. Tool schema nằm trong payload và sidecar records/task_contract.json.
Sidecar phục vụ release documentation; không được tự chèn vào historical prompts.

Answer là typed list text/number/date/boolean. Number có thể mang unit; date dùng
ISO year/month/day phù hợp schema. Private gold xác định sequence/set, aliases và
tolerance; chấm cùng canonicalization cho mọi nguồn. Các clarification về unit/order
đã đưa vào question có provenance riêng.

Argument schema sai hoặc tool không hợp lệ trả contract_error công khai. Tool lỗi
ghi last_error; candidate/history trước đó được giữ theo adapter semantics.
status success có nghĩa tool tạo hoặc khôi phục state; no_progress là không có
thay đổi theo operation đó, chưa phải nhãn human về action hợp lý.

## 6. Public verification và trusted correctness

Public verifier kiểm giá trị có được hỗ trợ bởi evidence/preview, và ghi nhận
issue về scope/operation/order/unit do executor cung cấp. Nó không chứng minh
candidate đã trả lời đúng question. Public pass có thể vẫn sai trusted gold.

Independent final_audit kiểm checksum private answer, freshness của current answer
và typed scoring. Gold chỉ dùng evaluator-only, không phản hồi vào trajectory.
Passed=public terminal AND STOP; End-task pass=final fresh answer đạt gold.
Hai metric không được cộng và không thay thế nhau. JSON báo thêm giao của hai tập.

## 7. Danh tính và review

Source hashes/config freeze định danh engine của run; adapter_id không đủ để kết
luận mọi batch cùng phiên bản code. Bank gốc giữ byte/hash và metadata review pending.
Readiness overlay mới ghi bằng chứng runtime, không tự đổi human review thành verified.
State/action labels mới vẫn pending; không chuyển nhãn Track A cũ bằng packet ID.
