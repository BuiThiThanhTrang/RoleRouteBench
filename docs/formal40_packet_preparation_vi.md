# Hoàn thiện 40 packet Formal Proof

> Tài liệu này ghi quy trình và trạng thái tại bước preparation ngày 2026-11-18;
> các câu “chưa có performance” phía dưới chỉ nói về bước đó. Thiết kế live
> hiện hành ngày 2026-11-20: [State và protocol](formal_proof_state_protocol_vi.md),
> [Harness, runtime và luồng thông tin](formal_proof_harness_information_flow_vi.md).

Ngày 2026-11-18.

## Chuẩn áp dụng

- domain_extension_packet_adapter_artifact_standard_vi.md.
- benchmark_domain_packet_completion_playbook_vi.md.
- code_formal_environment_design_vi.md.
- formal_proof_domain_integration_vi.md.
- minif2f_environment_preparation_vi.md.

Bank ở data/RoutingBench/formal40_pythagoras_v1_20261118.
Danh sách source ID đúng với formal40_pythagoras_candidate_selection_20261118.
Tỷ lệ là 8 MiniF2F, 20 LeanDojo, 10 APRIL và 2 Putnam. Các mẫu được giữ qua
quá trình sửa runtime và witness. Hai witness Putnam do project viết và được Lean
kiểm chứng. Witness MiniF2F tái sử dụng bank chuẩn bị trước. Source và license có
provenance riêng cho từng packet.

## Implementation

Builder authoritative là scripts/prepare_formal40_packets.py. Các bản port và witness
đầu vào nằm ở data/RoutingBench/formal40_preparation_inputs_20261118. Source gốc và
archive lock được lưu trong formal40_candidate_sources_20261118 và selection đã pin.
Builder đọc preparation inputs, kiểm tra hash, lấy goal bằng Lean, chạy kernel gate
rồi ghi manifest/public/private/fixture và các lock cấp release.

Adapter mới formal_proof.lean4.v2 đăng ký candidate ban đầu cho cohort APRIL và
ghi event có origin environment. Artifact ban đầu giữ đúng byte và hash của Main.lean
trên Windows. Candidate source là độc lập với diagnostic/rejected artifacts, nên
một rejected write giữ candidate được chấp nhận còn fresh.

LeanDojo dùng namespace/open/variables từ source đã pin, cùng Mathlib runtime đã
port. Verifier kiểm tra toàn bộ dependency proof để loại lời giải gọi theorem
đích gốc hoặc lemma phụ thuộc vào nó. Contract công khai danh sách loại này.
Kernel negative control kiểm tra cả lời gọi trực tiếp và lời gọi qua alias.

Actor hỗ trợ codec Lean nguyên văn và payload audit cho adapter v2.
Pool 7 role, action space đầy đủ và STOP dùng chung runner.
Cấu hình mẫu dùng Pythagoras-Prover-4B và budget 12, worker 1.

## Các port đã ghi nhận

- LeanDojo chuyển import sang Mathlib snapshot đã pin và giữ declaration header,
  scoped variables, namespace và các open cần thiết. Tên target chuẩn hóa theo packet.
- IsPwo chuyển thành tên IsPWO của runtime 4.8. Một số tactic API ở private witness
  được đổi theo phiên bản. Các thay đổi nằm trong recipe từng packet.
- Packet 15 tắt simp attribute của target gốc vì witness ban đầu vô tình dùng rule đó.
- APRIL khôi phục context/import hợp lệ quanh proof body lỗi, phù hợp edit scope.
- Packet 33 ghi rõ binder List và universe Type u. Standalone preflight phát hiện
  Type* cần notation Mathlib, dù batch có import tổng hợp vẫn compile được.
- Hai task Putnam giữ nguyên statement và có witness đại số do project viết.

## Kiểm định

Evidence ở runs/formal40_preparation_20261118 và runs/formal40_preflight_20261118.

Kernel gate riêng cho từng packet dùng đúng imports của packet để tránh batch
che mất dependency hoặc notation. Batch goal/kernel là evidence bổ sung.
10 candidate APRIL phải compile thất bại trong context hợp lệ. 40 packet được
kiểm tra manifest, public-only materialization, context serialization/readability
của 7 role, mutation policy, accepted pointer và compiler/verifier preconditions.

Bốn smoke đại diện bốn nguồn chạy compile, kernel verification, freshness và
trusted final evaluator thật. Proof hole phải fail evaluator. Các kiểm tra codec,
seed lineage, host IO/metaprogramming rejection và target dependency có báo cáo riêng.
Đây là preparation với witness, số hosted model calls và benchmark trajectories bằng 0.

Bộ test hồi quy shared domains, shared environment và table QA có tổng 36 test.
Smoke Code Debugging lần đầu thất bại ở Git clone mirror local trong môi trường hạn chế.
Chạy lại cùng test với quyền clone local đã pass. Chi tiết ở regression_report.json.

## Trạng thái

preparation_report.json trong bank là nguồn authoritative cho kết quả nghiệm thu.
Mục tiêu của bước này là deterministic-ready. Pythagoras pilot/provider I/O smoke,
human packet review và routing labels tiếp tục được theo dõi bằng trạng thái riêng.
Bank chưa có kết quả performance của Pythagoras hoặc của bất kỳ router nào.
