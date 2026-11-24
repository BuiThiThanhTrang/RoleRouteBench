# RoleRouteBench: kết quả router trên Track A và Track B

Ngày tổng hợp ban đầu: 2026-11-09. Cập nhật bốn domain và trạng thái Track A V2: 2026-11-23.

## Trạng thái hiện hành

- Track B hiện có **112 task/phương pháp**: database 12, code debugging 20,
  formal proof 40 và structured data processing 40.
- Hai cohort đã cân bằng là Formal40 và Structured40. Database và code debugging
  dùng các run rerun ngày 2026-11-23 trên source revision hiện hành.
- Track A V2 đã rebuild và validate từ đúng các run Track B hiện hành, nhưng
  **chưa gán nhãn**. Vì vậy chưa có Track A V2 accuracy và không được dùng các
  điểm của Track A V1 để xếp hạng cùng Track B mới.
- Track A V1 gồm 568 state và bảng Track B 82 task ngày 2026-11-09 được giữ phía
  dưới như snapshot lịch sử, không phải bảng kết quả hiện hành.

## Định nghĩa metric của snapshot Track B V4 cũ

Mỗi router ban đầu chạy 82 packet: database 12, code debugging 20, formal proof 30 và structured data processing 20. Ba episode formal proof của JEV có `infrastructure_failure = true` được loại khỏi cả tử số lẫn mẫu số, nên JEV có 79 episode hợp lệ; các router còn lại giữ 82.

- **Pass + STOP (P):** `result.passed = true` và router đã chọn `STOP`.
- **End-task pass, không STOP (E):** final task audit độc lập trả `passed = true`, nhưng state cuối không chọn `STOP`.
- Hai nhóm trên loại trừ nhau. `Track B success = P + E` và `Track B accuracy = (P + E) / N hợp lệ`.
- Ba episode formal proof lỗi hạ tầng của JEV là exclusion đã biết. Một episode còn lại chỉ được tính thành công nếu thuộc đúng P hoặc E như trên.

Formal proof trong bảng dùng các run có cùng executor Goedel-Prover-V2-32B. Structured data của JEV lấy từ canonical Track B package đã đóng băng.

Run nguồn hiện hành của hai domain refresh được gom tại [`runs/database`](../runs/database/README.md) và [`runs/code_debugging`](../runs/code_debugging/README.md). Selection PPLX code nằm trong `runs/code_debugging/collection_manifest.json`.

## Kết quả cập nhật ngày 2026-11-23

Phần này dùng cùng metric `P + E` ở trên. Accuracy được chia cho toàn bộ packet được yêu cầu; `U` là final audit không khả dụng và được ghi riêng, không tự động tính là pass. Sáu cấu hình database và sáu cấu hình code debugging đã được chạy trên source hiện hành với cùng packet bank, role pool, executor và budget trong từng domain.

### Database: sáu cấu hình trên source hiện hành

| Cấu hình | P | E | Success / 12 | Accuracy | CALL_LIMIT | PREMATURE_STOP |
|---|---:|---:|---:|---:|---:|---:|
| JEV | 9 | 0 | 9/12 | **75.00%** | 3 | 0 |
| Drex 9B | 8 | 1 | 9/12 | **75.00%** | 4 | 0 |
| PPLX Decider Flash | 7 | 1 | 8/12 | **66.67%** | 4 | 1 |
| Sol | 10 | 0 | 10/12 | **83.33%** | 2 | 0 |
| Fixed workflow | 7 | 0 | 7/12 | **58.33%** | 0 | 5 |
| Single-agent | 9 | 0 | 9/12 | **75.00%** | 3 | 0 |

### Code debugging: sáu cấu hình trên source hiện hành

| Cấu hình | Source snapshot | P | E | Success / 20 | Accuracy | U |
|---|---|---:|---:|---:|---:|---:|
| JEV | mới, 2026-11-23 | 12 | 0 | 12/20 | 60.00% | 0 |
| Drex 9B | mới, 2026-11-23 | 0 | 11 | 11/20 | 55.00% | 0 |
| PPLX Decider Flash | mới + infra retry | 13 | 1 | 14/20 | **70.00%** | 0 |
| Sol | mới, 2026-11-23 | 15 | 0 | 15/20 | **75.00%** | 0 |
| Fixed workflow | mới, 2026-11-23 | 14 | 0 | 14/20 | **70.00%** | 0 |
| Single-agent | mới, 2026-11-23 | 8 | 5 | 13/20 | **65.00%** | 1 |

Single-agent có 13 pass trong 19 final audit khả dụng, tương đương 68.42% trên mẫu đã đánh giá; bảng chính giữ mẫu số 20 để không che packet `code-bugsinpy-fastapi-10` đang `UNAVAILABLE`.

