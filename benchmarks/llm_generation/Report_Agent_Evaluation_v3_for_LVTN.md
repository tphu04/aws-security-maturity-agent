## 6.6.3 Report Agent Evaluation

Report Agent là thành phần cuối trong pipeline, chịu trách nhiệm tổng hợp kết quả từ các agent trước và sinh báo cáo hoàn chỉnh dưới dạng HTML. Khác với Planning Agent và Risk Evaluation Agent, đầu ra của Report Agent không phải là một quyết định đơn lẻ mà là một tài liệu kết hợp giữa phần template (deterministic rendering) và nhiều đoạn narrative do mô hình ngôn ngữ sinh ra. Đặc thù này làm cho bài toán đánh giá phức tạp hơn: một báo cáo có thể có cấu trúc đúng, số liệu đúng, nhưng phần tường thuật vẫn chứa các phát biểu không được hỗ trợ bởi dữ liệu đầu vào. Do đó, khung đánh giá cần phân tách rõ các nguồn sai lệch và kết hợp cả phương pháp định lượng lẫn LLM-as-a-judge để bao phủ được các khía cạnh không thể biểu diễn bằng quy tắc cứng.

Thí nghiệm được thực hiện trên 30 test cases chia thành 5 nhóm theo năng lực (capability-based grouping) thay vì theo dịch vụ AWS, với mô hình sinh nội dung là gemma3:4b chạy cục bộ qua Ollama và LLM-as-a-judge là gemini-flash-latest (2 samples mỗi lời gọi, temperature 0.3). Khung đánh giá được tổ chức theo 5 trục — Scope, Structure, Faithfulness, Correctness, Quality — tổng cộng 9 chỉ số, trong đó 7 chỉ số deterministic dùng lại module `ReportValidator` của production để tránh silent drift và 2 chỉ số LLM-judge.

### Evaluation Metrics

**Scope Fidelity.** Hai chỉ số được sử dụng nhằm xác định báo cáo có nhắc đúng chủ thể hay không. *scope_accuracy* đo tỷ lệ trường hợp module scope detector nhận diện đúng primary service và service list; *off_scope_mention_rate* đo tỷ lệ section LLM nhắc đến dịch vụ nằm ngoài phạm vi scan. Đây là hai chỉ số quan trọng nhất vì nếu báo cáo nhắc sai chủ thể, các chỉ số khác đều không còn ý nghĩa.

**Structure.** *structure_pass_rate* tổng hợp bốn điều kiện cứng: HTML hợp lệ, đủ section bắt buộc, không có template leak, và không có giá trị `None` hiển thị.

**Faithfulness.** Ba chỉ số bổ sung nhau đo mức độ bám sát nguồn. *numerical_faithfulness* tách các số trong narrative và đối chiếu với tập allowed_numbers dẫn xuất từ findings và pre/post stats. *capability_grounding_rate* được định nghĩa là 1 − (số capability candidate bị flag ungrounded)/(tổng số capability candidate), đo precision của các phát biểu về năng lực bảo mật. *claim_support_rate* là chỉ số LLM-judge theo phong cách RAGAS: judge decompose narrative thành 3–8 claim rồi gán nhãn supported/partial/unsupported so với context, score cuối là (supported + 0.5 × partial)/total.

**Correctness.** *template_data_accuracy* là trung bình cộng bốn chỉ số con (stats, findings table, score, status color), phản ánh độ chính xác của phần template. *ndcg_at_5_severity* đo thứ tự ưu tiên: thứ tự mention finding trong narrative được so với severity desc ideal, chỉ áp dụng cho các trường hợp có finding đa severity.

**Quality.** *actionability_likert* là chỉ số LLM-judge theo phong cách G-Eval với thang Likert 1–5, được cung cấp rubric cụ thể (5 = có lệnh CLI kèm resource được đặt tên, 1 = platitude không thể thực thi) và yêu cầu suy luận Chain-of-Thought trước khi gán điểm.

