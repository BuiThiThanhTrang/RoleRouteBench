# Inspection handoff và metric dynamic routing của Table QA

Ngày: 2026-11-22. Phân tích tiếp theo của structured_data_release_readiness_20261122_vi.md.
Chỉ đọc trajectory/state, tính derived metrics và ghi báo cáo mới. Không sửa adapter,
packet, model config hay raw run records; không gọi hosted model.

## Kết luận cập nhật

Inspection revisit là lỗi projection có thể tái hiện. Tuy nhiên, không tìm thấy lỗi
đó trong320 episode của tám full runs đã kiểm tra. Riêng bốn router chính có221
inspection trả artifact, gồm70 lượt đọc lặp no_progress; tất cả artifact trả về
đều có trong observation kế tiếp. Mỗi episode của bốn router chính tạo tối đa2
inspection khác nhau, chưa đạt điều kiện đẩy inspection cũ ra ngoài cửa sổ3.

Do đó chưa có bằng chứng quy bất kỳ mức giảm accuracy, recovery hay chênh lệch
giữa bốn router hiện tại cho lỗi này. Không cần chạy lại toàn bộ chỉ vì phát hiện
reproducer. Cần sửa và kiểm định nó trước khi mở rộng benchmark/workflow.

Evidence: runs/structured_data_inspection_impact_20261122/impact_and_metrics.json
và metric_definitions.json. Reproducer trước đó ở
runs/structured_data_release_audit_20261122/inspection_revisit_probe.json.

## Cơ chế

inspect_table đọc một slice tối đa12 hàng. Lượt đầu tạo inspection:1, đưa dữ liệu
vào history và đặt current.inspection. Khi có nhiều slice, public_observation chỉ
đưa một số inspection vào prompt, chủ yếu ba artifact tạo gần nhất, cùng current
và các dependency của answer đang dùng.

_record deduplicate inspection theo nội dung. Nếu đọc lại slice cũ, nó trả artifact
đã có với changed=False. Nó không cập nhật current hoặc recency truy cập. Vì vậy,
nếu slice cũ đã ra khỏi cửa sổ và chưa được answer cite, lần đọc lại không đưa nó
trở về projection.

Reproducer offsets0,12,24,36 rồi0:

1. Bốn lượt đầu tạo inspection:1 tới inspection:4.
2. State trước lượt cuối chỉ thấy inspection:2,3,4.
3. Tool đọc lại offset0 và trả inspection:1 cùng các hàng của nó.
4. State sau lượt cuối vẫn chỉ thấy inspection:2,3,4; status là no_progress.

Dữ liệu vẫn ở history trong state.json và raw tool logs. Router nhận recent_events
đã bỏ raw result; executor lượt sau dựng prompt mới từ public_observation cộng
preview5 hàng đầu. Do đó raw result vừa trả không tự trở thành trí nhớ của role sau,
kể cả khi role sau có cùng tên với role trước.

Đây là vấn đề delivery/visibility của một lần đọc. Artifact không cần phải là
artifact mới mới có thể mang lại thông tin hữu ích cho context hiện tại.

## Ảnh hưởng tiềm tàng trong MAS

### Performance và chi phí

- Một inspection tiêu hao một trong12 attempted role calls nhưng thông tin yêu
  cầu không tới lượt sau. Repeating slice có thể tiếp tục trả no_progress.
- Router có thể giữ nguyên phân công, đổi role hoặc dừng dựa trên state thiếu dữ liệu.
  Số calls tăng, budget dành cho analyze/verify/recovery giảm.
- Nếu executor dùng preview hoặc slice khác để trả lời, có thể chọn sai hàng/scope.
  Public evidence verifier có thể chấp nhận giá trị được cite nhưng sai question;
  gold checker cuối mới phát hiện lỗi đáp án.

### Handoff và phối hợp

- Table Inspector có thể thực hiện đúng yêu cầu nhưng Evidence Selector,
  Numerical Analyst hoặc Answer Composer không nhận slice đó.