PPLX dùng 18 packet từ full run và thay đúng `code-quixbugs-flatten`, `code-quixbugs-quicksort` bằng infra retry sạch. Retry được chọn theo provenance, không theo pass/fail: `flatten` pass, `quicksort` fail do `PREMATURE_STOP`.

### Chênh lệch so với lần chạy trước

| Domain | Cấu hình | Accuracy cũ | Accuracy mới | Delta |
|---|---|---:|---:|---:|
| Database | JEV | 58.33% | 75.00% | +16.67 pp |
| Database | Drex 9B | 50.00% | 75.00% | +25.00 pp |
| Database | PPLX Decider Flash | 41.67% | 66.67% | +25.00 pp |
| Database | Sol | 66.67% | 83.33% | +16.67 pp |
| Database | Fixed workflow | 66.67% | 58.33% | -8.33 pp |
| Database | Single-agent | 41.67% | 75.00% | +33.33 pp |
| Code debugging | JEV | 60.00% | 60.00% | 0.00 pp |
| Code debugging | Drex 9B | 55.00% | 55.00% | 0.00 pp |
| Code debugging | PPLX Decider Flash | 55.00% | 70.00% | +15.00 pp |
| Code debugging | Sol | 75.00% | 75.00% | 0.00 pp |
| Code debugging | Fixed workflow | 50.00% | 70.00% | +20.00 pp |
| Code debugging | Single-agent | 60.00% | 65.00% | +5.00 pp |

Kết quả refresh này được dùng trong bảng tổng hợp 112 task bên dưới. Raw run và
selection manifest là nguồn chuẩn; không cộng lại từ bảng snapshot lịch sử.

### Vì sao accuracy thay đổi giữa hai lần chạy

Chênh lệch không đến từ max token, packet count hay việc đổi executor: các run matched vẫn dùng budget 8, output limit 16K và cùng executor theo domain. Có ba nguồn chính:

1. **Harness hiện hành làm thay đổi closed-loop trajectory.** `shared_actor` và `shared_runner` mới ghi contract error có cấu trúc và đưa failure evidence vào state tiếp theo. Single-agent hiện nhận đúng hợp công cụ toàn domain thay vì bị giới hạn theo một specialist card. Thay đổi này đặc biệt quan trọng với database single-agent: số `CALL_LIMIT` giảm từ 8 xuống 3 và success tăng từ 5 lên 9.
2. **Khả năng kết thúc thay đổi.** Với database, `CALL_LIMIT` giảm từ 6 xuống 3 cho JEV, 7 xuống 4 cho Drex, 6 xuống 4 cho PPLX và 4 xuống 2 cho Sol. Fixed workflow không có `CALL_LIMIT`, nhưng `PREMATURE_STOP` tăng từ 4 lên 5. Vì vậy phần lớn delta database là khác biệt về việc tạo đủ artifact và nhận biết terminal state trong budget, không chỉ là chọn role cục bộ.
3. **Executor và router live không hoàn toàn deterministic.** Cùng model và `temperature=0` không bảo đảm cùng output qua hai lượt provider. Mỗi packet đổi chỉ làm database thay đổi 8.33 điểm phần trăm và code thay đổi 5 điểm phần trăm. Code fixed mới đổi 5 packet fail→pass nhưng mất 1 packet pass→fail; code single đổi 3 packet fail→pass và 2 packet pass→fail. Đây là run-to-run variance nhìn thấy trực tiếp, không phải một mức tăng đồng đều trên toàn bank.

Code fixed còn hưởng lợi từ state `terminal` rõ ràng hơn: số quyết định giảm từ 160 xuống 136, `invalid_output` giảm 22→11 và action bị reject giảm 22→14; success tăng 10→14. Code single ít thay đổi hơn: success 12→13, gồm cả gain và loss ở các packet khác nhau. Trong bốn dynamic router code, chỉ PPLX đổi task success tổng thể sau khi thay infra retry; JEV, Drex và Sol giữ nguyên success count nhưng trajectory và phân bố STOP có thể khác.

Toàn bộ 13 physical run mới trong hai domain đều qua structural/source validation với đủ episode và không có trace error. Riêng final audit của `code-bugsinpy-fastapi-10` trong code single-agent là `UNAVAILABLE`; trajectory vẫn hợp lệ nhưng packet này không được diễn giải như một final-audit fail chắc chắn.

## Bảng Track B hiện hành trên 112 task

Bảng này gộp **primary endpoint đã công bố của từng domain**, không phải một metric
đồng nhất tuyệt đối:

- database và code debugging: `P + E`;
- formal proof: workflow success **và** independent proof audit pass;
- structured data: trusted-gold end-task pass, không yêu cầu STOP.

