# Formal40: nhận xét router và fixed workflow cho release

Cập nhật 2026-11-22. Ghi chú dùng cho dataset card/changelog của bản cập nhật
gồm Formal Proof, Structured Data và một phần Track A. Chưa phải tuyên bố
leaderboard ổn định hoặc human routing labels đã nghiệm thu.

## Mục tiêu và quyết định release

Track B cung cấp môi trường, công cụ, role contracts, visibility, budget và
checker thống nhất để quan sát điều phối một hệ thống executor nhỏ. Với
temperature 0.6, các router có thể đi tới candidate và failure state khác nhau;
đây là diễn biến bình thường của end-to-end evaluation. Đối chứng cùng failure
state là ablation bổ sung, không phải điều kiện phát hành domain.

Có cơ sở phát hành Formal40 như cohort mở rộng đã kiểm định thực thi và có
giá trị phân tích routing, tiếp tục calibration sau. Witness pass chứng minh
bài toán formal có lời giải trong runtime, không chứng minh mọi task đều vừa
sức SLM. Không cần dynamic thắng fixed mới công nhận benchmark có giá trị.

## Dữ liệu hiện tại

- 40 packet: 8 MiniF2F, 20 LeanDojo, 10 APRIL, 2 Putnam.
- Hai runtime: 30 packet Lean 4.8.0-rc1 và 10 packet Lean 4.22.0-rc4.
  Hai cohort khác đề, không phải A/B cùng đề đổi runtime.
- Fixed đã hoàn tất và được independent audit đủ40: 11 workflow success,
  11 proof pass, không có infrastructure được detector hiện tại ghi nhận.
- Dynamic giữ attempt gốc, thay đúng15 cặp lỗi API đã chọn trước bằng retry2,
  sau đó thay JEV04/PPLX22/PPLX26 bằng infra_retry3 bất kể pass/fail, không best-of.
  Ba retry mới có freeze unchanged=true và không lỗi infrastructure: JEV04
  thành công3 calls; PPLX22/26 thất bại proof sau12 calls.
- Selection cuối đủ200/200 episode,40 packet/phương pháp, không loại packet,
  không còn infrastructure hoặc audit UNAVAILABLE. PPLX37/38 đã hoàn tất cùng
  run retry2, đều thất bại proof sau12 calls. Attempt cũ vẫn ở runs để audit.
- Source delta của retry3 ngoài logging transport là adapters/table_qa.py,
  thuộc adapter domain khác; registry chọn FormalProofV2Adapter cho Formal40.
  Formal core giữ nguyên so với fixed/retry2; JSON cuối ghi riêng hashes khác.
- Lỗi403 trước đó được error body xác nhận là monthly spending limit;
  không dùng làm bằng chứng về năng lực giải proof/routing.
- Single-agent cũ khác bank, Goedel32B, budget8 và protocol. Chưa có matched
  single-agent Formal40/Pythagoras/budget12.

## Kết quả cuối và chiến thuật

Chỉ dùng [bảng cuối đủ40 packet](../report/formal40_final_results.md),
[JSON](../report/formal40_final_results.json) và [CSV](../report/formal40_final_results.csv).
Các bảng cohort nhỏ/partial và các gói staging cũ đã được thay bằng bản cuối;
không dùng chúng làm kết quả hiện hành.

- SOL và PPLX cùng13/40 (32.5%); JEV12/40 (30%); fixed11/40 (27.5%);
  DREX10/40 (25%). DREX có11 proof pass nhưng chỉ10 workflow success.
- Recovery: SOL3/29 (10.3%), PPLX2/29 (6.9%), fixed1/28 (3.6%),
  JEV1/29 (3.4%), DREX0/30. JEV04 mới thành công ngay, không tăng recovery.
- JEV gọi Diagnostician76 lần; SOL gọi Retriever32/Inspector12;
  DREX có200 chuyển tiếp Repair→Repair; PPLX gọi Compiler109 lần.
  DREX không gọi Retriever; PPLX không gọi Inspector. Fixed không có hai role
  này trong sequence. Đếm role không tự chứng minh role hữu ích/action đúng.
- Executor text token proxy/task: fixed19.9k, PPLX36.3k, JEV43.8k,
  SOL44.6k, DREX48.5k. Latency proxy tương ứng96.0/204.9/199.8/188.0/207.3s.
  Provider load và thời điểm chạy khác nhau làm nhiễu so sánh latency.

Mẫu số recovery phụ thuộc trajectory. Số recovery ít và chênh lệch accuracy
chỉ vài task, chưa đủ kết luận thứ hạng ổn định. SOL đa dạng evidence và recovery
cao hơn trong lần đo này; PPLX đạt cùng accuracy với token proxy thấp hơn.
JEV thiên về diagnosis; DREX thiên về sinh lại proof và có60% no-state-change.

