import json
import os
from typing import List, Dict, Any
from datetime import datetime

import inspect
from agent_tools import REMEDIATION_TOOLS


class AnalysisAgent:
    """
    AnalysisAgent (Custom Formatter Version)
    ------------------------------
    Nhiệm vụ:
    1. So sánh Pre vs Post scan.
    2. Phân loại trạng thái (Fixed, Manual, Failed...).
    3. In log theo đúng format yêu cầu (Summary, Breakdown, Remediation Results...).
    """

    def __init__(
        self, before_path="data/pre_scan.json", after_path="data/post_scan.json"
    ):
        self.before_path = before_path
        self.after_path = after_path

    def load(self):
        """Load dữ liệu scan thô từ file"""
        if not os.path.exists(self.before_path) or not os.path.exists(self.after_path):
            print("[AnalysisAgent] ⚠️ Warning: Scan files not found.")
            return [], []

        with open(self.before_path, "r", encoding="utf-8") as f:
            before = json.load(f).get("findings", [])
        with open(self.after_path, "r", encoding="utf-8") as f:
            after = json.load(f).get("findings", [])
        return before, after

    def run(self, pipeline_context: List[Dict] = None) -> List[Dict]:
        before, after = self.load()
        pipeline_context = pipeline_context or []

        print(f"\n[AnalysisAgent] 🤖 Aggregating data...")

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

            related_tasks = tasks_by_finding.get(uid, [])

            if related_tasks:
                first = related_tasks[0]

                entry["execution_status"] = first.get("execution_status")
                entry["execution_output"] = first.get("execution_output", {})
                entry["tool_name"] = first.get("tool_name")
                entry["tool_params"] = first.get("tool_params")

                # ⬇⬇ NEW FIELDS FOR REPORT ⬇⬇

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

        return diff_result

        # ==================================================================

    # BUILD REPORT CONTEXT (TRẢ VỀ DỮ LIỆU CHUẨN ĐỂ REPORT_AGENT DÙNG)
    # ==================================================================
    def build_report_context(self, pre_scan, post_scan, diff_data, meta=None):
        """
        Build toàn bộ dữ liệu dùng cho báo cáo.
        Bao gồm số liệu, phân loại findings, bảng summary và metadata hệ thống.
        """

        meta = meta or {}

        # -----------------------------------------------
        # 1) Extract từ pre_scan & post_scan
        # -----------------------------------------------
        pre_findings = pre_scan.get("findings", [])
        post_findings = post_scan.get("findings", [])

        total_pre = len(pre_findings)

        pre_pass = sum(1 for f in pre_findings if f.get("status") == "PASS")
        pre_fail = sum(1 for f in pre_findings if f.get("status") == "FAIL")

        post_pass = sum(1 for f in post_findings if f.get("status") == "PASS")
        post_fail = sum(1 for f in post_findings if f.get("status") == "FAIL")

        severity_pre = {
            "critical": sum(
                1 for f in pre_findings if f.get("severity", "").lower() == "critical"
            ),
            "high": sum(
                1 for f in pre_findings if f.get("severity", "").lower() == "high"
            ),
            "medium": sum(
                1 for f in pre_findings if f.get("severity", "").lower() == "medium"
            ),
            "low": sum(
                1 for f in pre_findings if f.get("severity", "").lower() == "low"
            ),
        }

        # -----------------------------------------------
        # 2) Classification từ diff
        # -----------------------------------------------
        classified = self._normalize_and_classify(diff_data)

        success_findings = classified.get("fixed", [])
        failed_findings = classified.get("failed", [])
        manual_findings = []

        for item in classified.get("manual", []):
            exec_out = item.get("execution_output", {}) or {}

            manual_findings.append(
                {
                    # Identity
                    "finding_uid": item.get("finding_uid"),
                    "finding_id": item.get("finding_id"),
                    "event_code": item.get("before", {}).get("event_code"),
                    # Core finding info
                    "description": item.get("description"),
                    "severity": item.get("before", {}).get("severity"),
                    "service": item.get("service"),
                    "resource": (
                        exec_out.get("resource")
                        or item.get("resource")
                        or item.get("before", {}).get("resource")
                        or "Account-level / Multiple S3 buckets"
                    ),
                    # Manual flags
                    "manual_required": True,
                    # Reason & guidance
                    "manual_reason": exec_out.get("reason")
                    or "This finding requires manual remediation.",
                    "remaining_actions": exec_out.get("remaining_actions", []),
                    # Tool metadata
                    "tool": {
                        "name": item.get("tool_name"),
                        "description": item.get("tool_description"),
                    },
                }
            )

        # -----------------------------------------------
        # 3) Pre-remediation summary
        # -----------------------------------------------
        pre_remediation_data = {
            "total": total_pre,
            "pass": pre_pass,
            "fail": pre_fail,
            "severity": severity_pre,
        }

        # -----------------------------------------------
        # 4) Findings Summary Table
        # -----------------------------------------------
        findings_summary = self._build_findings_summary(
            pre_findings, post_findings, diff_data
        )

        # -----------------------------------------------
        # 5) Post-remediation
        # -----------------------------------------------
        post_remediation_data = {
            "initial_pass": pre_pass,
            "initial_fail": pre_fail,
            "final_pass": post_pass,
            "final_fail": post_fail,
            "fixed": len(success_findings),
            "failed": len(failed_findings),
            "manual": len(manual_findings),
        }

        # -----------------------------------------------
        # RETURN VỀ REPORT AGENT
        # -----------------------------------------------
        return {
            "pre_remediation_data": pre_remediation_data,
            "post_remediation_data": post_remediation_data,
            "findings_summary": findings_summary,
            "success_findings": success_findings,
            "failed_findings": failed_findings,
            "manual_findings": manual_findings,
            "raw_pre_findings": pre_findings,
            "pre_findings": pre_findings,
            "meta": meta,
        }

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
            with open("data/analysis_diff.json", "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"   ❌ Lỗi lưu file: {e}")

    def _print_custom_log(self, s):
        """In log theo format chính xác của user"""
        print("")
        print("-" * 40)
        print(" FINDINGS SUMMARY")
        print("-" * 40)
        print(f"• Total findings (pre)  : {s['total_pre']}")
        print(f"• Total findings (post) : {s['total_post']}")
        print("")

        print("-" * 40)
        print(" STATUS BREAKDOWN")
        print("-" * 40)
        print(f"• PASS (pre)  : {s['pass_pre']}")
        print(f"• FAIL (pre)  : {s['fail_pre']}")
        print(f"• PASS (post) : {s['pass_post']}")
        print(f"• FAIL (post) : {s['fail_post']}")
        print("")

        print("-" * 40)
        print(" REMEDIATION RESULTS")
        print("-" * 40)
        print(f"• Remediate Pass      : {s['remediate_pass']}")
        print(f"• Remediate Fail      : {s['remediate_fail']}")
        print(f"• Manual Required     : {s['manual_required']}")
        print("")

        print("-" * 40)
        print(" CHANGES AFTER REMEDIATION")
        print("-" * 40)
        print(f"• Fixed (FAIL → PASS)       : {s['fixed']}")
        print(f"• New FAIL (PASS → FAIL)    : {s['new_fail']}")
        print(f"• PASS unchanged            : {s['pass_unchanged']}")
        print(f"• FAIL unchanged            : {s['fail_unchanged']}")
        print("")

        print("-" * 40)
        print(" OUTPUT")
        print("-" * 40)
        print(f"• Enriched diff saved to: data/analysis_diff.json")
        print("")
        print("[AnalysisAgent] Completed.")

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
            tool = next((t for t in REMEDIATION_TOOLS if t.name == tool_name), None)
            if tool is None:
                return {
                    "error": f"Tool '{tool_name}' not found in REMEDIATION_TOOLS."
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
            tool = next((t for t in REMEDIATION_TOOLS if t.name == tool_name), None)
            if not tool:
                return f"Tool not found: {tool_name}"

            func = getattr(tool, "func", None)
            if func is None:
                return f"Tool '{tool_name}' has no implementation."

            return inspect.getsource(func)

        except Exception as e:
            return f"Error loading tool source: {e}"

