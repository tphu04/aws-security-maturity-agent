import matplotlib.pyplot as plt
import os


# ---------------------------------------------------------
# PIE CHART: PASS vs FAIL
# ---------------------------------------------------------
def make_pass_fail_pie(pass_count, fail_count, output_path):
    import matplotlib.pyplot as plt

    # Ép kiểu an toàn
    try:
        p = int(pass_count or 0)
    except:
        p = 0

    try:
        f = int(fail_count or 0)
    except:
        f = 0

    total = p + f

    # Tránh chia cho 0 → NaN
    if total == 0:
        # Hiển thị placeholder để không crash
        p, f = 1, 1

    labels = ["PASS", "FAIL"]
    values = [p, f]
    colors = ["#4CAF50", "#F44336"]

    plt.figure(figsize=(4, 4))
    plt.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=140,
        colors=colors,
        wedgeprops={"linewidth": 1, "edgecolor": "white"},
    )
    plt.title("Pass vs Fail")
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


# ---------------------------------------------------------
# BAR CHART: SEVERITY BREAKDOWN
# ---------------------------------------------------------
def make_severity_bar(severity_dict, output_path):
    import matplotlib.pyplot as plt

    # severity_dict có thể None → fallback rỗng
    if not severity_dict:
        severity_dict = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    labels = list(severity_dict.keys())
    values = [int(severity_dict.get(k, 0) or 0) for k in labels]
    colors = ["#B71C1C", "#E65100", "#FFB300", "#1E88E5"]

    plt.figure(figsize=(5, 4))
    plt.bar(labels, values, color=colors)
    plt.title("Severity Breakdown")
    plt.xlabel("Severity Level")
    plt.ylabel("Number of Findings")

    # text trên đầu cột
    for i, v in enumerate(values):
        plt.text(i, v + 0.1, str(v), ha="center")

    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