- Router không có tín hiệu rõ để phân biệt tool không tìm thấy dữ liệu, agent
  không tiến triển, hay harness không đưa dữ liệu vào projection.
- Lựa chọn role hợp lý vẫn có thể không tạo được tiến triển. Nếu lỗi bị kích hoạt
  không đồng đều, router dùng nhiều exploration/revisit sẽ chịu bất lợi khác nhau.

### Recovery

- Sau một sai sót về scope, quay lại bảng cũ để đối chiếu là một hành động recovery
  hợp lý. Revisit bị khuất sẽ làm luồng diagnose → inspect → sửa evidence bị đứt.
- Lượt đọc có thể không tạo last_error mới. Failure Diagnoser chỉ chạy khi có
  public failure, nên thiếu handoff không nhất thiết tạo được một diagnosis path.
- Diagnosis/verification trước đó có thể được lặp lại với cùng bằng chứng thiếu,
  tạo vòng lặp ngay cả khi router đã chủ động chọn thao tác sửa sai.

Ảnh hưởng có điều kiện: inspection còn trong cửa sổ hoặc được answer cite vẫn
hiện diện; preview5 hàng có thể đủ; analyze/select có thể giải trực tiếp bằng
headers/filters/row IDs. Lỗi không làm mọi task thất bại và không nằm trên mọi path.

## Đối chiếu các run hiện có

| Router/baseline | Inspection trả artifact | Đọc lặp no_progress | Max inspection khác nhau/episode | Artifact vừa đọc bị khuất |
|---|---:|---:|---:|---:|
| JEV | 49 | 5 | 2 | 0 |
| SOL | 70 | 29 | 2 | 0 |
| DREX | 31 | 6 | 2 | 0 |
| PPLX | 71 | 30 | 2 | 0 |
| Single-agent | 44 | 12 | 3 | 0 |
| Predefined | 40 | 0 | 1 | 0 |

Không tính inspect call lỗi không trả artifact vào cột inspection thành công/đọc lặp.
Hai fixed calibration cũ cũng có0 artifact vừa đọc bị khuất, nhưng dùng snapshot
verifier/state khác nên không thuộc matched comparison phía trên.

SOL/PPLX có nhiều repeated inspection không tiến triển; dữ liệu của các lượt đó
vẫn tới state kế tiếp. Đây là hành vi thực tế cần nghiên cứu riêng, không phải
bằng chứng inspection revisit bug đã kích hoạt.

## Hai cột dynamic routing đề nghị

Giữ nguyên hai cột task performance:

- Passed: public verification + router STOP, theo metric hiện tại.
- End-task pass: fresh final answer đạt trusted gold, không yêu cầu STOP.

Hai tập này có thể giao nhau nhưng không bao hàm nhau. Không cộng hai cột thành
success tổng. Public passed vẫn có thể sai gold.

### STOP F1, evaluator-derived

Positive state là state có answer fresh/đúng gold VÀ public verification fresh/pass.
Positive prediction là router chọn STOP.

- TP: STOP tại positive state.
- FP: STOP khi chưa đạt positive state, gồm dừng sớm hoặc public pass nhưng sai gold.
- FN: chọn non-STOP tại positive state.
- F1 = 2TP / (2TP + FP + FN).

Metric đánh giá cả premature STOP và tiếp tục điều phối khi đã hoàn thành đúng
contract. Tính trên từng quyết định router thực sự đã ghi, kể cả reserved STOP
opportunity tại budget0. Non-STOP bị suppressed tại một positive state vẫn là FN
cho termination, vì STOP còn được phép miễn phí.

Đây không phải human valid-action accuracy nhiều lớp. Gold chỉ dùng offline,
không đưa vào router/executor. F1 không đo khả năng đi tới positive state; phải
đọc cùng task pass/coverage. Policy chỉ giải được ít task vẫn có thể có STOP F1 cao.

### Recovery@PublicFailure

Opportunity là một episode từng có state:

1. Có last_error công khai hoặc vừa có action_rejected công khai;
2. Chưa có answer fresh/đúng gold;
3. Còn ít nhất1 call.