Do endpoint khác nhau, cột tổng phù hợp để mô tả coverage/kết quả release hiện
hành, nhưng không nên dùng như bằng chứng thống kê rằng một router vượt trội tổng
quát. Mỗi phương pháp hiện chỉ có một full run cho từng cohort.

| Phương pháp | Database / 12 | Code / 20 | Formal / 40 | Structured / 40 | Tổng primary endpoint / 112 |
|---|---:|---:|---:|---:|---:|
| Sol | 10 | 15 | 13 | 27 | **65/112 (58.04%)** |
| Drex 9B | 9 | 11 | 10 | 28 | **58/112 (51.79%)** |
| JEV | 9 | 12 | 12 | 23 | **56/112 (50.00%)** |
| PPLX Decider Flash | 8 | 14 | 13 | 20 | **55/112 (49.11%)** |
| Fixed / predefined | 7 | 14 | 11 | 29 | **61/112 (54.46%)** |

Fixed/predefined không phát action trên cùng interface với bốn dynamic router,
nên không đưa baseline này vào phân tích tương quan Track A–Track B. Single-agent
chưa có run matched cho Formal40; không tạo tổng 112 giả bằng cách ghép run formal
cũ khác bank/backbone/budget. Trên ba domain đã matched, single-agent đạt database
9/12, code 13/20 và structured 25/40; một code final audit là `UNAVAILABLE`.

## Track A V2: đã rebuild, chưa gán nhãn

Artifact hiện hành nằm tại `data/RoleRouteBench/track_a_4d_multirouter_v2` và đã
qua `validation_report.json` với `valid = true`:

| Thành phần | Số lượng |
|---|---:|
| Source episode từ bốn dynamic router | 448 |
| Packet snapshot | 112 |
| Raw decision occurrence | 3,997 |
| Canonical primary candidate | 3,174 |
| Canonical audit-only state | 180 |
| State được chọn cho Track A V2 | 997 |

Phân bố state được chọn là code 250, database 247, formal 250 và structured 250;
theo origin-router stratum là PPLX 265, JEV 241, Sol 246 và Drex 245. Labeling
folder mới chỉ có `sample_manifest.json` và `sample_states.jsonl`; chưa có
`llm_prelabels.jsonl`, vì vậy trạng thái chính thức là **built / validated /
unlabeled**. Candidate router và labeler chỉ nhận router-visible state; behavior
action, dispatch status, executor trace, episode result và runtime snapshot được
giữ ở audit-only records.

## Bảng kết quả chính (snapshot lịch sử ngày 2026-11-09)

| Router | Track A đúng / 568 | Track A accuracy | P: pass + STOP | E: end-task pass, không STOP | Track B success / N hợp lệ | Track B accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Sol | 534 | 94.01% | 52 | 0 | 52/82 | **63.41%** |
| JEV | 486 | 85.56% | 44 | 1 | 45/79 | **56.96%** |
| Drex 9B | 405 | 71.30% | 33 | 13 | 46/82 | **56.10%** |
| PPLX Decider Flash | 502 | 88.38% | 43 | 2 | 45/82 | **54.88%** |

## Chi tiết Track B theo domain (snapshot lịch sử ngày 2026-11-09)

Mỗi ô có dạng `P + E = success / N (accuracy)`.

| Router | Database (12) | Code debugging (20) | Formal proof (30) | Structured data (20) |
|---|---:|---:|---:|---:|
| Sol | 8 + 0 = 8/12 (66.67%) | 15 + 0 = 15/20 (75.00%) | 26 + 0 = 26/30 (86.67%) | 3 + 0 = 3/20 (15.00%) |
| JEV | 6 + 1 = 7/12 (58.33%) | 12 + 0 = 12/20 (60.00%) | 24 + 0 = 24/27 (88.89%) | 2 + 0 = 2/20 (10.00%) |
| Drex 9B | 5 + 1 = 6/12 (50.00%) | 1 + 10 = 11/20 (55.00%) | 25 + 1 = 26/30 (86.67%) | 2 + 1 = 3/20 (15.00%) |
| PPLX Decider Flash | 4 + 1 = 5/12 (41.67%) | 11 + 0 = 11/20 (55.00%) | 25 + 1 = 26/30 (86.67%) | 3 + 0 = 3/20 (15.00%) |

## Khác biệt giữa các router trong snapshot lịch sử

### Sol

Sol đứng đầu ở cả Track A và Track B. Toàn bộ 52 success của Sol đều là pass có STOP; không có success phải được cứu bởi end-task audit. Sol đạt kết quả tốt nhất ở database và code debugging, đồng hạng cao nhất ở formal proof. Điểm yếu chung vẫn là structured data processing, chỉ 3/20.

