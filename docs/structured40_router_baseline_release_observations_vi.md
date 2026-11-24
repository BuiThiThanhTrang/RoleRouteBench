# Structured40: nhận xét router và baseline cho release

Cập nhật2026-11-22. Đọc bảng hiện hành report/structured40_final_results.md và JSON/CSV
cùng tên. Phạm vi là release kết hợp Formal Proof, Structured Data và phần Track A
được chọn; human labels/state review vẫn có trạng thái riêng.

## Mục tiêu của cập nhật

SpreadsheetBench20 trước đây có floor effect với executor nhỏ. Cohort mới chuyển
sang40 task Table QA được normalize input/output, với22 WTQ,14 HiTab,4 TableBench.
Mục tiêu là tạo task có thể tiến triển, nhiều đường đi và nhánh phục hồi để phân
biệt routing. Không chọn task hoặc định nghĩa metric nhằm buộc dynamic thắng fixed.

Đây là thay task family/contract/source mix và tăng cohort từ20 lên40; không phải
chỉ thêm20 task vào bank SpreadsheetBench. Thay đổi task, contract và budget giữa
các thế hệ không cho phép quy causal accuracy gain cho riêng độ khó hoặc router.
All40 reference paths pass chứng minh runtime/tools có lời giải; không chứng minh
mọi task đều vừa sức backbone hoặc đã được human review.

## Kết quả hiện có

Sáu complete runs có240 episode, không thay attempt/best-of; mỗi method dùng đủ40.
Gold pass JEV23, SOL27, DREX28, PPLX20; single25, predefined29.
Public pass+STOP tương ứng21/24/28/18/26/28. Hai metric có thể bất đồng:
false public pass JEV2, SOL2, DREX1, PPLX1, single5, predefined2.

STOP F1 cao nhất trong bốn dynamic là SOL91.7%, sau đó JEV90.5%, DREX85.7%,
PPLX65.4%. DREX có8 non-STOP decisions tại correct/verified states, gồm1 ở boundary0.
PPLX có18 STOP khi chưa đạt đúng contract. Không diễn giải STOP F1 như overall
task accuracy; policy giải ít task vẫn có thể có stopping score cao.

Recovery@PublicFailure: DREX13/23, SOL11/24, JEV9/23, PPLX1/17; single13/23,
predefined12/23. Mỗi policy gặp tập failure khác nhau; tỷ lệ này đo system recovery
quan sát được, không cô lập causal contribution của router. Một recovery có thể
do cùng role sửa hoặc do handoff nhiều role.

## Đa dạng trajectory và chiến thuật

Cả7 specialist role được dùng trong mỗi run dynamic. Unique dispatched-role
sequences: JEV27, SOL32, DREX31, PPLX24. Không đếm STOP/rejected actions trong
sequence này và không gọi sequence entropy/diversity là chất lượng routing.

- JEV thiên Answer Composer127 calls; Header Resolver2. Direct answering có thể
  hợp lý ở lookup/preview task, nhưng không bảo đảm evidence đủ cho mọi question.
- SOL có70 Inspector và52 Analyst calls, cùng74 Composer. Chọn evidence nhiều
  hơn liên quan tới workflow đa dạng nhưng chưa chứng minh gây ra cải thiện.
- DREX kết hợp53 Analyst,49 Selector,60 Composer và14 Header calls. Có recovery
  và gold pass cao nhất trong dynamic, vẫn có trường hợp tiếp tục sau completion.
- PPLX có71 Inspector,111 Composer,25 Diagnoser và25 Analyst calls; thấp về recovery
  trong lần đo này. Không quy mọi failure cho backbone hoặc một role riêng lẻ.

SOL/PPLX có29/30 inspection lặp no_progress; JEV5, DREX6. Không có artifact vừa đọc
bị khuất trong các episode này. Repeated read không tiến triển khác với lỗi handoff.
Chi phí role calls không đồng nhất chi phí token/API, nên số lần gọi role chưa đủ
để tuyên bố tiết kiệm tiền hoặc latency.

## Baseline và claim phù hợp

Predefined là literal sequence có terminal short circuit; không phải pipeline có
gating thông minh. Có29 precondition rejection trong run40; single-agent không có
model router nhưng phải tự chọn tool. Cùng task/backbone/budget không bảo đảm source
bytes lịch sử giống nhau: adapter replay tương đương được ghi riêng.

Dynamic có thể bỏ bước dư, chọn loại evidence và đổi nhánh sau feedback. Các kết
quả hiện tại cho thấy chiến thuật khác nhau; predefined vẫn có end-task pass29/40
và single25/40. Benchmark không cần dynamic thắng baseline để có giá trị.

Chỉ một full run/method,40 task và recovery opportunities nhỏ. Không tuyên bố
statistical dominance, leaderboard ổn định hoặc role causal usefulness.
Đối chứng cùng failure state và repeated seeds là ablation hữu ích sau này.

## Patch inspection và provenance

Lỗi cached inspection bị khuất đã sửa bằng5 dòng, không có bằng chứng nó kích hoạt
ở các run dùng bảng results. Stress tests và replay240 episode pass. Kết quả lịch sử
giữ source hashes gốc; snapshot sau sửa chỉ làm engine cho future runs/release.
Không diễn giải replay như một lần gọi model mới.

## Các revision sau

Giữ mốc40 cùng selection và protocol version. Sample mới có thể mở rộng routing
opportunities, table hierarchy, calculations, ambiguity có thể giải và recovery.
Thêm nguồn khi có input đủ thông tin, provenance/license, trusted checker và
backbone calibration phù hợp. Tránh tăng difficulty bằng task không có tiến triển.

Mỗi revision ghi source/dedup/selection criteria và baseline coverage; không chọn
task theo router winner hoặc chỉ thêm task khiến một method có lợi.
Chưa chốt số sample, nguồn mới hay ngày cập nhật tiếp theo. Nếu tool/state contract
đổi, version môi trường và thử baseline parity; nếu chỉ thêm cohort, giữ cohort
breakdown và không silently đổi denominator của các bảng lịch sử.
