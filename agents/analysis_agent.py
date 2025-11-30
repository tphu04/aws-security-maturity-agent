import json

class AnalysisAgent:

    def __init__(self, before_path="data/pre_scan.json", after_path="data/post_scan.json"):
        self.before_path = before_path
        self.after_path = after_path

    def load(self):
        before = json.load(open(self.before_path))
        after = json.load(open(self.after_path))
        return before["findings"], after["findings"]

    def run(self):
        before, after = self.load()

        before_map = {f["finding_uid"]: f for f in before}
        after_map  = {f["finding_uid"]: f for f in after}

        diff_result = []

        # A. Finding hiện hữu trước remediation
        for uid, bf in before_map.items():
            af = after_map.get(uid)
            if not af:
                diff_result.append({
                    "finding_uid": uid,
                    "before": bf["status"],
                    "after": None,
                    "change": "Removed"
                })
            else:
                if bf["status"] != af["status"]:
                    diff_result.append({
                        "finding_uid": uid,
                        "before": bf["status"],
                        "after": af["status"],
                        "change": "Changed"
                    })
                else:
                    diff_result.append({
                        "finding_uid": uid,
                        "before": bf["status"],
                        "after": af["status"],
                        "change": "Unchanged"
                    })

        # B. Finding mới phát sinh sau remediation
        for uid, af in after_map.items():
            if uid not in before_map:
                diff_result.append({
                    "finding_uid": uid,
                    "before": None,
                    "after": af["status"],
                    "change": "NewIssue"
                })

        return diff_result
