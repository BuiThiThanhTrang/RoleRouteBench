# Structured Data: kiểm định mức sẵn sàng release

Ngày kiểm định: 2026-11-22. Phạm vi là workspace hiện tại và các run local.
Không gọi hosted model, không sửa packet/config/adapter hoặc kết quả run gốc.

## Kết luận

Table QA 40 packet đã đủ bằng chứng để làm release candidate về task, công cụ thật,
khả năng tạo tiến triển và khả năng phân biệt routing. Chưa nên đóng băng thành
release hoàn chỉnh: còn một lỗi projection khi đọc lại inspection, định nghĩa success
cần tách rõ public workflow với gold correctness, và chưa có component/freeze cho
Table QA 40 thay thế SpreadsheetBench 20 trong release kế tiếp.

Không có bằng chứng cần giảm độ khó thêm hoặc đổi backbone để chuẩn bị release.
Các kết quả hiện có đã vượt floor effect của SpreadsheetBench.

Evidence máy đọc được nằm ở runs/structured_data_release_audit_20261122:

- run_inventory.json: 30 run có resolved_config của domain, gồm run nhỏ/chưa hoàn tất.
- packet_audit.json: manifest, source revision/hash/split, review và public files.
- run_comparisons.json: kết quả, false public pass, stopping, role usage và source drift.
- tool_state_replay.json: replay 320 episode theo tool calls đã ghi, dùng adapter hiện tại.
- inspection_revisit_probe.json: tái hiện lỗi đọc lại lát bảng.
- audit_summary.json: kết luận, phạm vi kiểm tra và fingerprints.

## Cấu hình đã chạy

### Table QA hiện hành

Nguồn: data/RoutingBench/structured_table_qa_v1_40, adapter structured_data.table_qa.v1.
40 packet gồm 22 WikiTableQuestions, 14 HiTab và 4 TableBench.
Tất cả run đầy đủ dưới đây dùng budget12 và tối đa1 tool call/lượt executor.
Qwen dùng output cap16384; TableGPT2 dùng4096. Seed42, workers1.

| Run | Router/policy | Backbone | Public workflow + STOP | Gold answer | Cả hai |
|---|---|---|---:|---:|---:|
| table_qa_jev_qwen9b_full40_b12 | JEV1.13 | Qwen3.5-9B | 21/40 | 23/40 | 19/40 |
| table_qa_sol_qwen9b_full40_b12 | gpt-6-sol-openrouter, low | Qwen3.5-9B | 24/40 | 27/40 | 22/40 |
| table_qa_drex_qwen9b_full40_b12 | DREX1.5 | Qwen3.5-9B | 28/40 | 28/40 | 27/40 |
| table_qa_pplx_qwen9b_full40_b12 | PPLX Decider Flash1.2 | Qwen3.5-9B | 18/40 | 20/40 | 17/40 |
| table_qa_single_agent_qwen9b | Một generalist có7 tool | Qwen3.5-9B | 26/40 | 25/40 | 21/40 |
| table_qa_predefined_qwen9b | Sequence specialist cố định | Qwen3.5-9B | 28/40 | 29/40 | 26/40 |
| table_qa_fixed_qwen9b_40 | Calibration policy có đọc state, bản cũ | Qwen3.5-9B | 4/40 | 19/40 | 4/40 |
| table_qa_fixed_tablegpt2_40 | Calibration policy có đọc state, bản cũ | TableGPT2-7B | 0/40 | 10/40 | 0/40 |

Cột gold được tính lại read-only bằng final_audit hiện tại. 280 episode đã có
stored audit đều giữ nguyên kết quả; predefined40 chưa có evaluation_report gốc,
nên kết quả gold29/40 ở đây là dẫn xuất mới của lần kiểm định này.
Hai run fixed cũ khác môi trường thông tin/verifier với sáu run còn lại.
Không dùng chúng như matched baseline của router hiện hành.

Ngoài ra có smoke3 cho JEV, SOL, DREX và một rerun smoke3 JEV. Các attempt nhỏ
không được cộng vào mẫu số40 hoặc lựa chọn attempt tốt nhất theo packet.

### SpreadsheetBench lịch sử

Domain ID giống nhau nhưng task/contract khác Table QA:

- Contract cũ, Qwen3.5-9B, budget8, tối đa3 tool calls/lượt: bốn router đã có
  kết quả Track B. JEV canonical20 là selection từ nhiều run trong package cũ;
  DREX/PPLX/SOL có run20 riêng. Giữ provenance của canonical selection.
