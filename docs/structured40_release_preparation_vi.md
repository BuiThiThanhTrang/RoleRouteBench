# Chuẩn bị thành phần Structured Data cho release kết hợp

Cập nhật 2026-11-23. Chuẩn bị local component Structured40 để ghép Formal Proof và
Track A V2 theo release plan chung. Chưa upload/thay dataset trên Hugging Face;
component version không quyết định global dataset version. Track A V2 đã
rebuild/validate 997 state từ bốn domain hiện hành nhưng chưa gán nhãn; không
chuyển nhãn Track A V1 sang V2 hoặc mô tả V2 là human-verified.

## 1. Tài liệu authoritative

- structured_data_state_protocol_vi.md: state, artifact, freshness, typed contract.
- structured_data_harness_information_flow_vi.md: runtime, visibility, budget, baseline.
- structured40_router_baseline_release_observations_vi.md: kết quả/claim/giới hạn.
- structured40_hf_release_notes.md: nội dung tiếng Anh cho dataset card/changelog.
- report/structured40_final_results.md, JSON, CSV: bảng hiện hành trên đủ40 task.

Các audit/readiness documents trước sửa là evidence lịch sử, không dùng các dòng
inspection pending hoặc18 tests để mô tả trạng thái sau patch. Mốc hiện hành có20
test và replay240 episode. Bank gốc vẫn ghi pending_runtime_verification; overlay
trong component ghi runtime evidence mà không đổi manifest/hash lịch sử.

## 2. Phạm vi cập nhật

Domain ID structured_data_processing, task family mới Table QA, adapter
structured_data.table_qa.v1. Bank40 gồm22 WikiTableQuestions,14 HiTab,4 TableBench.
Mục tiêu là cân bằng độ khó với executor nhỏ và tăng đa dạng workflow; không chỉ
thêm sample vào SpreadsheetBench20. Giữ reference của thế hệ cũ riêng.

Không tuyên bố mọi packet đã human-reviewed, mọi task đều vừa sức mọi SLM, hoặc
dynamic routing phải thắng baseline. Các revision sau có thể tăng sample và nguồn
khi đủ calibration, contract, provenance và license evidence. Chưa chốt quota/date.
Mỗi revision phải giữ selection/cohort denominator và historical results rõ ràng.

## 3. Local component

Builder: scripts/prepare_structured40_release_component.py.
Output mặc định: hf_release_staging/structured40_20261122/ và ZIP cùng tên.

| Đường dẫn trong component | Nội dung |
|---|---|
| payload/data/RoutingBench/structured_table_qa_v1_40 | Bank gốc copy byte-for-byte,40 manifest |
| payload/config/shared_environment | Sáu current configs, role cards và config fixtures cho shared policy tests |
| payload/docs và report | Tài liệu và bảng results có JSON/CSV |
| payload/routing_benchmark và scripts | Source dependency closure, live entry points, builder |
| payload/tests |20 test kiểm protocol/recovery/handoff/reference paths |
| payload/requirements-structured40.lock.txt | Version snapshot gồm runtime imports và transitive requirements |
| records/tasks.jsonl, agents.jsonl |40 tasks,7 specialist roles và1 generalist |
| records/selected_episodes.jsonl, runs.jsonl |240 selected episodes và config/fingerprints lịch sử |
| records/provenance.jsonl | Source hash/revision/split/license và original/adapted questions |
| records/readiness_overlay.jsonl | Runtime evidence overlay, giữ review pending |
| records/task_contract.json | Tool schemas và typed answer contract sidecar |
| records/licenses | License text lấy byte từ WTQ/HiTab source archives đã pin |
| records/runtime_snapshot.json | Python/platform/library/source fingerprints |
| archives/experiment_records.zip | Allowlist raw records/public workspace để audit local |
| integration_manifest, validation_report, file_manifest | Scope, automated checks và SHA-256 |

Đây là local assembly component, chưa phải Hub upload folder hoặc Hugging Face
Parquet configs hoàn chỉnh. Raw logs có local paths; bank có private answer/source.
Giữ evaluator-only records tách router-facing data ở bước ghép. Không upload ZIP
nguyên khối mà chưa áp dụng chính sách publication/attribution/visibility.

## 4. Provenance và adaptations

WTQ pin Git7d455a5a707b96341ef72aff9428749d443d8aa9, split pristine-unseen-tables;
HiTab pin Gitd179602662b490249baf068a76fbe4137029126e, split test_samples;
TableBench dùng TQA_test với exact cached JSONL SHA-256. Revision upstream cụ thể
của TableBench chưa được ghi trong cache, không tự điền HEAD hiện tại làm revision.
Giữ chi tiết này như unresolved provenance detail cho final card/assembly.