Recovery thành công nếu final answer fresh/đúng gold. Mỗi episode tính một lần,
không yêu cầu STOP ở endpoint này. Report cả tử số/mẫu số.

Metric đo khả năng đưa hệ thống từ một trạng thái cần sửa về đáp án đúng.
Nó bao gồm sửa scope, phép tính, representation, lỗi contract và precondition.
Không giả định mọi recovery phải dùng nhiều role; single-agent cũng có thể phục hồi.
Các policy tạo ra những failure/opportunity khác nhau, nên đây là observed
system-level recovery, không phải ước lượng nhân quả riêng cho router.

### Results dẫn xuất từ log hiện có

Tất cả cùng40 task, Qwen3.5-9B, budget12, tối đa1 tool call/lượt.

| Phương pháp | Passed | End-task pass | STOP F1 ↑ | Recovery@PublicFailure ↑ |
|---|---:|---:|---:|---:|
| JEV | 21/40 | 23/40 | 90.5% | 39.1% (9/23) |
| SOL | 24/40 | 27/40 | 91.7% | 45.8% (11/24) |
| DREX | 28/40 | 28/40 | 85.7% | 56.5% (13/23) |
| PPLX | 18/40 | 20/40 | 65.4% | 5.9% (1/17) |
| Single-agent | 26/40 | 25/40 | 89.4% | 56.5% (13/23) |
| Predefined | 28/40 | 29/40 | 78.8% | 52.2% (12/23) |

STOP confusion counts:

| Phương pháp | TP | FP | FN |
|---|---:|---:|---:|
| JEV | 19 | 4 | 0 |
| SOL | 22 | 4 | 0 |
| DREX | 27 | 1 | 8 |
| PPLX | 17 | 18 | 0 |
| Single-agent | 21 | 5 | 0 |
| Predefined | 26 | 14 | 0 |

DREX có recovery tốt và task pass cao nhất trong bốn router, nhưng có8 quyết định
tiếp tục tại state đã đúng/verified; một trong số đó ở boundary0. JEV/SOL ít
vấn đề tiếp tục sau completion, song vẫn có STOP khi chưa đạt đúng contract.
PPLX có nhiều STOP sai thời điểm và ít episode lỗi được phục hồi về đáp án đúng.
Các nhận xét là mô tả40 task/seed hiện có, không phải kết luận statistical dominance.

## Sửa và chạy lại

Bản sửa nên giữ immutable artifact và dedup; bảo đảm slice vừa yêu cầu xuất hiện
trong observation/handoff kế tiếp. Có thể cập nhật access recency/current view,
giữ giới hạn context. Không tạo artifact mới giả để đánh dấu progress.
Đọc lặp slice đang hiện diện có thể tiếp tục là no_progress; đọc lại slice đã khuất
phải được ghi nhận là khôi phục thông tin quan sát được.

Kiểm tra cần có:

- Reproducer0,12,24,36,0: slice cuối tới router và executor role kế tiếp.
- Repeat slice đang hiển thị: không tạo progress giả.
- Inspection cũ đã được cite: dependency/freshness không bị mất.
- Handoff inspect → select/analyze/compose → verify, dùng dữ liệu trong slice cũ.
- Không thêm private data hoặc nới context khác nhau theo router.

Không cần full rerun chỉ để kiểm tra lỗi này trong các kết quả hiện có.
Với fix tối thiểu chỉ re-expose inspection đang bị khuất, replay sáu run40 hiện
hành để xác nhận các recorded state/tool semantics không đổi, rồi chạy stress
tests deterministic. Nếu fix đổi current pointer/recency/prompt ở cả những lượt
đọc vốn đang hiện diện, replay có thể khác; khi đó không gọi run cũ là run của
engine mới.

Nếu chuẩn bị bảng results canonical trên một engine release mới với visibility
đã thay đổi, đề nghị chạy matched JEV/SOL/DREX/PPLX + single-agent/predefined,
cùng40 task, backbone, budget, pool và sampling. Chưa có lý do bắt buộc chạy lại
TableGPT2 hoặc hai fixed calibration cũ chỉ vì inspection bug.
