"""Generate clustering/persona code from a question + dataset profile.

Extends the plain codegen prompt (generate.py) with a strict output contract:
the script must cluster the dataset and print a persona array as JSON wrapped in
``[JSON_START_PERSONA] … [JSON_END_PERSONA]`` using the schema in persona_schema.
Domain-agnostic; the telecom domain appends extra guidance.
"""

from __future__ import annotations

import json
from typing import Callable, List, Optional

from generate import extract_code  # type: ignore[import-not-found]
from persona_schema import MARKER_END, MARKER_START  # type: ignore[import-not-found]

_SYSTEM = (
    "You are a senior data scientist. Write ONE self-contained Python script that "
    "segments the dataset into customer personas (clusters) and reports them. "
    "Rules: use ONLY libraries already installed in the sandbox — pandas, numpy, "
    "scikit-learn, matplotlib. NEVER pip install, import an unlisted package, or "
    "access the network (the sandbox blocks it and the run will fail). Use only "
    "column names that appear in the provided dataset profile — do NOT assume an "
    "'id'/'customer_id' column exists; get a cluster's row count with .size() or "
    "len(), not by counting a specific id column. Load the dataset from the exact "
    "path given; scale numeric features and choose a sensible cluster count "
    "(silhouette-guided) unless a count is specified; for each cluster compute "
    "support (row count) and support_pct (fraction of rows). Build a list "
    "`personas` where each item is a dict with these keys: cluster_id "
    "(int), persona_name (str), support (int), support_pct (float 0..1), "
    "confidence ('HIGH'|'MEDIUM'|'LOW'), priority_score (float), is_anomaly "
    "(bool), segmentation_quality (str), risk ('HIGH'|'MEDIUM'|'LOW'), risk_tier "
    "(str), severity ('LOW'|'MEDIUM'|'HIGH'|'EXTREME'), evidence (dict of the "
    "distinguishing features -> cluster mean, only features that deviate notably "
    "from the global mean), profile_attributes (dict), recommended_actions "
    "(list of str). "
    "Data-quality rules for the numbers you emit: (1) NEVER let a sentinel/fill "
    "value leak into evidence or feature means — e.g. a 'months since last X' of "
    "999 meaning 'never', or -1 meaning 'missing loyalty/VIP'; drop such features "
    "for that cluster or report null, never their average. (2) Keep binary-flag "
    "cluster means consistent with their base metric: if a cluster's call volume "
    "is ~0, its frequent_caller / high_missed_ratio / *_contact means MUST be ~0, "
    "not 1.0. (3) risk and risk_tier MUST differentiate clusters — do NOT label "
    "every segment HIGH; tie them to priority_score (higher score => higher "
    "risk). "
    "profile_attributes MUST include (when the columns exist) service_composition "
    "and package_composition as {category: fraction} maps, plus any of csat_avg, "
    "ces_avg, avg_fee, high_spender_pct, tier_upgrade_rate, tier_downgrade_rate, "
    "usage_decline_strong_pct, usage_decline_mild_pct, usage_unstable_pct, "
    "status_worsening_pct, loyalty_rank_avg. recommended_actions[0] MUST be EXACTLY "
    "one of these business actions (copy verbatim): "
    "'Outbound CSKH chủ động để xoa dịu khách hàng', 'Thu thập thêm dữ liệu hành vi', "
    "'Thu thập thêm App usage logs', 'Khảo sát mức độ hài lòng qua Zalo/SMS', "
    "'Phân tích nguyên nhân khiếu nại/liên hệ', 'Nghiên cứu nguyên nhân kỹ thuật', "
    "'Tư vấn đổi gói cước phù hợp hành vi sử dụng', "
    "'Khảo sát cơ hội upsell/cross-sell dịch vụ', "
    "'Chủ động liên hệ trước nguy cơ hạ cấp dịch vụ', "
    "'Phân tích nguyên nhân sử dụng dao động'. "
    "PRINT the formula you use for "
    "priority_score in plain text. Then print the markers and JSON exactly:\n"
    f"print('{MARKER_START}')\n"
    "print(json.dumps(personas, ensure_ascii=False))\n"
    f"print('{MARKER_END}')\n"
    "Also save a flat one-row-per-persona table to 'result.csv' "
    "(df.to_csv('result.csv', index=False), <= 50 rows). Do NOT access the "
    "network, spawn processes, or write outside the current directory. Return the "
    "code in one ```python``` block."
)
_TELECOM = (
    " Domain: telecom churn. Only use behavioural/technical fields already in the "
    "data; NEVER attribute churn to promotions, competitors, or marketing. Do not "
    "label raw metrics (e.g. dBm) as 'good'/'bad' — report the value."
)


def build_messages(
    question: str,
    profile: dict,
    *,
    k: Optional[int] = None,
    domain: Optional[str] = None,
    prior_error: Optional[str] = None,
    hypotheses: Optional[str] = None,
) -> List[dict]:
    """Build code-generation chat messages for the persona pipeline.

    Args:
        question: The user's natural-language segmentation request.
        profile: Dataset profile from ``profile.profile_dataset``.
        k: Optional fixed cluster count.
        domain: Optional domain pack name (e.g. ``"telecom"``).
        prior_error: Traceback from a failed run, to drive repair.
        hypotheses: Verifier hypotheses, to drive revision.

    Returns:
        OpenAI-format message list.
    """
    system = _SYSTEM + (_TELECOM if domain == "telecom" else "")
    prof_json = json.dumps(
        {
            key: profile[key]
            for key in ("path", "n_rows", "n_cols", "columns", "sample")
            if key in profile
        },
        default=str,
    )
    user = (
        f"Dataset path: {profile.get('path')}\n"
        f"Dataset profile (JSON):\n{prof_json}\n\n"
        f"Request: {question}\n"
    )
    if k is not None:
        user += f"\nUse exactly k={k} clusters.\n"
    if prior_error:
        user += f"\nThe previous code failed with this error — fix it:\n{prior_error}\n"
    if hypotheses:
        user += f"\nA verifier rejected the previous result. Address:\n{hypotheses}\n"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_code(
    question: str,
    profile: dict,
    chat_fn: Callable[[List[dict]], str],
    *,
    k: Optional[int] = None,
    domain: Optional[str] = None,
    prior_error: Optional[str] = None,
    hypotheses: Optional[str] = None,
) -> str:
    """Generate persona clustering code, returning the extracted Python.

    Args:
        question: The user's request.
        profile: Dataset profile.
        chat_fn: Callable mapping messages -> model text (bound to the codegen role).
        k: Optional fixed cluster count.
        domain: Optional domain pack name.
        prior_error: Optional error from a prior run.
        hypotheses: Optional verifier hypotheses.

    Returns:
        The extracted Python code; if no fenced block is present, the raw text.
    """
    messages = build_messages(
        question, profile, k=k, domain=domain, prior_error=prior_error, hypotheses=hypotheses
    )
    text = chat_fn(messages)
    found, code = extract_code(text)
    return code if found else text