- Full-source v1, JEV + Qwen9B, budget12, output16384: run20 đạt public pass2/20.
  Có thêm experiment2/5 packet và output4096.
- Transformation-body v2, JEV + Qwen9B, budget12, output16384: run20 đạt2/20.
- JEV + TableGPT2-7B: smoke1/5 packet ở v1 và run20 ở transformation-body v2;
  run20 v2 đạt0/20.

Inventory đầy đủ giữ tên run/config, coverage và audit availability. Không trộn
hai thế hệ task để so accuracy hoặc mô tả tất cả là cùng một contract.

## Protocol, harness và state đang có

### Luồng thông tin và thao tác

- MAS chỉ materialize public/task.json và public/tables.json. Gold/source record
  nằm private; public verifier không đọc gold.
- Router thấy question, schema/header hierarchy, current pointers, artifact data
  có freshness, verification_status, last_error, event history và budget.
- Executor thấy cùng state cộng preview5 hàng đầu mỗi bảng, role card và typed
  tool schema. inspect_table đọc tối đa12 hàng/lần theo offset; selection preview
  có giới hạn rõ và công bố row_count/shown_row_count/rows_truncated.
- Bảy role map tới inspect, headers, select, analyze, submit, verify và diagnose.
  Mỗi quyết định vẫn có đủ pool + STOP; guard tắt ở bốn router chính.
- Không buộc phải inspect/resolve/select theo thứ tự. Direct lookup/submit có thể
  dùng row IDs hoặc preview_cells. Numerical Analyst có thể submit ngay.
- Một attempted role, kể cả precondition rejection, tiêu hao một đơn vị budget.
  STOP không tiêu hao executor call; router vẫn được quyết định ở boundary0.
  Chọn role ở boundary0 được ghi suppressed_by_budget, không dispatch.
- Input bảng bất biến qua tool. history giữ artifact ID theo kind và dependency
  refs; current trỏ latest. Đổi dependency/candidate làm evidence liên quan stale.
- Answer schema thống nhất text/number/date/boolean; checker có unit, sequence/set,
  numeric tolerance và Unicode normalization. Đây là cohort đã chuẩn hóa riêng.

### Điểm đã đủ

- Manifest/checksum40/40 valid; source cache hashes của cả ba nguồn khớp provenance.
- Test hiện tại pass18/18: Structured Table QA, shared router protocol,
  predefined workflow và single-agent policy. Trong đó có reference paths của
  cả40 packet qua public tools và trusted evaluator, recovery/freshness,
  visibility, invalid argument feedback và direct paths.
- Bốn router chính có241 tracked file chung và không có hash khác nhau.
  Replay160/160 episode khớp mọi public state được ghi, tool status/output và
  final state với TableQAAdapter hiện tại.
- Single-agent/predefined mới replay80/80 episode khớp tương tự. Replay chỉ kiểm tra
  adapter state/tool semantics; không tái sinh model output, không chứng minh
  actor/router prompt hay toàn bộ engine byte-for-byte giống lịch sử.
- Cả7 role được dùng trong mỗi run router chính. Số sequence role được dispatch
  khác nhau là JEV27, SOL32, DREX31, PPLX24 trên40 task.
- Đã có public errors, recovery, ready states, premature STOP và calls sau ready.
  Domain tạo được những hành vi routing cần nghiên cứu.

## Những phần cần chốt trước release

### 1. Tách metric theo đúng ý nghĩa

SharedTrajectoryRunner ghi passed = terminal and stopped. Table QA terminal chỉ
là public evidence verification; verifier tự động kiểm tra giá trị có trong
evidence và nhận issue do executor nêu. Nó không tự chứng minh scope/operation
đã trả lời đúng question. Vì vậy public workflow pass không tương đương gold pass.

Các false public pass hiện có: JEV2, SOL2, DREX1, PPLX1, single-agent5,
predefined2. Ví dụ JEV STOP thành công ở WTQ nu-47 và nu-9 nhưng trusted gold fail.
Đây là bằng chứng cụ thể về khác biệt hai metric, không phải yêu cầu đưa gold
vào router hoặc làm public verifier thành oracle.

Release cần công bố riêng:

