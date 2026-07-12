"""Seed the garage-copilot demo: manual corpus + historical work logs.

Plants a believable workshop history so the flywheel is demonstrable from the
first minute: past repair cases (including one that matches the star demo
scenario) become searchable via ``work_log_search`` / the REST search endpoint,
and the manual corpus is (re)ingested.

Idempotent — safe to run repeatedly (records are keyed by session id; Qdrant
points are uuid5 of the citation).

Usage:
    python seed_demo.py            # ingest corpus + seed work logs
    python seed_demo.py --logs-only
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent


def _load(name: str) -> ModuleType:
    key = f"_garage_seed_{name}"
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, _HERE / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"cannot load {name} from {_HERE}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


# Five historical cases across the three brands. The first matches the star
# demo scenario so a paraphrase search during the demo surfaces real history.
SEED_WORKLOGS: list[dict] = [
    {
        "session_id": "seed-0101",
        "ro_number": "RO-2026-0101",
        "vin": "SCATV03C9PU204411",
        "brand": "Rolls-Royce",
        "technician": "Tran Minh B",
        "symptom_reported": "Xe rung nhẹ ở tầm 60 cây, đạp ga thấy rõ hơn",
        "hypotheses": [
            {
                "hypothesis": "Mất cân bằng bánh xe",
                "outcome": "rejected",
                "evidence": "Cân bằng lại 4 bánh, rung không đổi; rung giảm khi coast",
            },
            {
                "hypothesis": "Mòn khớp CV trong (tripod) trục trước",
                "outcome": "confirmed",
                "evidence": "Độ rơ hướng kính tại tripod housing bên phải, boot còn nguyên",
            },
        ],
        "diagnostic_steps": [
            {
                "step": "Road test theo WSM-RR-1005, phân biệt load/coast",
                "result": "Rung 55-70 km/h, tăng khi đạp nhẹ ga, gần hết khi coast",
                "citation": "WSM-RR-1005#1",
            },
            {
                "step": "Kiểm tra CV axle hai bên theo WSM-RR-2041",
                "result": "Bên phải có độ rơ tại tripod; bên trái ổn",
                "citation": "WSM-RR-2041#0",
            },
        ],
        "root_cause": "Mòn khớp CV trong (tripod) trục trước bên phải — đúng lô TSB-RR-2026-03",
        "fix_applied": "Thay nguyên cụm CV axle phải (part 31 60 7 999 102), torque theo "
        "WSM-RR-2041, road test lại hết rung",
        "parts_used": ["31 60 7 999 102", "31 20 6 867 260"],
        "tools_used": ["cần siết lực", "máy cân bằng bánh xe"],
        "citations": ["WSM-RR-1005#1", "WSM-RR-2041#0", "TSB-RR-2026-03#1"],
        "status": "complete",
        "language": "vi",
        "created_at": "2026-04-18T09:30:00+00:00",
    },
    {
        "session_id": "seed-0102",
        "ro_number": "RO-2026-0102",
        "vin": "SCATC42C0RU330077",
        "brand": "Rolls-Royce",
        "technician": "Nguyen Van A",
        "symptom_reported": "Đạp phanh từ cao tốc xuống thì rung vô lăng, chạy bình thường không rung",
        "hypotheses": [
            {
                "hypothesis": "Mất cân bằng bánh trước",
                "outcome": "rejected",
                "evidence": "Rung CHỈ xuất hiện khi phanh — chữ ký của đĩa phanh, không phải cân bằng",
            },
            {
                "hypothesis": "Đĩa phanh trước bị dày mỏng không đều (DTV)",
                "outcome": "confirmed",
                "evidence": "Đo runout + độ dày đĩa: lệch vượt chuẩn ở đĩa trước trái",
            },
        ],
        "diagnostic_steps": [
            {"step": "Road test: phanh từ 120 xuống 60", "result": "Rung vô lăng rõ khi phanh"},
            {"step": "Đo độ dày đĩa tại 8 điểm", "result": "Chênh 0.06mm đĩa trái (chuẩn <0.02)"},
        ],
        "root_cause": "Đĩa phanh trước trái dày mỏng không đều (disc thickness variation)",
        "fix_applied": "Thay cặp đĩa phanh trước + má phanh, chạy rà theo quy trình, hết rung",
        "parts_used": ["34 11 6 887 401", "34 11 6 887 540"],
        "tools_used": ["đồng hồ so", "panme đo đĩa"],
        "citations": ["WSM-RR-2040#4"],
        "status": "complete",
        "language": "vi",
        "created_at": "2026-05-06T14:00:00+00:00",
    },
    {
        "session_id": "seed-0103",
        "ro_number": "RO-2026-0103",
        "vin": "ZPBUA1ZL9PLA55210",
        "brand": "Lamborghini",
        "technician": "Le Quang C",
        "symptom_reported": "Urus đỗ 4-5 ngày là hết bình, khách phải câu bình hai lần",
        "hypotheses": [
            {
                "hypothesis": "Bình yếu",
                "outcome": "rejected",
                "evidence": "Test dung lượng bình đạt; sạc đầy vẫn tụt sau vài ngày",
            },
            {
                "hypothesis": "Dòng rò do thiết bị lắp thêm",
                "outcome": "confirmed",
                "evidence": "Dòng ngủ 380mA; rút cầu chì mạch camera hành trình → về 32mA",
            },
        ],
        "diagnostic_steps": [
            {
                "step": "Đo dòng ngủ sau 30 phút khóa xe theo WSM-LAM-3020",
                "result": "380mA — vượt xa chuẩn <50mA",
                "citation": "WSM-LAM-3020#1",
            },
            {"step": "Rút cầu chì từng mạch", "result": "Camera hành trình đấu điện thường trực"},
        ],
        "root_cause": "Camera hành trình lắp ngoài đấu nguồn thường trực gây dòng rò 350mA",
        "fix_applied": "Đấu lại camera qua nguồn ACC có hạ áp tự ngắt, dòng ngủ về 32mA, "
        "theo dõi 1 giờ ổn định",
        "parts_used": [],
        "tools_used": ["ampe kìm", "hộp cầu chì thử"],
        "citations": ["WSM-LAM-3020#1"],
        "status": "complete",
        "language": "vi",
        "created_at": "2026-05-27T10:15:00+00:00",
    },
    {
        "session_id": "seed-0104",
        "ro_number": "RO-2026-0104",
        "vin": "SBM14FCA4KW004832",
        "brand": "McLaren",
        "technician": "Tran Minh B",
        "symptom_reported": "Đánh lái hết cỡ lúc quay đầu nghe tách tách ở bánh trước",
        "hypotheses": [
            {
                "hypothesis": "Mòn khớp CV ngoài",
                "outcome": "confirmed",
                "evidence": "Tiếng click mỗi nhịp khi đánh hết lái; boot ngoài nứt, văng mỡ",
            },
        ],
        "diagnostic_steps": [
            {
                "step": "Kiểm tra boot và khớp ngoài trên cầu nâng",
                "result": "Boot ngoài trái nứt ở nếp gấp, mỡ văng lên tai xe",
                "citation": "WSM-RR-2041#0",
            },
        ],
        "root_cause": "Khớp CV ngoài trái chạy khô do boot nứt",
        "fix_applied": "Thay cụm CV axle trái (khớp đã chạy khô — không tra mỡ lại theo quy trình)",
        "parts_used": ["11B-0871-CP"],
        "tools_used": ["cầu nâng", "kềm bấm đai boot"],
        "citations": ["WSM-RR-2041#0"],
        "status": "complete",
        "language": "vi",
        "created_at": "2026-06-14T16:40:00+00:00",
    },
    {
        "session_id": "seed-0105",
        "ro_number": "RO-2026-0105",
        "vin": "SCATV03C9PU201188",
        "brand": "Rolls-Royce",
        "technician": "Nguyen Van A",
        "symptom_reported": "Ù ù ở sàn xe từ 80 km/h trở lên, đánh lái không đổi",
        "hypotheses": [
            {
                "hypothesis": "Khớp CV trong",
                "outcome": "rejected",
                "evidence": "Không nhạy tải, dải tốc độ cao hơn chữ ký CV joint",
            },
            {
                "hypothesis": "Bạc đạn treo giữa láp dọc (centre bearing)",
                "outcome": "confirmed",
                "evidence": "Cao su centre bearing nứt vòng quanh, láp dọc võng nhẹ",
            },
        ],
        "diagnostic_steps": [
            {
                "step": "Phân loại theo WSM-RR-2040 Stage 3",
                "result": "Drone >80km/h, không nhạy lái → propshaft/centre bearing",
                "citation": "WSM-RR-2040#3",
            },
        ],
        "root_cause": "Cao su centre bearing láp dọc lão hóa, nứt",
        "fix_applied": "Thay centre bearing, cân chỉnh lại láp dọc, hết ù",
        "parts_used": ["26 12 8 743 220"],
        "tools_used": ["cầu nâng", "đồng hồ so"],
        "citations": ["WSM-RR-2040#3"],
        "status": "complete",
        "language": "vi",
        "created_at": "2026-06-30T08:20:00+00:00",
    },
]


def seed_worklogs(worklog: ModuleType, store=None) -> list[str]:
    """Save + index every seed record; returns the saved session ids."""
    saved: list[str] = []
    for record in SEED_WORKLOGS:
        problems = worklog.validate_record(record)
        if problems:  # pragma: no cover - guarded by tests
            raise ValueError(f"seed {record['session_id']} invalid: {problems}")
        worklog.save_record_json(record)
        worklog.index_record(record, store=store)
        saved.append(record["session_id"])
    return saved


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="seed_demo.py", description=__doc__)
    ap.add_argument("--logs-only", action="store_true", help="Skip corpus ingest.")
    args = ap.parse_args(argv)

    garage = _load("garage")
    worklog = _load("worklog")
    garage._load_dotenv()

    summary: dict = {}
    if not args.logs_only:
        docs = garage.ek("corpus").load_corpus(garage.corpus_dir())
        garage._cmd_ingest(garage.corpus_dir())
        summary["corpus_documents"] = len(docs)

    store = worklog._build_store()
    saved = seed_worklogs(worklog, store=store)
    summary["worklogs_seeded"] = saved
    summary["worklog_dir"] = str(worklog.worklog_dir())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
