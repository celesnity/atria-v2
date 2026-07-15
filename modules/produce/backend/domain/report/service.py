"""E10 Báo cáo & hiển thị — tổng hợp thuần từ các epic khác (không bảng riêng).

Dashboard live trạng thái tổ (P-RPT-01) và báo cáo cuối ca tự tổng hợp
(P-RPT-02: sản lượng, OEE, top lý do downtime, phế phẩm). Chỉ gọi service của
epic nguồn — không truy vấn trực tiếp model epic khác (giữ isolation).
"""

from __future__ import annotations

from domain.downtime import service as downtime_service
from domain.exception import service as exception_service
from domain.oee import service as oee_service
from domain.scrap import service as scrap_service
from domain.wip import service as wip_service
from domain.work import service as work_service


def live_dashboard(line_id: int) -> dict:
    """Trạng thái tổ theo thời gian thực (P-RPT-01)."""
    return {
        "line_id": line_id,
        "tasks": work_service.team_board(line_id),
        "open_andons": downtime_service.team_andons(line_id),
        "open_exceptions": exception_service.open_exceptions(line_id),
    }


def end_of_shift_report(line_id: int, shift_id: int, total_count: int) -> dict:
    """Báo cáo cuối ca tự tổng hợp (P-RPT-02).

    OEE bỏ qua nếu chưa nạp production order (báo cáo vẫn ra được phần còn lại).
    """
    try:
        oee = oee_service.shift_oee(shift_id, total_count)
    except oee_service.OeeError as exc:
        oee = {"error": str(exc)}

    return {
        "line_id": line_id,
        "shift_id": shift_id,
        "output_count": total_count,
        "oee": oee,
        "scrap_count": scrap_service.scrap_total(shift_id=shift_id),
        "top_downtime_reasons": downtime_service.top_reasons(shift_id),
    }


def why_late(line_id: int, shift_id: int, downtime_threshold_min: float = 15.0) -> dict:
    """Vì sao line X trễ: lần theo downtime, ngoại lệ và WIP của line (P-RPT-04).

    Tổng hợp các nguyên nhân khả dĩ để quản lý ra quyết định dựa trên dữ liệu —
    phiên bản Track A của việc traverse graph.
    """
    return {
        "line_id": line_id,
        "shift_id": shift_id,
        "long_downtimes": downtime_service.long_open(downtime_threshold_min),
        "top_downtime_reasons": downtime_service.top_reasons(shift_id),
        "open_exceptions": exception_service.open_exceptions(line_id),
        "wip_by_station": wip_service.wip_by_station(),
        "scrap_by_station": scrap_service.scrap_by_station(shift_id=shift_id),
    }


def trend(entries: list[dict]) -> list[dict]:
    """Xu hướng OEE qua các ca (P-RPT-03). entries: [{shift_id, total_count}].

    OEE bỏ qua (error mềm) nếu ca chưa nạp production order.
    """
    out: list[dict] = []
    for e in entries:
        shift_id = int(e["shift_id"])
        total = int(e.get("total_count", 0))
        try:
            r = oee_service.shift_oee(shift_id, total)
            out.append({"shift_id": shift_id, "oee": r["oee"], "total_count": total})
        except oee_service.OeeError as exc:
            out.append({"shift_id": shift_id, "oee": None, "error": str(exc)})
    return out
