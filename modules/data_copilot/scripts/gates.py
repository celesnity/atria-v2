"""Deterministic semantic gates (Dimension 2) + LLM syntax inspector (Dimension 1).

Ported verbatim (minus the RIMRULE memory bank) from
.reference/data-agent/triadic_dgm/agent/verifier.py. verify_semantics runs the
~12 hard business gates in reference order; the first failure returns REVISE.
Gate feedback strings are copied verbatim (Vietnamese) for output parity.
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

import persona_schema  # type: ignore[import-not-found]
import verdict as _verdict  # type: ignore[import-not-found]

# Keywords that trigger full semantic verification (Semantic Routing).
# Copied verbatim from .reference/data-agent/triadic_dgm/agent/verifier.py.
BUSINESS_KEYWORDS = [
    "clustering",
    "cluster",
    "persona",
    "phân cụm",
    "gom cụm",
    "churn",
    "hidden pattern",
    "phân tích persona",
    "segment",
    "nhóm khách",
    "k-means",
    "kmeans",
    "decision tree",
    "retention",
    "phân tích khách hàng",
    "customer analysis",
    "segmentation",
]

# NO CAUSAL HALLUCINATION forbidden terms — copied verbatim from the reference.
_CAUSAL_TERMS = [
    "khuyến mãi",
    "promotion",
    "đối thủ",
    "cạnh tranh",
    "thương hiệu",
    "marketing",
    "chính sách giá",
    "ưu đãi giá",
    "price-sensitive",
    "nhạy cảm giá",
]


def is_business_task(user_query: str) -> bool:
    """Semantic Router: only enable Dimension 2 for deep business tasks.

    Saves API cost for simple utility commands.

    Args:
        user_query: The raw task/user query string.

    Returns:
        True if the query matches any business keyword.
    """
    query_lower = user_query.lower()
    return any(kw in query_lower for kw in BUSINESS_KEYWORDS)


def verify_syntax(
    code: str, error_log: str, task: str, chat_fn: Callable[[List[dict]], str]
) -> str:
    """Catch Traceback errors and produce a generalized fix instruction.

    Args:
        code: The faulty code that raised the error.
        error_log: The captured execution error/traceback.
        task: The original task description.
        chat_fn: Callable that sends chat messages and returns the reply text.

    Returns:
        A fix instruction string for the Programmer.
    """
    system_prompt = (
        "You are a strict QA Engineer and Code Reviewer. "
        "Analyze the faulty code and the execution error log based on the original task. "
        "Provide a concise, actionable instruction on how to fix the error. "
        "CRITICAL: Your fix instructions must be generalizable. "
        "Do NOT hardcode variable names or line numbers. "
        "Do NOT write the code yourself, just give the logical steps to avoid the error."
    )

    user_prompt = (
        f"Original Task:\n{task}\n\n"
        f"Code:\n```python\n{code}\n```\n\n"
        f"Error Log:\n{error_log}\n\n"
        "Please analyze and provide generalized fix instructions."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        feedback = chat_fn(messages)
    except Exception as e:  # noqa: BLE001
        feedback = f"Try using alternative approach or package. Error: {e}"

    return feedback


def verify_semantics(
    task: str, code: str, exec_output: str, *, domain: Optional[str] = None
) -> dict:
    """Validate the business-logic semantics of code execution output.

    Runs the ~12 hard business gates (Regex-based) in reference order; the
    first failing gate returns a REVISE verdict immediately. If the task is
    not a business task, short-circuits to ACCEPT without running any gate.

    Args:
        task: The original task description.
        code: The generated code that was executed.
        exec_output: Captured stdout of the code execution.
        domain: Optional domain hint (unused by the ported gates themselves,
            kept for interface compatibility with callers).

    Returns:
        A verdict dict built via verdict.new_verdict.
    """
    if not is_business_task(task):
        return _verdict.new_verdict(_verdict.ACCEPT)

    personas = persona_schema.extract_personas(exec_output) or []

    verdict = {
        "status": "ACCEPT",
        "missing": [],
        "feedback": "",
        "epiplexity_score": 0.0,
    }

    # Rule 1: Silhouette < 0.2
    sil_matches = re.findall(r"(?i)silhouette.*?([0-9]*\.[0-9]+)", exec_output)
    if sil_matches:
        try:
            sil_score = float(sil_matches[-1])
            if sil_score < 0.2:
                verdict["status"] = "REVISE"
                verdict["feedback"] = (
                    f"⚠ Persona quality too low. Silhouette {sil_score} < 0.2. "
                    "Không đủ bằng chứng thống kê để tạo persona đáng tin cậy. "
                    "Dừng việc tạo Persona giả."
                )
        except ValueError:
            pass

    # Rule 2: Target Leakage Check
    if "RMDT" in code and ("KMeans" in code or "clustering" in code or "TfidfVectorizer" in code):
        if re.search(r"(?i)(features|cols|columns)\s*=\s*\[[^\]]*'RMDT'[^\]]*\]", code) or (
            re.search(r"KMeans", code)
            and not re.search(r"drop\([^\)]*RMDT", code)
            and not re.search(r"features\s*=", code)
        ):
            verdict["status"] = "REVISE"
            verdict["feedback"] = (
                "⚠ Data Leakage: Biến mục tiêu `RMDT` đang được dùng làm feature "
                "cho thuật toán phân cụm. BẮT BUỘC phải drop `RMDT` khỏi tập dữ "
                "liệu huấn luyện KMeans!"
            )

    # Rule 2.5: Geography Dominance Check
    if "khu_vuc" in code and "KMeans" in code:
        if re.search(
            r"(?i)(feature_cols|cols_for_clustering|behavior_cols|cat_cols_to_use)"
            r"\s*=[^\]\n]*'khu_vuc'",
            code,
        ):
            verdict["status"] = "REVISE"
            verdict["feedback"] = (
                "⚠ Geography Dominance: KHÔNG được dùng `khu_vuc`, `goi_cuoc` hoặc "
                "`ma_su_co_pho_bien` làm input features cho KMeans. Điều này khiến "
                "cụm bị chia hoàn toàn theo địa lý. CHỈ dùng các biến hành vi (rớt "
                "mạng, CSKH, suy hao, thang_su_dung) và text TF-IDF để train KMeans!"
            )

    # Rule 3 & 4 & 5 & 6: JSON Validation & Support & Scale & Unique
    if "KMeans" in code or "TfidfVectorizer" in code:
        # Personas are extracted once via persona_schema.extract_personas above
        # (adaptation over the reference's ad-hoc re.search/json.loads here).
        json_candidates = [personas] if personas else []

        has_valid_json = False
        for data_arr in json_candidates:
            if not (
                isinstance(data_arr, list) and len(data_arr) > 0 and "persona_name" in data_arr[0]
            ):
                continue
            has_valid_json = True

            # Business Diversity K-Score
            k_scores = {}
            for m in re.finditer(r"K=(\d+).*?Silhouette=([0-9.]+)", exec_output, re.IGNORECASE):
                k_scores[int(m.group(1))] = float(m.group(2))

            total_support = sum(c.get("support", 0) for c in data_arr)

            if len(data_arr) < 3:
                verdict["status"] = "REVISE"
                verdict["feedback"] = (
                    "⚠ Lỗi nghiệp vụ (Business Logic Error): Số lượng cụm (K) phải >= 3."
                )

            if total_support > 0:
                overall_churn = (
                    sum(c.get("churn_rate", 0) * c.get("support", 0) for c in data_arr)
                    / total_support
                )
            else:
                overall_churn = 0.0  # noqa: F841 -- unused in reference too; kept verbatim

            churn_rates = [  # noqa: F841 -- unused in reference too; kept verbatim
                c.get("churn_rate", 0) for c in data_arr
            ]
            # Bỏ check churn_rate < 0.001 vì dataset này churn_rate = 0 (hardcoded 1.0 mode)

            persona_names = []
            for cluster in data_arr:
                pct = cluster.get("support_pct", 1.0)
                arpu = cluster.get("arpu", 0)
                churn = cluster.get("churn_rate", 0)
                p_name = cluster.get("persona_name", "")
                # noqa: F841 -- both unused in reference too; kept verbatim
                sample_text = cluster.get("sample_persona_text", "").lower()  # noqa: F841
                p_name_lower = p_name.lower()  # noqa: F841

                # RULE_PERSONA_NAME Numeric & Hallucination Check
                if (
                    re.match(r"^(cluster_)?\d+$", p_name, re.IGNORECASE)
                    or len(p_name) < 5
                    or "0.0" in p_name
                ):
                    verdict["status"] = "REVISE"
                    verdict["feedback"] = (
                        f"⚠ Lỗi nghiệp vụ: Tên Persona '{p_name}' quá ngắn hoặc là số. "
                        "Bạn PHẢI đặt tên có Semantic Meaning dựa trên hành vi."
                    )

                if pct > 1.0 or churn > 1.0:
                    verdict["status"] = "REVISE"
                    verdict["feedback"] = (
                        "⚠ Lỗi định dạng: support_pct và churn_rate phải là tỷ lệ trong "
                        "khoảng [0.0, 1.0]."
                    )

                if arpu > 0 and arpu < 50000:
                    verdict["status"] = "REVISE"
                    verdict["feedback"] = (
                        f"⚠ Lỗi Kế Toán: ARPU của cụm '{p_name}' quá thấp "
                        f"({arpu} VND < 50,000 VND)."
                    )

                persona_names.append(p_name)

            # Duplicate Name Check
            cleaned_names = [
                re.sub(r"\(Cụm \d+\)", "", name, flags=re.IGNORECASE).strip().lower()
                for name in persona_names
            ]
            if len(set(cleaned_names)) < len(cleaned_names):
                verdict["status"] = "REVISE"
                verdict["feedback"] = (
                    "⚠ Lỗi nghiệp vụ (Duplicate Personas): Mỗi cụm BẮT BUỘC phải có tên "
                    "DUY NHẤT chứa Feature phân biệt."
                )

            if any("(cụm" in n.lower() for n in persona_names):
                verdict["status"] = "REVISE"
                verdict["feedback"] = (
                    "⚠ Lỗi nghiệp vụ (Cụm Naming): TUYỆT ĐỐI KHÔNG ĐƯỢC đặt tên Persona "
                    "có chứa chữ '(Cụm X)'."
                )

            # Gate: Silhouette Inflation Warning (when micro-clusters exist)
            min_support_pct = min(float(p.get("support_pct", 1.0)) for p in data_arr)
            if min_support_pct < 0.01:
                sil_matches = re.findall(r"(?i)silhouette.*?([0-9]*\.[0-9]+)", exec_output)
                if sil_matches:
                    try:
                        sil_score = float(sil_matches[-1])
                        if sil_score > 0.5:
                            # Add warning to sample_persona_text of the anomaly cluster
                            # (don't REVISE, just flag). We embed this in the feedback
                            # as INFO, not REVISE.
                            verdict.setdefault("warnings", []).append(
                                f"⚠ Silhouette Inflation Warning: Score={sil_score:.4f} "
                                "có thể bị thổi phồng bởi anomaly cluster "
                                f"({min_support_pct*100:.2f}% data). Silhouette cao "
                                "nhưng không phản ánh chất lượng phân cụm thực sự."
                            )
                    except ValueError:
                        pass

            break

        if not has_valid_json and verdict.get("status") != "REVISE":
            verdict["status"] = "REVISE"
            verdict["feedback"] = (
                "⚠ Không tìm thấy JSON Output hợp lệ cho Persona. BẮT BUỘC phải dùng "
                "lệnh print('[JSON_START_PERSONA]'), sau đó print(json.dumps(personas)), "
                "và cuối cùng print('[JSON_END_PERSONA]')."
            )

    # Rule 8: Hidden Pattern Actionable Logic (Decision Tree) & Hallucination Check
    if "CHURN PREDICTION RULES:" in exec_output:
        tree_text = exec_output.split("CHURN PREDICTION RULES:")[1].lower()
        if "class: 0" in tree_text and "class: 1" not in tree_text:
            verdict["status"] = "REVISE"
            verdict["feedback"] = (
                "⚠ Actionable Pattern Validator: Decision Tree không tìm được pattern "
                "nào cho class: 1 (Churn). Thuật toán đã thất bại trong việc phân loại "
                "rời mạng. YÊU CẦU: Không được bịa đặt insights từ cây quyết định "
                "rỗng này!"
            )

        allowed_concepts = {
            "so_lan_rot_mang": ["rớt mạng", "mạng rớt", "network drop", "mất kết nối"],
            "so_lan_goi_cskh": ["cskh", "support", "tổng đài", "chăm sóc khách hàng", "hỗ trợ"],
            "do_suy_hao_quang": [
                "suy hao",
                "cáp quang",
                "tín hiệu",
                "chất lượng kém",
                "đường truyền",
            ],
        }
        insight_text = exec_output.lower()
        code_lower = code.lower()
        for feature, keywords in allowed_concepts.items():
            if feature not in tree_text and feature not in code_lower:
                for kw in keywords:
                    if kw in insight_text:
                        verdict["status"] = "REVISE"
                        verdict["feedback"] = (
                            f"⚠ Ảo giác diễn giải (Business Hallucination): Bạn kết "
                            f"luận về '{kw}' nhưng feature `{feature}` lại không được "
                            "dùng trong mô hình. Hãy dựa hoàn toàn vào dữ liệu có thật!"
                        )

    # Rule 10: NO CAUSAL HALLUCINATION
    forbidden_causal_terms = _CAUSAL_TERMS
    found_terms = [t for t in forbidden_causal_terms if t in exec_output.lower()]
    if found_terms:
        verdict["status"] = "REVISE"
        verdict["feedback"] = (
            "⚠ Ảo Giác Nhân Quả (Causal Hallucination): Bạn không được phép kết luận "
            f"nguyên nhân rời mạng là do {', '.join(found_terms)}. Tập dữ liệu FTEL "
            "này CHỈ có các biến hành vi kỹ thuật. Bạn phải giải thích dựa trên dữ "
            "liệu thật!"
        )

    # Rule 11: ACTION EVIDENCE ALIGNMENT
    exec_lower = exec_output.lower()
    if re.search(
        r"(?i)(0 cuộc gọi|không gọi).*?(tăng cường cskh|gọi điện|chủ động gọi)", exec_lower
    ):
        verdict["status"] = "REVISE"
        verdict["feedback"] = (
            "⚠ Mâu thuẫn Action & Evidence: Dữ liệu mẫu ghi '0 cuộc gọi CSKH' nhưng "
            "Action lại đề xuất 'Tăng cường CSKH' hoặc 'Chủ động gọi'. Lời khuyên phải "
            "ĐÚNG với vấn đề thực tế!"
        )
    if re.search(
        r"(?i)(không rớt mạng|suy hao tốt|ổn định).*?(kiểm tra kỹ thuật|kéo cáp|bảo trì)",
        exec_lower,
    ):
        verdict["status"] = "REVISE"
        verdict["feedback"] = (
            "⚠ Mâu thuẫn Action & Evidence: Khách hàng ổn định (không rớt mạng, suy "
            "hao tốt) nhưng bạn lại đề xuất 'kiểm tra kỹ thuật' hoặc 'bảo trì cáp'. "
            "Lời khuyên hành động bị sai lệch hoàn toàn với dữ liệu!"
        )

    # Rule 13: NO INVENTED METRICS EVALUATION
    if re.search(r"(?i)(tốt|xấu|kém|hoàn hảo).*?(dbm)", exec_lower) or re.search(
        r"(?i)(dbm).*?(tốt|xấu|kém|hoàn hảo)", exec_lower
    ):
        verdict["status"] = "REVISE"
        verdict["feedback"] = (
            "⚠ Ảo giác Đánh giá (Invented Threshold): Bạn ĐANG TỰ ĐÁNH GIÁ chỉ số dBm "
            "là 'tốt' hoặc 'xấu'. Do không có tài liệu kỹ thuật FTEL đính kèm, BẠN CHỈ "
            "ĐƯỢC BÁO CÁO GIÁ TRỊ THỰC TẾ (Ví dụ: 'Trung bình là -16.4 dBm'), TUYỆT "
            "ĐỐI KHÔNG DÙNG TỪ TỐT/XẤU."
        )

    # Rule 12: PRIORITY SCORE EXPLAINABLE
    if "priority score" in exec_lower or "opportunity score" in exec_lower:
        if not re.search(r"(?i)(công thức|formula|=|tính bằng|tính theo|x|\*)", exec_lower):
            verdict["status"] = "REVISE"
            verdict["feedback"] = (
                "⚠ Thiếu Minh Bạch: Bạn đang xếp hạng 'Priority Score' nhưng không in "
                "ra công thức tính. BẤT KỲ metric tự chế nào cũng BẮT BUỘC phải đi kèm "
                "công thức minh bạch (VD: Priority Score = Revenue At Risk * Churn Rate)."
            )

    # Gate 6, 7, 8: Anti-Hallucination for zero-variance datasets
    try:
        if personas:
            personas_json = personas
            cluster_count = len(personas_json)

            # Gate 6: No Fake Persona
            if cluster_count == 1:
                fake_terms = [
                    "lâu năm",
                    "trung thành",
                    "giá nhạy cảm",
                    "hay gọi cskh",
                    "gọi cskh nhiều",
                    "tương tác cao",
                    "ít tương tác",
                ]
                found_fake = [
                    t for t in fake_terms if t in exec_output.lower() or t in code.lower()
                ]
                if found_fake:
                    verdict["status"] = "REVISE"
                    verdict["feedback"] = (
                        "⚠ Gate 6 (No Fake Persona): Dataset chỉ phân được 1 cụm duy "
                        "nhất (100% data). BẠN CẤM DÙNG các từ mang tính so sánh như "
                        f"{', '.join(found_fake)} vì không có cụm nào khác để so sánh. "
                        "Hãy đặt tên trung lập như 'Khách hàng churn phổ biến', 'Nhóm "
                        "hành vi không phân biệt được', hoặc 'Homogeneous Churn Group'."
                    )

            # Gate 7: No Increase-K Suggestion
            if cluster_count > 0:
                largest_cluster_pct = max([float(p.get("support_pct", 0)) for p in personas_json])
                if largest_cluster_pct > 0.8:  # >80% data in 1 cluster
                    increase_k_terms = [
                        "thử k từ 4",
                        "thử k từ 5",
                        "tăng k",
                        "increase k",
                        "thử k từ 4-6",
                        "thử k=4",
                        "thử k=5",
                        "thử k=6",
                    ]
                    # We also check the AI's markdown report instructions, but since
                    # verifier only checks JSON/Code, we enforce it if it prints it
                    # in stdout or if the LLM adds it in persona text.
                    found_k = [
                        t for t in increase_k_terms if t in exec_output.lower() or t in code.lower()
                    ]
                    if found_k:
                        verdict["status"] = "REVISE"
                        verdict["feedback"] = (
                            "⚠ Gate 7 (No Increase-K Suggestion): Cụm lớn nhất chiếm "
                            f"{largest_cluster_pct*100}% dữ liệu (Silhouette > 0.6). "
                            "Vấn đề KHÔNG PHẢI LÀ K, mà là dữ liệu KHÔNG CÓ TÍN HIỆU "
                            "PHÂN TÁCH. CẤM đề xuất tăng K hoặc thử K=4,5,6. Bạn PHẢI "
                            "KẾT LUẬN: 'Dữ liệu hiện tại không chứa đủ tín hiệu để "
                            "phân tách hành vi'."
                        )

            # Gate 8: Root Cause Integrity
            revenue_columns_not_found = all(float(p.get("arpu", 0)) == 0 for p in personas_json)
            if revenue_columns_not_found:
                revenue_terms = ["roi", "revenue at risk", "recoverable revenue", "priority score"]
                found_rev = [
                    t for t in revenue_terms if t in exec_output.lower() or t in code.lower()
                ]
                if found_rev:
                    verdict["status"] = "REVISE"
                    verdict["feedback"] = (
                        "⚠ Gate 8 (Root Cause Integrity): Dataset không có biến doanh "
                        f"thu (ARPU=0). CẤM sử dụng các keyword {', '.join(found_rev)}. "
                        "Bắt buộc ép chạy 100% ở ROOT CAUSE MODE."
                    )

            # Gate 9: Outlier Naming
            for p in personas_json:
                if float(p.get("support_pct", 1)) < 0.01:
                    bad_words = ["persona", "nhóm khách hàng", "segment", "cụm phổ biến"]
                    name = str(p.get("persona_name", "")).lower()
                    text = str(p.get("sample_persona_text", "")).lower()
                    if any(w in name for w in bad_words) or any(w in text for w in bad_words):
                        verdict["status"] = "REVISE"
                        verdict["feedback"] = (
                            f"⚠ Gate 9 (Outlier Naming): Cụm '{p.get('persona_name')}' "
                            "chỉ chiếm <1%. CẤM gọi là 'Persona' hay 'Nhóm khách hàng'. "
                            "Bắt buộc đổi tên thành 'Nhóm ngoại lệ', 'Outlier Cluster', "
                            "hoặc 'Anomaly Group'."
                        )

            # Gate 10: Persona Name Duplicate
            names = [str(p.get("persona_name", "")).lower().strip() for p in personas_json]
            if len(names) != len(set(names)):
                verdict["status"] = "REVISE"
                verdict["feedback"] = (
                    "⚠ Gate 10 (Persona Name Duplicate): Bị trùng tên Persona giữa "
                    "các cụm. BẮT BUỘC phải phân cấp (ví dụ: thấp, cao, cực cao) để "
                    "đảm bảo KHÔNG CÓ TÊN NÀO TRÙNG NHAU."
                )
    except Exception:
        pass

    # Gate 11: Cluster Leakage — only check persona_name fields in JSON, not entire output
    try:
        if personas:
            for _p in personas:
                _pname = str(_p.get("persona_name", "")).lower()
                if re.match(r"^(cluster_?\s*\d+|cụm\s*\d+)$", _pname.strip()):
                    verdict["status"] = "REVISE"
                    verdict["feedback"] = (
                        f"⚠ Gate 11 (Cluster ID Leakage): Persona tên "
                        f"'{_p.get('persona_name')}' là tên kỹ thuật thuần túy. BẮT "
                        "BUỘC phải gọi bằng Tên Persona có ý nghĩa nghiệp vụ."
                    )
    except Exception:
        pass

    # Rule 9: Metadata Integrity
    if "sentiment" in code.lower() or "cảm xúc" in exec_output.lower():
        if "do_suy_hao_quang" in code.lower() or "do_suy_hao_quang" in exec_output.lower():
            verdict["status"] = "REVISE"
            verdict["feedback"] = (
                "⚠ Lỗi Metadata (Metadata Integrity): 'do_suy_hao_quang' là độ suy "
                "hao quang học (Optical Attenuation), KHÔNG PHẢI chỉ số cảm xúc "
                "(Sentiment). Không được tự chế khái niệm."
            )

    if re.search(
        r"(?i)(ctbdv|đi vắng).*?(proxy arpu|doanh thu)", exec_output.lower() + " " + code.lower()
    ):
        verdict["status"] = "REVISE"
        verdict["feedback"] = (
            "⚠ Lỗi Giải thích (Metadata Hallucination): CTBDV là 'Chủ thuê bao đi "
            "vắng', TUYỆT ĐỐI KHÔNG giải thích nó là 'Proxy ARPU'."
        )

    return _verdict.new_verdict(
        verdict["status"],
        feedback=verdict["feedback"],
        missing=verdict["missing"],
        epiplexity_score=verdict["epiplexity_score"],
    )