1. End-task answer accuracy: fresh final answer đạt trusted gold.
2. Workflow + STOP: metric công khai hiện có, đặt tên đúng nghĩa.
3. Verified correct completion: giao của hai tập trên.
4. Stopping metrics theo public readiness; nếu muốn đo đã giải đúng thật sự,
   bổ sung correctness readiness ở evaluator-only trên snapshots/prefixes.

Không áp dụng công thức P+E lịch sử bằng cách tin mọi public pass đều đúng.
Current generic evaluation_report chưa có tổng hợp giao workflow và gold.
Đây có thể được bổ sung như derived report, giữ nguyên raw records.

### 2. Sửa projection khi đọc lại inspection

Tái hiện trên tableqa-wtq-nu-10 bằng inspect offsets0,12,24,36 rồi0.
Lượt cuối trả inspection:1 với no_progress, nhưng current.inspection vẫn là
inspection:4 và public artifacts chỉ còn inspection:2,3,4. Dữ liệu vừa được đọc
lại không tới router và không nằm trong context lượt executor kế tiếp.

Nguyên nhân: _record deduplicate inspection nhưng không cập nhật access/current
pointer; public_observation chọn ba inspection theo thứ tự tạo, không theo lần đọc.
Evidence trong inspection_revisit_probe.json. Cần bảo đảm lần đọc thành công
đưa slice đã yêu cầu vào state/handoff, rồi kiểm tra negative/no-progress semantics.
Version hóa thay đổi visibility và giữ nguyên các run lịch sử.

### 3. Freeze đúng môi trường và baseline

Code hiện tại khác source hashes lịch sử của bốn router ở11 file; replay xác nhận
Table QA semantics của các record đã quan sát vẫn khớp. Hai fixed run cũ replay
0/40 tương đương cho mỗi run, gồm khác verification_status, row preview metadata
và verifier output. Không rebrand chúng thành run của engine mới.

Chốt engine/protocol/pool/config hiện hành và archive theo version mới.
Nếu dùng single-agent/predefined làm baseline chính, ghi rõ execution snapshot
khác nhưng adapter replay tương đương; parity smoke trên engine đóng băng sẽ bổ
sung bằng chứng cho actor/runner. Không mặc định cần trả tiền chạy lại toàn bộ.

### 4. Hoàn thiện packet/release metadata và tái dựng

Root Table QA hiện chỉ có packet_index và packs; manifest40 vẫn ghi
pending_runtime_verification, packet/human review pending. Mỗi pack mới có public
task/tables và private answer/source, chưa có execution contract/README/license
fixtures như chuẩn extension mô tả. Runtime/readiness evidence cần overlay mới,
không ghi đè bank đã được historical runs hash.

Cần component tương tự Formal40: bộ contract/state/harness docs, role/config
snapshot, exact dependency lock, source/license/citation/adaptation ledger,
preparation evidence, inventory/attempt policy và checksum/archive verify.
16 question string đã đổi so upstream, gồm typo, scope, order/unit clarification;
phải ghi nhận cohort adapted thay vì trình bày như official dataset score.
TableBench có archive hash nhưng chưa ghi dataset revision.

Artifact runtime hiện dùng ID/dependency trong state.json, chưa có per-artifact
content hash/file như chuẩn extension. Cần bổ sung provenance/input binding hoặc
ghi rõ representation và checksum của state/artifact sidecar khi đóng gói.
Không cần thay đổi thông tin router nhìn thấy chỉ để thêm metadata audit.

Packager/certifier và release registry hiện vẫn trỏ Structured Data SpreadsheetBench20.
Release kế tiếp phải dùng assembler/spec mới cho Table QA40, giữ riêng archive cũ.
Human review có thể tiếp tục pending nếu phát hành research preview có disclosure;
không đổi thành human_verified từ test runtime. Routing valid_actions hiện vẫn
pending; chưa đủ để tuyên bố action accuracy trên state mới.

## Thứ tự hoàn thiện đề nghị

1. Chốt metric và tạo derived evaluation cho cả tám run40.
2. Sửa inspection revisit dưới environment version mới; kiểm tra handoff đầy đủ.
3. Tạo component Table QA40 với contract, locks, provenance và current overlay.
4. Chạy deterministic/replay/parity smoke, verify archive và đối chiếu baseline.
5. Ghép với Formal40/Track A theo release plan; công bố review/coverage đúng trạng thái.

Các bước này nhằm làm benchmark rõ nghĩa và tái dựng được. Kết quả accuracy hiện có
và sự đa dạng workflow đã đủ cơ sở giữ nguyên40 task để chuẩn bị release candidate.
