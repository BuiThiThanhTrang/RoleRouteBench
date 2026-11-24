# Chuẩn bị thành phần Formal Proof cho release kết hợp

Cập nhật 2026-11-23. Chỉ chuẩn bị local component Formal40. Release cuối còn
ghép Structured Data và Track A V2; chưa upload hoặc thay dataset trên Hub.
Track A V2 đã rebuild/validate 997 state từ bốn domain hiện hành nhưng chưa gán
nhãn, nên không bundle nhãn V1 hoặc mô tả V2 là leaderboard đã hoàn tất.

## Tài liệu hiện hành

- [State/protocol](formal_proof_state_protocol_vi.md).
- [Harness/runtime/luồng thông tin](formal_proof_harness_information_flow_vi.md).
- [Fixed baseline](formal40_fixed_baseline_vi.md).
- [Nhận xét router/fixed dùng cho release](formal40_router_fixed_release_observations_vi.md).
- [Packet preparation lịch sử](formal40_packet_preparation_vi.md).

README/preparation_report trong bank20261118 là snapshot lịch sử, còn ghi
pilot/provider smoke pending và config cũ. Giữ nguyên byte/hash vì các run đã
tham chiếu bank này. Hướng dẫn hiện hành nằm ở docs và overlay release mới.

## Các điểm đã đối chiếu

Bank40 dùng adapter v2; protocol artifact-first v2, handoff v2, presentation
parser/identity và tactic Inspector. Budget12, input12288, proof4096,
diagnosis/retrieval1024, sampling0.6/0.95. Hai runtime pin; compile300,
Inspector180. Timeout180 trong packet không thay runtime override300.

Current role card là config/shared_environment/formal40_inspector_roles.json.
Inspector khác card trong bank ban đầu; component phải dùng current overlay.
Chỉ public manifest files được materialize cho MAS. Human review40 packet
còn pending, khác với bằng chứng kernel/runtime đã pass.

## Component local

Builder: scripts/prepare_formal40_release_component.py.
Output hiện hành: hf_release_staging/formal40_20261122_final40_grouped/.
Chỉ giữ component cuối; các component/bảng partial cũ được dọn sau khi kiểm
định bản thay thế. Raw runs và attempt cũ vẫn giữ nguyên để audit.

- payload/: bank copy byte-for-byte, config/role cards hiện hành,
  source dependency closure, Lean driver, requirements, docs và reports.
- records/: tasks, agents, run inventory và episode/attempt selection.
- archives/experiment_records.zip: local run records và public runtime artifacts.
- integration_manifest.json, validation_report.json, file_manifest.json:
  phạm vi, kiểm định và SHA-256.

Đây là component để ghép, **không upload folder này trực tiếp**. Bank có
private evaluator artifacts; archive có raw model logs/local paths. Chính sách
công bố các phần này được quyết định ở bước lắp release cuối. Builder không có
bước publish hoặc sửa Track A/Structured Data.

## Kiểm định và tái dựng

Kiểm tra bank integrity,40 manifest, profile parity, role card, run coverage,
staged checksums và native cohort gates30/10. Không gọi hosted model. Witness
kernel evidence40 được tái sử dụng từ preparation, không mô tả là vừa compile
lại toàn bộ witness trong bước đóng gói.

Không bundle model weights, tokenizer cache, Lean/Mathlib binaries hoặc secrets.
Máy tái dựng cần provision đúng runtime/layout và dùng
prepare_formal_executor_resources.py để tải tokenizer pin. Môi trường đã kiểm
định là Windows; không mặc định chạy ngay trên Linux. Staged native validation
dùng external resources của máy chuẩn bị, không đổi config được đóng gói.

Dùng Python Formal tokenizers0.22.2. Trên máy hiện tại:

~~~powershell
$project = '<ROLE_ROUTEBENCH_ROOT>'
$py = (Get-Command python).Source
& $py "$project\scripts\prepare_formal40_release_component.py"
& $py "$project\scripts\prepare_formal40_release_component.py" `
    --verify "$project\hf_release_staging\formal40_20261122_final40_grouped"
~~~

Builder từ chối overwrite output đã tồn tại. Dùng output/version mới cho
candidate khác, giữ nguyên archive/registry lịch sử.

## Results và ghép release cuối

16 run nguồn của bảng chính thức được gom tại runs/formal_proof/.
README.md và official_run_manifest.json trong thư mục đó ghi từng run,
runtime và danh sách packet được chọn; relocation_manifest.json lưu checksum
trước/sau di chuyển. Không gom các pilot hoặc api_retry1 không đóng góp số liệu.
Nội dung raw run, frozen config và đường dẫn tuyệt đối lịch sử trong log giữ
nguyên; dùng manifest để ánh xạ vị trí cũ sang mới. Config output_root lịch sử
vẫn là runs, không sửa run đã đóng băng để resume tại vị trí mới.

Fixed và cả4 dynamic router có đủ40 packet sạch/phương pháp:200/200 episode,
không có infrastructure hoặc audit UNAVAILABLE, không loại packet.
Selection áp dụng15 API retry2, rồi thay JEV04/PPLX22/PPLX26 bằng infra_retry3
bất kể pass/fail. JEV04 pass3 calls; PPLX22/26 proof FAIL12 calls; cả hai run
retry3 có freeze unchanged=true. Không chọn attempt theo điểm.

Chỉ giữ [bảng cuối40](../report/formal40_final_results.md),
[JSON có provenance/attempt selection](../report/formal40_final_results.json),
[CSV](../report/formal40_final_results.csv). Tái dựng bằng
report/build_formal40_fixed_comparison.py; không tạo bảng cohort nhỏ/partial.
Accuracy: SOL/PPLX13/40, JEV12/40, fixed11/40, DREX10/40. Single-agent matched
và human routing labels chưa có; results hoàn tất không đồng nghĩa human review
hoặc leaderboard nhiều seed đã hoàn tất.

Source delta của retry3 có file Table QA adapter ngoài phần logging transport;
file này không được chọn làm execution adapter cho Formal40. Component ghi
old/new hashes và kiểm tra current file khớp retry3; formal core khớp fixed.
Không ghi full-source identical khi toàn bộ source manifest có khác biệt.

Packager package_routingbench_v4_track_b_hf.py và FROZEN_DOMAINS.json vẫn mô tả
formal30 cũ. Chưa sửa chúng vì packager còn thay đổi/xóa dữ liệu dùng chung và
mặc định giữ Track A nguyên trạng, khác phạm vi release kết hợp sắp tới.

Khi đủ ba thành phần, assembler mới cần ghép40 tasks/current runtime-protocol
từ component này với Structured Data và đúng phần Track A đã chọn, giữ các
phần khác theo release plan chung. Giữ review pending, licenses/provenance,
runtime variants, engine hashes và attempt selection; không kế thừa nhãn
human_verified của formal30 cũ. Sau final package/card validation mới publish
riêng theo yêu cầu người dùng. Component version không tự quyết định version
chung của dataset; mở rộng sample sau này dùng revision/selection mới.
