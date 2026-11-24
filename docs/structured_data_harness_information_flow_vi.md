# Structured40: harness, runtime và luồng thông tin

Đối chiếu implementation2026-11-22. Phạm vi là Table QA40/Qwen3.5-9B/budget12.
Đọc cùng structured_data_state_protocol_vi.md và structured40_release_preparation_vi.md.

## 1. Runtime

Adapter đọc normalized JSON và thực hiện phép tính bằng Python/Decimal. Table QA
không cần Excel, LibreOffice, Lean, repository checkout hoặc model weights local.
Các model calls vẫn cần provider credentials và kết nối mạng; public table tools
không tự truy vấn web hoặc upstream dataset.

Môi trường chuẩn bị đã kiểm định Windows/Python3.13.9. Component ghi snapshot
requirements-structured40.lock.txt với dependency versions đã cài và markers của
platform này; không phải cam kết tái dựng binary trên mọi OS.
Original source archives được pin bằng hash trong provenance nhưng không bundle
vào component; bank đã normalize đủ dữ liệu để chạy và đánh giá40 packet.

## 2. Vòng lặp và accounting

1. Materialize public inputs và initial state.
2. Ghi decision snapshot: task, current_state, agent_profiles, recent_events,
   budget.calls_remaining và constraints.allowed_actions.
3. Router chọn một role hoặc STOP.
4. STOP được xử lý trước budget boundary. Non-STOP khi còn budget tiêu hao1 call,
   rồi mới kiểm precondition và dispatch actor.
5. Tool ghi artifact/feedback; harness lấy public observation mới và lặp lại.

Rejected role, generation/contract failure và dispatched role đều tiêu hao call.
Transport retries trong cùng actor request không tạo quyết định routing mới.
Tại budget0, STOP vẫn được chọn miễn phí; non-STOP là suppressed_by_budget và không
dispatch. No auto-STOP cho dynamic khi terminal pass; policy baseline có STOP rule
công khai. PREMATURE_STOP chỉ nghĩa terminal chưa pass, có thể xảy ra sau khi đã
dùng hết budget; không tự suy ra còn calls từ tên nhãn.

## 3. Ai thấy gì?

| Thông tin | Router | Executor đang chọn | Checker/preparation |
|---|---|---|---|
| Question, table IDs, columns/header hierarchy | Có | Có | Có |
| Toàn bộ table rows ngay ban đầu | Không | Preview5 rows/bảng | Có |
| Artifact projection và freshness | Có | Có | Có |
| Remaining budget và toàn bộ role pool | Có | Payload chỉ thêm role đang chọn; không tự thêm remaining budget | Dùng accounting |
| Tool schemas | Role cards mô tả chức năng, không tự nhận union schema | Schema tool của role; generalist có7 | Có |
| Raw chat/tool result của lượt trước | Không tự truyền nguyên văn | Không có shared chat memory | Lưu trajectory để audit |
| Public errors và recent role/status/delta | Có | current last_error trong context | Có |
| Private answer/source/upstream answer formulas | Không | Không | Evaluator/preparation |

Tool output và raw requests/responses được lưu trong trajectory. Runner bỏ result
raw khi tạo recent_events, giữ contract_error công khai nếu có. Artifact/state là
kênh handoff giữa các role. Có evidence trong prompt không chứng minh model đã dùng nó.

## 4. Actor và output

SharedRoleActor dùng selected role + public_context + allowed_tools. Với cấu hình
Table QA hiện tại, mỗi dispatched role có tối đa1 typed tool call, thường1 model
response thành công; transport retries có thể tăng số HTTP attempts. Không đồng
nhất role calls, tool calls, HTTP requests và token usage.

Executor yêu cầu temperature0 và output cap16384; không có benchmark tokenizer
input truncation hoặc formal parser/streaming protocol trong profile này.
Schema validation, authorized tool allowlist và adapter feedback áp dụng như nhau
giữa bốn dynamic router. SOL dùng run_shared_environment_sol.py để thêm LLM router;
ba router quyết định dùng run_shared_environment.py.

## 5. Baseline

Single-agent dùng Table QA Agent, union7 tools và cùng per-turn call limit.
Policy chỉ dispatch generalist tới khi public terminal rồi STOP; model phải tự
lập kế hoạch thao tác. Context được dựng lại mỗi lượt như specialist, không tự
giữ chat memory dài.

Predefined dùng sequence11 specialist actions trong YAML:
Inspector → Header → Selector → Analyst → Verifier → Diagnoser → Composer →
Verifier → Selector → Analyst → Verifier. Sequence không đổi nhánh theo state;
rejection vẫn tiêu hao call và vẫn tiến bước. Ngoại lệ là terminal short circuit.
Hết sequence thì STOP, kể cả chưa terminal. Không gọi model router riêng.

Hai TableQAFixedPolicy calibration cũ có đọc state/nhánh recovery và snapshot
verifier khác. Không gọi chúng là literal predefined baseline hiện hành.

## 6. Evaluator và metric

Independent audit đọc final state và trusted answer; không dựa vào public verifier
do backbone điều khiển. Mỗi kết quả giữ Passed, EndTaskPass và giao của hai tập.
STOP F1/Recovery@PublicFailure được tính offline từ decision snapshots và errors.
Metric formulas và denominators nằm trong report/structured40_final_results.json.

Gold scoring ở các prefix chỉ dùng khi phân tích STOP/recovery offline, không đi
vào router prompt. Đây không phải human valid-action labels cho tất cả role.
Detector không thấy infrastructure là bằng chứng trong phạm vi log hiện có,
không chứng minh mọi timeout hoặc provider behavior đã được instrument đầy đủ.

## 7. Replay và patch inspection

Minimal patch chỉ khôi phục cached inspection bị khuất. Hai regression test tái
hiện lỗi trên code cũ và pass sau sửa; stress/handoff task qua các role đạt gold.
Replay240 episode/sáu phương pháp khớp2084 public states, preconditions,1616
complete ToolResults và final states. Source bank201 file được giữ byte.

Replay phát lại recorded actions/tools, không tái sinh model decisions và không
chứng minh provider deterministic. Bốn router chia sẻ241 tracked file cùng hash
khi chạy; single/predefined/current source có delta. Component giữ fingerprints
lịch sử và snapshot mới riêng, không reversion historical runs.

## 8. Tái dựng và dữ liệu audit

Run giữ resolved_config, role_cards, source_hashes, freeze_verification; mỗi episode
có result, decisions, decision_states, trajectory và workspace/state.json.
Local experiment archive giữ các file allowlist cần tái dựng cùng public inputs.
File manifest cấp component gắn checksum; runtime artifacts vẫn là embedded history.

Archive local chứa raw model logs/đường dẫn host và bank có private evaluator data.
Assembler cuối phải áp dụng publication visibility thay vì upload component nguyên
khối. Nguồn gold có trong archive tái dựng không có nghĩa runtime agent được đọc nó.