Năm chỉ số được xếp là HARD (gate release): structure_pass_rate ≥ 1.00, off_scope_mention_rate ≤ 0.02, scope_accuracy ≥ 1.00, numerical_faithfulness ≥ 0.90, template_data_accuracy ≥ 1.00. Bốn chỉ số SOFT còn lại được dùng để phân tích chất lượng và đánh giá đóng góp của RAG, không làm điều kiện gate.

**Ablation design.** Mỗi test case được chạy dưới hai điều kiện: *no_rag* (RAG bundle rỗng) và *with_rag_v2* (bundle đầy đủ theo thiết kế Phase 3, gồm `capability_details` với các trường recommendation và risk_explanation). Các trường khác giữ nguyên giữa hai điều kiện, đảm bảo chênh lệch quan sát được chỉ phản ánh ảnh hưởng của RAG.

### Results and Analysis

Trước tiên, toàn bộ năm điều kiện HARD đều được thoả mãn: báo cáo luôn có cấu trúc hợp lệ, nhận diện đúng scope, không nhắc đến dịch vụ ngoài phạm vi, template_data_accuracy đạt mức tối đa, và numerical_faithfulness đạt 0.9750 — vượt ngưỡng 0.90. Vì các chỉ số trên đã gần mức bão hoà, phần phân tích tiếp theo tập trung vào bốn chỉ số SOFT có tín hiệu phân biệt (capability_grounding_rate, claim_support_rate, ndcg_at_5_severity, actionability_likert), là các chỉ số mang thông tin về chất lượng nội dung sinh ra và vai trò của RAG.

Bảng 6.16 trình bày hiệu năng của các chỉ số SOFT dưới điều kiện with_rag_v2.

**Bảng 6.16:** Hiệu năng của Report Agent trên các chỉ số chất lượng

| Metric | Value |
|--------|-------|
| capability_grounding_rate | 1.00 |
| ndcg_at_5_severity | 0.922 |
| claim_support_rate | 0.794 |
| actionability_likert | 3.00 / 5 |

Kết quả cho thấy hai chỉ số đo mức độ bám sát RAG (capability_grounding, claim_support) cho kết quả trái chiều: nhóm deterministic đạt mức rất cao nhờ cơ chế validator, trong khi LLM-judge phát hiện được phần sai lệch mà validator bỏ qua. Khoảng cách 0.20 giữa hai chỉ số này chính là vùng sai lệch dạng narrative định tính — các phát biểu về rủi ro, hệ quả, hoặc ngữ cảnh mà mô hình sinh bổ sung không có trong evidence. Đây là loại hallucination mà quy tắc cứng không thể phát hiện, nhấn mạnh vai trò của LLM-as-a-judge trong khung đánh giá. Chỉ số actionability ở mức 3.00/5 cho thấy recommendation đạt được định hướng đúng và nhắc đến các control được đặt tên cụ thể, nhưng chưa đến mức có lệnh CLI hoặc tham số tài nguyên chi tiết.

**Phân tích theo nhóm năng lực.** Bảng 6.17 trình bày kết quả theo năm nhóm test case, mỗi nhóm tập trung vào một năng lực cụ thể.

**Bảng 6.17:** Hiệu năng theo nhóm năng lực (chỉ số SOFT)

| Group | n | num_faith | cap_grnd | claim_sup | ndcg | action |
|-------|---|-----------|----------|-----------|------|--------|
| C1 Scope Detection | 5 | 1.00 | 1.00 | 0.83 | — | 3.00 |
| C2 Hallucination Stress | 5 | 0.92 | 1.00 | 0.66 | — | 3.00 |
| C3 Prioritization | 4 | 1.00 | 1.00 | 0.84 | 0.922 | 3.00 |
| C4 Structural Robustness | 5 | 0.96 | 1.00 | 0.78 | — | 3.00 |
| C5 RAG Grounding | 5 | 1.00 | 1.00 | 0.84 | — | 3.00 |