Original archives không bundle; per-packet source records và hash được giữ.
16 question string khác upstream, gồm typo/scope/order/unit clarification. Ledger
giữ cả hai bản; builder là adaptation authority. Header flattening và typed answers
là adaptation chung; không gọi bảng này official WTQ/HiTab/TableBench leaderboard.

License metadata: WTQ CC-BY-SA-4.0, HiTab Computational Use of Data Agreement v1.0,
TableBench Apache-2.0 theo source metadata. Giữ source-specific notices, attribution
và source hashes; không áp một license mới cho toàn bộ nội dung upstream.
WTQ/HiTab có original license text; TableBench license text/revision còn cần đối
chiếu tại final publication review. Không biến metadata này thành kết luận pháp lý.

## 5. Result selection và environment parity

Sáu run dùng bảng chính thức được gom dưới runs/structured_data/, giữ nguyên run ID.
README.md và collection_manifest.json trong thư mục đó ghi selection, đường dẫn
cũ–mới và kiểm tra checksum trước/sau di chuyển. Builder ưu tiên location mới,
vẫn đọc layout runs/<run_id> khi tái dựng từ archive lịch sử. Các audit directories
vẫn giữ đường dẫn gốc; component/ZIP đã đóng gói là snapshot riêng, không bị sửa.

Chọn đúng một complete run40 cho JEV/SOL/DREX/PPLX/single-agent/predefined.
Không lấy smoke, calibration fixed cũ hoặc best-of packet. Source/config lịch sử
giữ nguyên; patch hiện hành và current runtime snapshot được ghi riêng.
Predefined40 chưa có evaluation_report gốc; derived gold/metric đã được audit từ
final state và snapshots, không sửa raw episode.

Bốn router có241 shared tracked files cùng hash ở thời điểm chạy. Các baseline và
current engine có source delta. Replay240/240 episode khớp2084 states, preconditions,
1616 tools và final state; không tuyên bố toàn bộ engine bytes hoặc mọi prompt
của sáu batches giống nhau. Không có fresh hosted rerun sau inspection patch.

## 6. Kiểm định và lệnh

Chạy từ repository root trên environment đã cài dependencies:

~~~powershell
python scripts/prepare_structured40_release_component.py
python scripts/prepare_structured40_release_component.py --verify hf_release_staging/structured40_20261122
~~~

Builder từ chối overwrite component/ZIP cũ. Dùng --output với một child path mới
của hf_release_staging khi thay tài liệu/source; không regenerate snapshot lịch sử.
Builder tạo bảng results từ derived audit có input hashes, kiểm40 manifest, coverage240,
source/config backbone/budget, staging source closure và20 test trong payload.
File set/checksum verify và ZIP integrity ghi trong verification JSON ngoài component.
Không gọi model, Hub API hoặc sửa release registry.

Tests staged chạy trên installed host environment, không phải clean-venv/platform
certification. Có Python3.13/Windows version snapshot; các platform khác cần preflight.
Shared registry eager-import SpreadsheetBench nên lock có openpyxl, dù Table QA
không dùng Excel. Model weights, provider credentials và source archives là external.

Chạy future experiments từ payload:

~~~powershell
python scripts/run_shared_environment.py --config config/shared_environment/table_qa_jev_qwen9b.yaml --run-id structured40_jev_new_snapshot
python scripts/run_shared_environment_sol.py --config config/shared_environment/table_qa_sol_qwen9b.yaml --run-id structured40_sol_new_snapshot
python scripts/evaluate_shared_environment.py runs/structured40_jev_new_snapshot
~~~

Các config DREX/PPLX/single_agent/predefined dùng shared runner tương tự JEV.
Metric STOP F1/recovery hiện là derived report, chưa tự được generic evaluator
tổng hợp; giữ metric definitions/input records khi lắp final HF results.

## 7. Ghép với Formal40 và Track A

Assembler cuối cần chọn đúng40 Structured Data tasks thay thế cohort SpreadsheetBench20
trong revision mới; giữ archive/version cũ. Formal40 và phần Track A có manifest
riêng, không lấy cấu hình/label domain cũ làm mặc định cho40 tasks mới.
Legacy packager/certifier/FROZEN_DOMAINS vẫn mô tả20 Structured Data; không gọi
packager đó trực tiếp để tạo release mới mà chưa cập nhật spec.

Tách router-facing tasks/agents/public inputs, analysis trajectories/runs/provenance,
evaluator-only gold/results và human-review metadata. Giữ existing split policy
được quyết định ở release chung; component40 là full cohort, không tự sinh sealed
test hoặc suy nguồn upstream test thành contamination-free benchmark test.

Trước publish: verify combined dataset cardinality/checksums/schema/card, kiểm
publication visibility và source-specific notices, giữ review pending, ghi rõ
historical result selection/current snapshot/replay scope và version mới.
Việc upload là bước riêng theo yêu cầu người dùng.
