import inspect
import json
import os
from datetime import datetime
from typing import Any, Dict, List

from pdca.observability.logger import get_logger
from pdca.tools import REGISTRY  # B14: source of truth thay REMEDIATION_TOOLS

logger = get_logger(__name__)

# Phase B8: default file paths giữ ở module-level cho `load()` backward
# compat. AnalysisAgent KHÔNG còn nhận path qua __init__ — orchestrator
# truyền `pre_scan`/`post_scan` dict trực tiếp.
_DEFAULT_PRE_PATH = "data/artifacts/pre_scan.json"
_DEFAULT_POST_PATH = "data/artifacts/post_scan.json"


class AnalysisAgent:
    """So sánh pre vs post scan, phân loại trạng thái remediation.

    Phase B8: API thống nhất — chỉ nhận data trực tiếp qua `run(pre_scan,
    post_scan, pipeline_context)`. `__init__` không còn tham số. Method
    `load()` giữ làm helper backward-compat (đọc từ default artifact paths).
    """

    def __init__(self) -> None:
        # Không còn before_path/after_path — orchestrator chịu trách nhiệm
        # đọc file & truyền dict vào run().
        self.last_stats: Dict[str, Any] = {}

    def load(self):
        """Backward-compat: đọc từ default artifact paths (DEPRECATED).

        Phase B8: Giữ method để test cũ không break, nhưng caller mới
        nên truyền `pre_scan` + `post_scan` dict thẳng vào `run()`.
        """
        before_path = _DEFAULT_PRE_PATH
        after_path = _DEFAULT_POST_PATH
        if not os.path.exists(before_path) or not os.path.exists(after_path):
            logger.warning("Scan files not found",
                           extra={"pre": before_path, "post": after_path})
            return [], []
        with open(before_path, "r", encoding="utf-8") as f:
            before = json.load(f).get("findings", [])
        with open(after_path, "r", encoding="utf-8") as f:
            after = json.load(f).get("findings", [])
        return before, after

    def run(self, pre_scan: dict = None, post_scan: dict = None,
            pipeline_context: List[Dict] = None) -> dict:
        """Phân tích diff giữa pre-scan và post-scan.

        Input:  raw scan data + execution context
        Output: dict chứa ĐẦY ĐỦ kết quả phân tích (single source of truth)
                Không chứa metadata (account_id, region...) — orchestrator lo.

        Backward compat: nếu pre_scan/post_scan = None → đọc default file
        (chỉ cho test cũ; pipeline mới luôn truyền dict).
        """
        if pre_scan is None or post_scan is None:
            before, after = self.load()
        else:
            before = pre_scan.get("findings", [])
            after = post_scan.get("findings", [])

        pipeline_context = pipeline_context or []

        logger.info("Aggregating analysis data",
                    extra={"pre_count": len(before), "post_count": len(after)})

        # 1. Map dữ liệu
        before_map = {f["finding_uid"]: f for f in before}
        after_map = {f["finding_uid"]: f for f in after}

        # 2. Group Tasks theo finding_uid
        tasks_by_finding = {}
        for item in pipeline_context:
            uid = item.get("finding_uid")
            if uid:
                tasks_by_finding.setdefault(uid, []).append(item)

        diff_result = []

        # KHỞI TẠO BIẾN ĐẾM (STATS)
        stats = {
            "total_pre": len(before),
            "total_post": len(after),
            "pass_pre": sum(1 for f in before if f["status"] == "PASS"),
            "fail_pre": sum(1 for f in before if f["status"] == "FAIL"),
            "pass_post": sum(1 for f in after if f["status"] == "PASS"),
            "fail_post": sum(1 for f in after if f["status"] == "FAIL"),
            # Remediation Stats
            "remediate_pass": 0,  # Sửa xong
            "remediate_fail": 0,  # Sửa auto nhưng fail
            "manual_required": 0,  # Cần sửa tay
            # Changes Stats
            "fixed": 0,  # FAIL -> PASS
            "new_fail": 0,  # PASS -> FAIL
            "pass_unchanged": 0,  # PASS -> PASS
            "fail_unchanged": 0,  # FAIL -> FAIL
        }

        # 3. CORE LOGIC
        for uid, bf in before_map.items():
            af = after_map.get(uid)
            related_tasks = tasks_by_finding.get(uid, [])

            entry = bf.copy()
            entry["finding_uid"] = uid
            entry["before_status"] = bf["status"]
            entry["remediation_actions"] = []

            if related_tasks:
                first = related_tasks[0]

                entry["execution_status"] = first.get("execution_status")
                entry["execution_output"] = first.get("execution_output", {})
                entry["tool_name"] = first.get("tool_name")
                entry["tool_params"] = first.get("tool_params")

                # Action mà tool đã làm (vd: Enable KMS Encryption)
                entry["action"] = entry["execution_output"].get("action")

                # Resource mà tool tác động (vd: logs-06520…)
                entry["resource"] = entry["execution_output"].get("resource")

                # BEFORE STATE từ pre-scan (đủ để mô tả lỗi ban đầu)
                entry["before"] = {
                    "status": bf.get("status"),
                    "severity": bf.get("severity"),
                    "resource": bf.get("resource_id"),
                    "event_code": bf.get("event_code"),
                }

                # AFTER STATE từ post-scan (chỉ cần status)
                entry["after"] = {"status": af.get("status") if af else None}

                tool_name = first.get("tool_name")
                entry["tool_description"] = self._load_tool_description(tool_name)
                entry["tool_code"] = self._load_tool_source(tool_name)

            else:
                entry["execution_status"] = None
                entry["execution_output"] = {}
                entry["tool_name"] = None
                entry["tool_params"] = {}
                entry["action"] = None
                entry["resource"] = entry.get("resource_id")

                entry["before"] = {
                    "status": bf.get("status"),
                    "severity": bf.get("severity"),
                    "resource": bf.get("resource_id"),
                    "event_code": bf.get("event_code"),
                }

                entry["after"] = {"status": af.get("status") if af else None}

            # --- A. Enrich Actions & Detect Manual ---
            is_manual_case = False
            for task in related_tasks:
                if (
                    task.get("manual_required") is True
                    or task.get("execution_status") == "manual_required"
                ):
                    is_manual_case = True

                entry["remediation_actions"].append(task)
                entry["manual_required"] = is_manual_case

            # --- B. Tính toán Stats & Changes ---

            # Xử lý trường hợp không tìm thấy finding sau scan (coi như fixed hoặc pass)
            af_status = af["status"] if af else "PASS"

            if bf["status"] == "PASS":
                if af_status == "FAIL":
                    stats["new_fail"] += 1
                    entry["change"] = "NewIssue"
                else:
                    stats["pass_unchanged"] += 1
                    entry["change"] = "Unchanged"

            elif bf["status"] == "FAIL":
                if af_status == "PASS":
                    stats["fixed"] += 1
                    stats["remediate_pass"] += 1  # Auto fix thành công
                    entry["change"] = "Fixed"
                else:
                    # Vẫn FAIL
                    stats["fail_unchanged"] += 1

                    if is_manual_case:
                        stats["manual_required"] += 1
                        entry["change"] = "ManualRequired"
                    elif related_tasks:
                        # Có chạy auto tool nhưng vẫn fail
                        stats["remediate_fail"] += 1
                        entry["change"] = "RemediationFailed"
                    else:
                        entry["change"] = "Unchanged"

            entry["after_status"] = af_status
            diff_result.append(entry)

        # 4. Save File
        self.last_stats = stats
        self._save_file(diff_result, stats)

        # 5. IN LOG THEO ĐÚNG MẪU YÊU CẦU
        self._print_custom_log(stats)

        # 6. Phân loại findings
        classified = self._normalize_and_classify(diff_result)

        # 7. Format manual findings
        manual_findings = self._format_manual_findings(classified.get("manual", []))

        # 8. Build findings summary table
        findings_table = self._build_findings_summary(before, after, diff_result)

        # 9. Count severity
        severity_pre = self._count_severity(before)

        # ============================================================
        # TRẢ VỀ ANALYSIS RESULTS ĐẦY ĐỦ — single source of truth
        # Không chứa metadata (account_id, region...) — việc của orchestrator
        # ============================================================
        return {
            "pre_stats": {
                "total": len(before),
                "pass": stats["pass_pre"],
                "fail": stats["fail_pre"],
                "severity": severity_pre,
            },
            "post_stats": {
                "pass": stats["pass_post"],
                "fail": stats["fail_post"],
            },
            "remediation_stats": {
                "fixed": len(classified["fixed"]),
                "failed": len(classified["failed"]),
                "manual": len(manual_findings),
            },
            "success_findings": classified["fixed"],
            "failed_findings": classified["failed"],
            "manual_findings": manual_findings,
            "findings_table": findings_table,
            "raw_pre_findings": before,
            # Giữ diff_result và stats cho backward compat (verification_results)
            "diff_result": diff_result,
            "stats": stats,
        }

        # ==================================================================

    # ==================================================================
    # HELPER: COUNT SEVERITY
    # ==================================================================
    def _count_severity(self, findings: list) -> dict:
        """Đếm số lượng findings theo severity level."""
        result = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            sev = (f.get("severity") or "").lower()
            if sev in result:
                result[sev] += 1
        return result

    # ==================================================================
    # HELPER: FORMAT MANUAL FINDINGS
    # ==================================================================
    def _format_manual_findings(self, manual_items: list) -> list:
        """Chuẩn hóa manual findings cho report."""
        result = []
        for item in manual_items:
            exec_out = item.get("execution_output", {}) or {}
            result.append({
                "finding_uid": item.get("finding_uid"),
                "finding_id": item.get("finding_id"),
                "event_code": item.get("before", {}).get("event_code"),
                "description": item.get("description"),
                "severity": item.get("before", {}).get("severity"),
                "service": item.get("service"),
                "resource": (
                    exec_out.get("resource")
                    or item.get("resource")
                    or item.get("before", {}).get("resource")
                    or "Account-level / Multiple S3 buckets"
                ),
                "manual_required": True,
                "manual_reason": (
                    exec_out.get("reason")
                    or "This finding requires manual remediation."
                ),
                "remaining_actions": exec_out.get("remaining_actions", []),
                "tool": {
                    "name": item.get("tool_name"),
                    "description": item.get("tool_description"),
                },
            })
        return result

    # ==================================================================
    # HÀM PHÂN LOẠI DIFF
    # ==================================================================
    def _normalize_and_classify(self, diff_list):
        fixed, failed, manual, unchanged = [], [], [], []

        for item in diff_list:
            before = item.get("before_status")
            after = item.get("after_status")

            # ƯU TIÊN MANUAL
            if item.get("manual_required") is True:
                manual.append(item)
                continue

            if before == "FAIL" and after == "PASS":
                fixed.append(item)
                continue

            exec_status = item.get("execution_status")
            if exec_status in ("failed", "error"):
                failed.append(item)
                continue

            unchanged.append(item)

        return {
            "fixed": fixed,
            "failed": failed,
            "manual": manual,
            "unchanged": unchanged,
        }

    # ==================================================================
    # HÀM BUILD BẢNG FINDINGS SUMMARY
    # ==================================================================
    def _build_findings_summary(self, pre_findings, post_findings, diff_data=None):
        table = []
        post_lookup = {
            f.get("finding_id"): f for f in post_findings if f.get("finding_id")
        }
        diff_data = diff_data or []
        diff_lookup = {d.get("finding_id"): d for d in diff_data if d.get("finding_id")}

        for idx, f in enumerate(pre_findings, start=1):
            fid = f.get("finding_id")
            after = post_lookup.get(fid, {}) if fid else {}
            ctx = diff_lookup.get(fid, {}) if fid else {}

            before_status = f.get("status", "UNKNOWN")
            after_status = after.get("status", "UNKNOWN")

            # Lấy ngữ cảnh remediation từ diff
            exec_status = ctx.get("execution_status")
            manual_required = ctx.get("manual_required") is True
            change_flag = ctx.get(
                "change"
            )  # Fixed / ManualRequired / RemediationFailed / Unchanged...

            # --- CHANGE LABEL ---
            if before_status == "FAIL" and after_status == "PASS":
                change = "Fixed"

            elif before_status == "FAIL" and after_status == "FAIL":
                # Ưu tiên theo change_flag / exec_status / manual_required
                if (
                    manual_required
                    or change_flag == "ManualRequired"
                    or exec_status == "manual_required"
                ):
                    change = "Still Failing (ManualRequired)"
                elif (
                    exec_status in ("failed", "error")
                    or change_flag == "RemediationFailed"
                ):
                    change = "Still Failing (RemediationFailed)"
                else:
                    change = "Still Failing"

            elif before_status == "PASS" and after_status == "PASS":
                change = "Unchanged"

            elif before_status == "PASS" and after_status == "FAIL":
                change = "NewIssue"

            else:
                change = "Unknown"

            table.append(
                {
                    "stt": idx,
                    "check_id": f.get("event_code", ""),
                    "finding": f.get("description", ""),
                    "service": f.get("service", ""),
                    "resource": f.get("resource_id", ""),
                    "severity": f.get("severity", ""),
                    "before": before_status,
                    "after": after_status,
                    "change": change,
                }
            )

        return table

    def _save_file(self, diff_result, summary=None):
        os.makedirs("data", exist_ok=True)

        # Nếu summary chưa được truyền, tự build lại từ stats
        summary = summary or self.last_stats

        output = {
            "summary": {
                "total_pre": summary["total_pre"],
                "total_post": summary["total_post"],
                "pass_pre": summary["pass_pre"],
                "fail_pre": summary["fail_pre"],
                "pass_post": summary["pass_post"],
                "fail_post": summary["fail_post"],
                "remediate_pass": summary["remediate_pass"],
                "remediate_fail": summary["remediate_fail"],
                "manual_required": summary["manual_required"],
                "fixed": summary["fixed"],
                "new_fail": summary["new_fail"],
                "pass_unchanged": summary["pass_unchanged"],
                "fail_unchanged": summary["fail_unchanged"],
            },
            "results": diff_result,
        }

        try:
            with open("data/artifacts/analysis_diff.json", "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Failed to save analysis_diff.json", extra={"error": str(e)})

    def _print_custom_log(self, s):
        """Log summary qua structured logger (Phase B8 — không print)."""
        logger.info(
            "Analysis summary",
            extra={
                "findings": {"pre": s["total_pre"], "post": s["total_post"]},
                "status": {
                    "pass_pre": s["pass_pre"], "fail_pre": s["fail_pre"],
                    "pass_post": s["pass_post"], "fail_post": s["fail_post"],
                },
                "remediation": {
                    "pass": s["remediate_pass"], "fail": s["remediate_fail"],
                    "manual_required": s["manual_required"],
                },
                "changes": {
                    "fixed": s["fixed"], "new_fail": s["new_fail"],
                    "pass_unchanged": s["pass_unchanged"],
                    "fail_unchanged": s["fail_unchanged"],
                },
                "output_path": "data/artifacts/analysis_diff.json",
            },
        )

    def _load_tool_description(self, tool_name: str) -> dict:
        """
        Load và chuẩn hóa mô tả kỹ thuật của tool từ docstring.
        Trả về structured metadata để LLM diễn giải audit-safe.
        """
        if not tool_name:
            return {
                "intent": None,
                "behavior": [],
                "automation_level": None,
                "limitations": [],
            }

        try:
            tool = REGISTRY.get(tool_name)
            if tool is None:
                return {
                    "error": f"Tool '{tool_name}' not found in REGISTRY."
                }

            func = getattr(tool, "func", None)
            if func is None:
                return {
                    "error": f"Tool '{tool_name}' has no underlying function."
                }

            doc = inspect.getdoc(func)
            if not doc:
                return {
                    "error": f"No documentation available for tool '{tool_name}'."
                }

            # ===============================
            # PARSE DOCSTRING (THEO FORMAT BẠN ĐANG DÙNG)
            # ===============================
            intent = None
            behavior = []
            limitations = []
            automation_level = None

            for line in doc.splitlines():
                line = line.strip()

                if line.startswith("Mục đích:"):
                    intent = line.replace("Mục đích:", "").strip()

                elif line.startswith("Tự động:"):
                    automation_level = "auto"
                    behavior.append(line.replace("Tự động:", "").strip())

                elif line.startswith("Dùng khi:"):
                    # optional: có thể đưa vào context
                    pass

                elif line.startswith("Giới hạn:"):
                    limitations.append(line.replace("Giới hạn:", "").strip())

                elif line.startswith("Lưu ý:"):
                    limitations.append(line.replace("Lưu ý:", "").strip())

            if automation_level is None:
                automation_level = "manual_or_partial"

            return {
                "tool_name": tool_name,
                "intent": intent,
                "behavior": behavior,
                "automation_level": automation_level,
                "limitations": limitations,
                "raw_doc": doc,  # giữ lại để trace/audit nếu cần
            }

        except Exception as e:
            return {
                "error": f"Unable to load tool description: {e}"
            }

    def _load_tool_source(self, tool_name: str) -> str:
        """
        Snapshot source code của tool tại thời điểm remediation.
        Được dùng cho phân tích kỹ thuật hậu kiểm (engineering-grade).
        """
        if not tool_name:
            return None

        try:
            tool = REGISTRY.get(tool_name)
            if not tool:
                return f"Tool not found: {tool_name}"

            func = getattr(tool, "func", None)
            if func is None:
                return f"Tool '{tool_name}' has no implementation."

            return inspect.getsource(func)

        except Exception as e:
            return f"Error loading tool source: {e}"