Nhóm C2 cho kết quả thấp nhất về claim_support_rate (0.66). Đây là tín hiệu kỳ vọng và phản ánh đúng mục tiêu thiết kế: các trường hợp trong C2 được xây dựng để đưa agent vào tình huống dữ liệu nghèo (một finding duy nhất, không có FAIL, hoặc RAG bundle thưa). Khi dữ liệu không đủ để viết đầy các section, mô hình có xu hướng bù bằng các phát biểu định tính nghe hợp lý nhưng không có evidence hỗ trợ. Đáng chú ý, trong cùng nhóm C2, numerical_faithfulness vẫn giữ ở mức 0.92, cho thấy validator gate chặn được hallucination về số, nhưng không chặn được hallucination về narrative định tính — quan sát này củng cố lý do phải kết hợp cả hai loại phương pháp đánh giá.

Nhóm C3 đạt ndcg_at_5_severity ở mức 0.922 ngay cả trên các trường hợp khó như `inverted_description_trap` (Critical có description ngắn, Low có description dài) và `findings_100plus_top5` (danh sách lớn hơn 100 findings). Điều này gợi ý rằng năng lực prioritization phần lớn được quyết định bởi prior của mô hình về từ khoá severity, không phụ thuộc nhiều vào RAG.

Cần lưu ý rằng capability_grounding_rate đạt mức tối đa trên nhóm C5 (các trường hợp adversarial với RAG có nhiễu) không có nghĩa khung đánh giá phát hiện được mọi dạng lỗi RAG: validator check capability candidate so với tập allowed_capabilities của RAG, do đó nếu retriever đưa capability nhiễu vào allowed set, validator vẫn cho qua. Khung đánh giá này bảo vệ trước hallucination của mô hình sinh, chất lượng của retriever là vấn đề độc lập đánh giá ở tầng RAG Retrieval (Mục 6.5).

**Ảnh hưởng của RAG.** Bảng 6.18 so sánh trung bình các chỉ số SOFT dưới hai điều kiện no_rag và with_rag_v2.

**Bảng 6.18:** So sánh các cấu hình của Report Agent

| Metric | no_rag | with_rag_v2 | Δ |
|--------|--------|-------------|----|
| capability_grounding_rate | 0.933 | 1.00 | +0.067 |
| ndcg_at_5_severity | 0.921 | 0.922 | +0.001 |
| claim_support_rate | 0.786 | 0.794 | +0.008 |
| actionability_likert | 2.84 | 3.00 | +0.159 |

Các chỉ số HARD không thay đổi giữa hai điều kiện (tất cả Δ = 0), trong khi các chỉ số liên quan đến nội dung tường thuật đều tăng khi có RAG và không có chỉ số nào giảm. Pattern này cho thấy khung đánh giá đang phản ánh đúng thiết kế hệ thống: các chỉ số được quyết định bởi tầng template và validator không chịu ảnh hưởng của RAG, các chỉ số về narrative chịu ảnh hưởng tích cực từ RAG. Đây là tín hiệu của một khung đánh giá có tính phân biệt: nếu tất cả chỉ số thay đổi hoặc không thay đổi đồng loạt, không thể tách được đóng góp của RAG khỏi đóng góp của các thành phần khác.

Tuy nhiên, magnitude của Δ nhỏ hơn đáng kể so với kỳ vọng ban đầu. Nguyên nhân không phải RAG không có tác dụng, mà phản ánh việc baseline no_rag đã ở mức cao do hai yếu tố: validator gate chặn trước phần lớn capability ungrounded ngay cả khi không có RAG (đẩy baseline capability_grounding lên 0.933), và gemma3:4b có prior mạnh về từ vựng remediation AWS thu được trong pre-training (đẩy baseline actionability lên 2.84). Điều này gợi ý rằng trong hệ thống hiện tại, RAG đóng vai trò của lớp tinh chỉnh cuối cùng chứ không phải lớp cung cấp nội dung cốt lõi.