Hai episode vừa hoàn tất vẫn thể hiện nhánh Repair–Compiler: sample37 có8 Repair
và4 Compiler; sample38 có10 Repair và2 Compiler. Không gọi Retriever, Inspector
hay Diagnostician. Sample38 có9 invalid_output trong10 Repair. Đây là quan sát
thất bại generation/proof và lựa chọn tiếp tục cùng nhánh, không phải API outage.
Terminal reason lưu PREMATURE_STOP nhưng cả hai đã dùng hết12 calls; không diễn
giải nhãn này là dừng sớm khi vẫn còn ngân sách.

## Dynamic, fixed và single-agent

Dynamic có thể chọn loại evidence, bỏ bước dư hoặc tiếp tục một nhánh còn triển
vọng; cũng có thể lặp generation và phát sinh router overhead. Fixed có chi phí
executor quan sát thấp hơn trên các cohort đã đo, nhưng ít khả năng đổi nhánh.

Fixed là literal sequence S→C→V và hai vòng D→R→C→V, tổng11 bước trong cap12,
dừng khi terminal pass. C fail vẫn dẫn tới V bị precondition reject, tốn role
call nhưng không sinh backbone tokens. Trên40 packet có96 rejection/356 calls;
57.3% no-state-change gồm cả các rejection. Không diễn giải kết quả như đã thắng
mọi gated pipeline hoặc đồng nhất path length với token cost.

Single-agent tự chọn tools, không có model router riêng; backbone phải đảm
nhiệm cả lập kế hoạch và thực thi. Chưa có số liệu matched để xếp hạng nó với
Formal40 hiện tại. Không gộp kết quả single-agent cũ vào bảng này.

## Ba tình huống minh họa

**MiniF2F05:** SOL lỗi áp dụng h₁ với đối số proof Even4 thay vì số nguyên,
sau một Repair lặp và một candidate trùng mới gọi diagnosis; Repair tiếp theo
sửa cách áp dụng giả thiết rồi C/V pass, tổng8 calls. Các phương pháp khác
đều giải ngay3 calls. Đây là recovery hợp lệ, chưa chứng minh SOL hiệu quả hơn
trên task hoặc diagnosis là điều kiện cần.

**LeanDojo23:** S lỗi generation → L kiểm tra symbols → S tạo candidate →
C báo goal nil → R bổ sung xử lý nil → C→V pass, tổng7 calls. Không gọi
Diagnostician/Inspector. Lookup có một tên unknown và type information cho
các symbol khác; chưa chứng minh có lemma then chốt. Bằng chứng trực tiếp là
feedback fresh được bàn giao đủ và Repair thay đổi đúng nhánh còn lỗi.
JEV lặp diagnosis cũ dù nhận lỗi mới; DREX/PPLX không đổi candidate; fixed có
reject, diagnosis kém hữu ích và repair lỗi generation. Candidate ban đầu khác
nhau nên không quy toàn bộ thành bại cho policy.

**APRIL36:** PPLX và fixed đều recovery: **5 so với7 total calls**, lần lượt
4 và5 calls sau lỗi proof đầu tiên; executor text tokens **9413/14185**.
Đây là một ví dụ ủng hộ khả năng rút ngắn workflow và tiết kiệm token, chưa
phải bằng chứng tổng quát từ nhiều task/lần lặp.

## Claim phù hợp để công bố

Formal proof có thể nhiều tactic/suy luận bên trong một executor call, trong
khi đường MAS giải ngay chỉ S→C→V. Mô tả phù hợp là quy trình tạo/sửa proof
lặp có kiểm chứng và các nhánh thu thập evidence; không mặc định mọi packet
đều cần workflow MAS dài hoặc nhiều function-specific agents.

Giả thuyết: ở các tình huống phục hồi được, dynamic routing có thể chọn
evidence/reviewer phù hợp và tránh bước dư, đạt chất lượng tương đương hoặc
cao hơn với ít calls/executor tokens hơn fixed. Có khác biệt chiến thuật và
một số ví dụ thuận lợi; claim tổng quát vẫn cần thêm dữ liệu.

## Metric và giới hạn đi cùng kết quả

- Success gồm workflow/STOP và independent final audit; ProofPass báo riêng.
- Recovery hiện đếm logical compile/verify failure, không gộp API errors và
  mọi generation-format failure vào một mẫu số.
- Calls/success chịu ảnh hưởng tập task giải được; xem paired-success data.
- No-state-change là proxy, gồm rejection; không phải human action accuracy.
- Executor text tokens đếm input/output quan sát bằng tokenizer pin, không
  phải USD, chưa gồm router tokens và generation không quan sát được.
- Latency là filesystem proxy, chịu ảnh hưởng thời điểm chạy, compilation
  và tải provider; không tự quy chênh lệch cho routing.
- Compile timeout có thể do candidate/tactic tốn tài nguyên. Giữ riêng nó
  với401/403/429/504 và công bố attempt selection/provenance.

Giữ bản40 làm mốc có version. Packet mới nên bổ sung độ phủ failure/workflow,
không chọn chỉ để cải thiện thứ hạng một router. Human review còn pending;
không gắn nhãn tất cả packet vừa sức SLM hoặc leaderboard hoàn chỉnh.

Nguồn duy nhất cho số liệu hiện hành: [Formal40 final results](../report/formal40_final_results.md).