Terminal distribution của Sol là 52 `STOP`, 30 `CALL_LIMIT`, không có `PREMATURE_STOP`. Điều này cho thấy Sol có hành vi kết thúc chính xác hơn ba router còn lại trên tập run này.

### JEV

Sau khi loại ba episode formal lỗi hạ tầng, JEV có 44 pass có STOP và chỉ một task đạt đích mà không STOP. Kết quả này phản ánh termination tương đối tốt, nhưng số episode hợp lệ chạm `CALL_LIMIT` vẫn cao: 35/79. JEV tốt hơn PPLX ở database và code, cao nhất ở formal proof sau infrastructure exclusion, nhưng thấp nhất ở structured data.

### Drex 9B

Drex có Track A thấp nhất nhưng Track B vẫn gần JEV: Drex có nhiều hơn một success thô (46 so với 45), nhưng accuracy thấp hơn vì JEV đã loại ba episode lỗi hạ tầng khỏi mẫu số. Lý do chính là metric E: 13/46 success của Drex đã đạt task contract nhưng router không STOP. Riêng code debugging, Drex chỉ có 1 pass có STOP nhưng có thêm 10 end-task pass không STOP.

Terminal distribution của Drex là 33 `STOP` và 49 `CALL_LIMIT`. Vì vậy Drex không hẳn yếu ở việc đưa executor tới lời giải; điểm yếu rõ nhất là nhận biết thời điểm hoàn tất và kết thúc trajectory.

### PPLX Decider Flash

PPLX có Track A cao thứ hai nhưng Track B thấp nhất, dù chênh lệch với JEV/Drex chỉ một packet. Router này chọn STOP nhiều nhất: 67/82 episode, nhưng chỉ 43 episode trở thành pass có STOP; 24 episode kết thúc bằng `PREMATURE_STOP`.

PPLX vì thế thể hiện xu hướng ngược Drex: Drex thường không STOP khi task đã đạt, còn PPLX thường STOP trước khi terminal contract sẵn sàng. Đây là nguyên nhân chính khiến accuracy Track A khá cao nhưng không chuyển thành kết quả Track B tương ứng.

## Tương quan Track A V1 và Track B trong snapshot lịch sử

Ở mức bốn router, tương quan chỉ mang tính thăm dò vì `n = 4`:

- Pearson giữa Track A accuracy và Track B accuracy: **0.575**.
- Spearman: **0.400**.
- Nếu xem 16 điểm router × domain, Pearson chỉ còn **0.292**, Spearman **0.281**.

Không nên xem Track A là proxy trực tiếp cho Track B:

1. Track A chấm một quyết định độc lập trên state đã ghi lại, theo membership trong tập `valid_actions` do Terra gán nhãn. Nó đo chất lượng chọn next action trong điều kiện state cố định.
2. Track B là closed-loop. Quyết định hiện tại làm thay đổi state tiếp theo, đồng thời kết quả còn phụ thuộc executor, tool outcome, recovery, ngân sách và quyết định STOP.
3. State Track A được lấy từ trajectory của JEV, nên không bao phủ hoàn toàn state distribution do các router khác tự tạo ra trong Track B.
4. Structured data cho thấy khoảng cách rõ nhất: Track A đạt 51.28–98.72%, nhưng Track B chỉ đạt 10–15%. Chọn role hợp lệ tại từng state chưa đủ để bảo đảm executor tạo đúng artifact cuối.
5. Formal proof gần ceiling ở Track B (86.67–88.89% sau khi loại lỗi hạ tầng của JEV) vì cùng dùng executor 32B mạnh. Domain này hiện phân biệt router kém hơn code và database.

Kết luận: Track A vẫn hữu ích để đo chất lượng decision model ở cấp quyết định, còn Track B đo hiệu quả điều phối end-to-end. Hai track bổ sung cho nhau; không nên dùng accuracy Track A để dự đoán trực tiếp task success Track B.

## Nguồn kết quả

- Track A V2 build: `data/RoleRouteBench/track_a_4d_multirouter_v2/build_manifest.json`
  và `validation_report.json`; chưa có file prelabel.
- Track A V1 lịch sử: `report/roleroutebench_track_a_{router}_vs_terra.json`.
- Database và code hiện hành: `runs/database/collection_manifest.json`,
  `runs/code_debugging/collection_manifest.json` và `evaluation_report.json`
  trong các run được chọn.
- Formal hiện hành: `report/formal40_final_results.json` và
  `runs/formal_proof/official_run_manifest.json`.
- Structured hiện hành: `report/structured40_final_results.json` và
  `runs/structured_data/collection_manifest.json`.
- Parquet JEV trong `hf_release/RoutingBench-V4` chỉ là nguồn của snapshot lịch sử
  ngày 2026-11-09, không phải Structured40 hiện hành.