Quan sát đáng chú ý là cả hai chỉ số LLM-judge chưa đạt ngưỡng đều có Δ dương khi thêm RAG. Điều này gợi ý rằng hạn chế về claim_support_rate và actionability_likert không đến từ pipeline (vì pipeline đang đẩy chỉ số đi đúng chiều khi có RAG) mà đến từ trần năng lực của mô hình sinh — một mô hình 4B tham số gặp khó khăn khi phải đồng thời neo từng phát biểu vào evidence và sinh recommendation có lệnh CLI cụ thể. Do đó, hướng cải thiện tự nhiên không nằm ở tầng pipeline mà ở việc nâng cấp backbone sinh nội dung sang lớp 7B–8B tham số.

**Ví dụ so sánh chất lượng nội dung.** Vì các Δ định lượng phản ánh trung bình trên toàn bộ dataset, chúng chưa thể hiện hết sự khác biệt về chất lượng tường thuật giữa hai điều kiện. Phần này trình bày ba ví dụ cụ thể được trích trực tiếp từ HTML artifact của cùng test case dưới hai cấu hình, nhằm minh hoạ tính chất của đóng góp RAG mà các chỉ số tổng hợp khó phản ánh.

*Ví dụ 1 (case `c1_single_iam_dominant`, fixture IAM).* Đây là trường hợp regression test cho bias S3 của phiên bản trước. Dưới điều kiện không có RAG, phần Tóm tắt điều hành thu gọn thành một câu duy nhất do mô hình không có context để mở rộng:

> **no_rag:** "Đánh giá bảo mật AWS IAM đã hoàn tất với 6 findings (2 PASS, 4 FAIL). Chi tiết xem phần bên dưới."

Trong khi đó, với RAG bundle đầy đủ, cùng section này liệt kê chi tiết các tài nguyên và findings theo mức severity:

> **with_rag_v2:** "Phạm vi đánh giá bao gồm 3 IAM entities: user/alice, user/bob và user/carol. [...] Các nhóm rủi ro chính bao gồm: (CRITICAL) Root account MFA is disabled (scope: account-level). (HIGH) IAM user alice does not have MFA enabled (IAM entity: arn:aws:iam::123456789012:user/alice). [...] (MEDIUM) Password policy does not meet strength requirements."

Sự khác biệt ở đây không chỉ về độ dài mà ở mức độ grounded: báo cáo with_rag tham chiếu trực tiếp các tên tài nguyên (alice, bob, carol) và phân loại theo severity, trong khi no_rag không đủ context để tổ chức nội dung. Điều này cho thấy RAG không chỉ cung cấp thêm thông tin, mà còn tạo được khung để mô hình tổ chức lại dữ liệu có sẵn trong findings.

*Ví dụ 2 (case `c2_minimal_1_finding`, stress test dữ liệu nghèo).* Trường hợp chỉ có một finding duy nhất được thiết kế để đẩy mô hình vào tình huống phải "lấp đầy" các section với dữ liệu hạn chế. Phần Khuyến nghị dưới điều kiện no_rag thể hiện rõ hiện tượng này:

> **no_rag:** "Thực hiện đánh giá nguyên nhân gốc rễ cho các auto-fix thất bại. Mặc dù không có auto-fix nào thất bại, việc không có auto-fix nào thất bại là một dấu hiệu tích cực. Tuy nhiên, cần tiến hành điều tra nguyên nhân gốc rễ cho việc không có auto-fix nào được kích hoạt."

Đoạn văn trên tự mâu thuẫn logic (không có auto-fix thất bại nhưng đề xuất điều tra nguyên nhân auto-fix thất bại), là dạng sai lệch mà chỉ số deterministic không thể phát hiện: số liệu đúng (0 auto-fix fail), scope đúng (IAM), nhưng logic suy luận bị sai. Dưới điều kiện with_rag, mô hình bám vào tên capability cụ thể từ bundle:

> **with_rag_v2:** "[Cần] áp dụng baseline Identity And Access Management (IAM) trên tất cả các tài nguyên. [...] Tăng cường Bảo mật Xác thực: cần thực thi các biện pháp bảo mật xác thực mạnh mẽ, bao gồm yêu cầu xác thực đa yếu tố (MFA), áp dụng chính sách mật khẩu mạnh và thường xuyên xoay vòng các khóa."

Ví dụ này làm rõ vai trò của LLM-judge trong khung đánh giá: hallucination dạng "sai logic khi thiếu data" không thể bắt bằng rule, buộc phải dùng judge. Điều này cũng phản ánh trong chỉ số claim_support_rate của nhóm C2 (0.66) — giá trị thấp nhất trong toàn bộ dataset.

*Ví dụ 3 (case `c5_rich_rag_full_capdetails`, RAG rich).* Trên trường hợp có bundle RAG đầy đủ nhất, sự khác biệt tập trung ở mức độ chi tiết của kế hoạch hành động. Với điều kiện no_rag, recommendation dừng ở định hướng tổng quan:

> **no_rag:** "Thực hiện đánh giá rủi ro định kỳ và giám sát. Cần thiết lập một chương trình giám sát và rà soát định kỳ các cấu hình AWS để phát hiện các thay đổi không mong muốn."

Với điều kiện with_rag_v2, cùng nội dung được bổ sung cadence cụ thể và cấu trúc theo giai đoạn:

> **with_rag_v2:** "Giám sát và Rà soát Định kỳ: re-scan hàng tuần/tháng, tích hợp cảnh báo cho các finding mới phát sinh. [...] 7.2 Kế hoạch Hành động Tiếp theo: (1) NGAY (trong 1 tuần): Ưu tiên xử lý các findings có mức độ nghiêm trọng CRITICAL và HIGH chưa được khắc phục. (2) NGẮN HẠN (trong 1 tháng): Các findings có mức độ nghiêm trọng MEDIUM và LOW sẽ được ưu tiên khắc phục."

Đây là đóng góp mà chỉ số actionability_likert đang đo (Δ = +0.16): khả năng chuyển từ "định hướng đúng" (Likert 3) sang "có bước thực thi đo được" (Likert 4+). Magnitude của Δ nhỏ vì gemma3:4b ở mức 4B tham số vẫn chưa sinh được lệnh CLI cụ thể ngay cả khi có RAG; nhưng ở cấp độ nội dung, khác biệt giữa "giám sát định kỳ" và "re-scan hàng tuần, có cảnh báo tự động" là rõ ràng và có ý nghĩa vận hành.

Tổng hợp ba ví dụ trên cho thấy ảnh hưởng của RAG lên chất lượng nội dung báo cáo có ba dạng khác biệt: mức độ grounded (Ví dụ 1 — tham chiếu tên tài nguyên cụ thể), tính nhất quán logic trong dữ liệu nghèo (Ví dụ 2 — tránh các phát biểu tự mâu thuẫn), và tính thực thi được của khuyến nghị (Ví dụ 3 — cadence và phân giai đoạn cụ thể). Các khác biệt này là bằng chứng định tính bổ sung cho các Δ định lượng trong Bảng 6.18, củng cố kết luận rằng RAG đóng vai trò của lớp tinh chỉnh nội dung thay vì lớp cung cấp thông tin cốt lõi.

### Tóm tắt

Report Agent đáp ứng đầy đủ năm điều kiện HARD của khung đánh giá, chứng minh rằng các cải tiến ở Phase 1–5 đã giải quyết được các sai lệch cốt lõi về cấu trúc, phạm vi dịch vụ, và tính chính xác của số liệu. Hai chỉ số SOFT dựa trên LLM-judge chưa đạt ngưỡng phản ánh trần năng lực của mô hình sinh ở kích thước 4B, không phải hạn chế của pipeline — kết luận này được củng cố bởi việc ablation cho thấy RAG đóng góp theo đúng chiều kỳ vọng trên đúng các chỉ số nó được thiết kế để ảnh hưởng. Kết quả này đồng thời cho thấy giá trị thực tế của việc thiết kế khung đánh giá theo hướng phân tách: khung đánh giá đủ phân biệt để tách được đóng góp của RAG, vai trò của template, và giới hạn của mô hình sinh.
