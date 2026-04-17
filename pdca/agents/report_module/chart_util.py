import matplotlib
matplotlib.use("Agg")  # non-interactive backend for server/CI
import matplotlib.pyplot as plt
import numpy as np
import os


# ---------------------------------------------------------
# PIE CHART: PASS vs FAIL
# ---------------------------------------------------------
def make_pass_fail_pie(pass_count, fail_count, output_path):
    import matplotlib.pyplot as plt

    try:
        p = int(pass_count or 0)
    except (ValueError, TypeError):
        p = 0

    try:
        f = int(fail_count or 0)
    except (ValueError, TypeError):
        f = 0

    total = p + f

    fig = plt.figure(figsize=(4, 4))
    try:
        if total == 0:
            plt.text(0.5, 0.5, "No data", ha="center", va="center",
                     fontsize=14, color="#999", transform=fig.transFigure)
            plt.axis("off")
        else:
            labels = ["PASS", "FAIL"]
            values = [p, f]
            colors = ["#4CAF50", "#F44336"]
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
    finally:
        plt.close()


# ---------------------------------------------------------
# BAR CHART: SEVERITY BREAKDOWN
# ---------------------------------------------------------
def make_severity_bar(severity_dict, output_path):
    import matplotlib.pyplot as plt

    if not severity_dict:
        severity_dict = {"critical": 0, "high": 0, "medium": 0, "low": 0}

    labels = list(severity_dict.keys())
    values = [int(severity_dict.get(k, 0) or 0) for k in labels]
    colors = ["#B71C1C", "#E65100", "#FFB300", "#1E88E5"]

    fig = plt.figure(figsize=(5, 4))
    try:
        if all(v == 0 for v in values):
            plt.text(0.5, 0.5, "No data", ha="center", va="center",
                     fontsize=14, color="#999", transform=fig.transFigure)
            plt.axis("off")
        else:
            plt.bar(labels, values, color=colors)
            plt.title("Severity Breakdown")
            plt.xlabel("Severity Level")
            plt.ylabel("Number of Findings")
            for i, v in enumerate(values):
                plt.text(i, v + 0.1, str(v), ha="center")

        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close()


# ---------------------------------------------------------
# RADAR CHART: Maturity Domain Scores (5-axis)
# ---------------------------------------------------------
def make_domain_radar(domain_scores: dict, output_path: str):
    """5-axis radar/spider chart showing maturity score per domain.

    Args:
        domain_scores: {"Data Protection": 75.0, "Identity & Access Management": 60.0, ...}
        output_path: path to save PNG
    """
    if not domain_scores:
        domain_scores = {}

    labels = list(domain_scores.keys())
    values = [float(domain_scores.get(l, 0)) for l in labels]
    n = len(labels)

    fig = plt.figure(figsize=(6, 6))
    try:
        if n == 0:
            plt.text(0.5, 0.5, "No data", ha="center", va="center",
                     fontsize=14, color="#999", transform=fig.transFigure)
            plt.axis("off")
        else:
            # Compute angles for each axis
            angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
            # Close the polygon
            values_closed = values + [values[0]]
            angles_closed = angles + [angles[0]]

            ax = fig.add_subplot(111, polar=True)

            # Reference circles at 25, 50, 75
            for ref in [25, 50, 75]:
                ref_vals = [ref] * (n + 1)
                ax.plot(angles_closed, ref_vals, color="#E0E0E0", linewidth=0.5, linestyle="--")

            # Plot data
            ax.plot(angles_closed, values_closed, color="#1565C0", linewidth=2)
            ax.fill(angles_closed, values_closed, color="#1E88E5", alpha=0.25)

            # Axis labels with scores
            ax.set_xticks(angles)
            tick_labels = [f"{l}\n({v:.0f})" for l, v in zip(labels, values)]
            ax.set_xticklabels(tick_labels, fontsize=8, ha="center")

            ax.set_ylim(0, 100)
            ax.set_yticks([25, 50, 75, 100])
            ax.set_yticklabels(["25", "50", "75", "100"], fontsize=7, color="#999")

            ax.set_title("Maturity Profile", fontsize=13, fontweight="bold", pad=20)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close()


# ---------------------------------------------------------
# HORIZONTAL BARS: Stage Completion Progress
# ---------------------------------------------------------
def make_stage_progress(maturity_data: dict, output_path: str):
    """4 horizontal bars showing completion percentage per maturity stage.

    Args:
        maturity_data: full output from MaturityEngine.assess()
        output_path: path to save PNG
    """
    from pdca.agents.report_module.maturity_engine import STAGE_ORDER, STAGE_LABELS

    # Collect all capabilities across domains
    all_caps = []
    for domain in (maturity_data or {}).get("domains", {}).values():
        all_caps.extend(domain.get("capabilities", []))

    # Group by stage and compute completion
    stage_names = []
    completion_pcts = []
    for stage in STAGE_ORDER:
        stage_caps = [c for c in all_caps if c.get("stage") == stage]
        if stage_caps:
            passing = sum(1 for c in stage_caps if c.get("score", 0) >= 50.0)
            pct = passing / len(stage_caps) * 100
        else:
            pct = 0.0
        stage_names.append(STAGE_LABELS.get(stage, stage))
        completion_pcts.append(pct)

    overall_stage = (maturity_data or {}).get("overall_stage", "1 quickwins")

    fig, ax = plt.subplots(figsize=(8, 3))
    try:
        y_pos = range(len(stage_names))
        colors = []
        for pct in completion_pcts:
            if pct >= 70:
                colors.append("#4CAF50")   # green
            elif pct >= 30:
                colors.append("#FFB300")   # yellow/amber
            else:
                colors.append("#F44336")   # red

        bars = ax.barh(y_pos, completion_pcts, color=colors, height=0.5, edgecolor="white")

        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(stage_names, fontsize=10)
        ax.set_xlim(0, 105)
        ax.set_xlabel("Completion %", fontsize=9)
        ax.invert_yaxis()  # Quick Wins at top

        # Label values on bars
        for i, (bar, pct) in enumerate(zip(bars, completion_pcts)):
            label = f"{pct:.0f}%"
            ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2,
                    label, va="center", fontsize=9, fontweight="bold")

        # Highlight current overall stage
        for i, stage in enumerate(STAGE_ORDER):
            if stage == overall_stage:
                bars[i].set_edgecolor("#1565C0")
                bars[i].set_linewidth(2)

        ax.set_title("Stage Completion", fontsize=12, fontweight="bold")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close()


# ---------------------------------------------------------
# GROUPED BAR: Maturity Delta (Pre vs Post)
# ---------------------------------------------------------
def make_maturity_delta_chart(maturity_delta: dict, output_path: str):
    """Grouped bar chart comparing pre vs post maturity score per domain.

    Args:
        maturity_delta: output from MaturityEngine.compute_delta()
        output_path: path to save PNG
    """
    if not maturity_delta:
        fig = plt.figure(figsize=(10, 5))
        try:
            plt.text(0.5, 0.5, "No delta data", ha="center", va="center",
                     fontsize=14, color="#999", transform=fig.transFigure)
            plt.axis("off")
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
        finally:
            plt.close()
        return

    domains_data = maturity_delta.get("domains", {})
    overall = maturity_delta.get("overall", {})

    # Build parallel arrays
    domain_names = []
    pre_scores = []
    post_scores = []
    deltas = []
    stage_changed_flags = []

    for d_id, d_info in domains_data.items():
        domain_names.append(d_info.get("display_name", d_id))
        pre_scores.append(d_info.get("pre_score", 0))
        post_scores.append(d_info.get("post_score", 0))
        deltas.append(d_info.get("score_delta", 0))
        stage_changed_flags.append(d_info.get("stage_changed", False))

    n = len(domain_names)
    x = np.arange(n)
    bar_width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))
    try:
        bars_pre = ax.bar(x - bar_width / 2, pre_scores, bar_width,
                          label="Truoc khac phuc", color="#9E9E9E")
        bars_post = ax.bar(x + bar_width / 2, post_scores, bar_width,
                           label="Sau khac phuc", color="#1E88E5")

        # Delta labels above post bars
        for i, (bar, delta) in enumerate(zip(bars_post, deltas)):
            if delta == 0:
                continue
            color = "#2E7D32" if delta > 0 else "#C62828"
            label = f"{delta:+.1f}"
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5,
                    label, ha="center", va="bottom", fontsize=9,
                    fontweight="bold", color=color)

        # Highlight stage-changed domains
        for i, changed in enumerate(stage_changed_flags):
            if changed:
                bars_post[i].set_edgecolor("#FFD600")
                bars_post[i].set_linewidth(2)

        ax.set_xticks(x)
        # Wrap long domain names
        wrapped = [name.replace(" & ", "\n& ").replace(" - ", "\n- ") for name in domain_names]
        ax.set_xticklabels(wrapped, fontsize=8, ha="center")
        ax.set_ylim(0, 110)
        ax.set_ylabel("Score", fontsize=10)

        # Title + subtitle
        pre_total = overall.get("pre_score", 0)
        post_total = overall.get("post_score", 0)
        total_delta = overall.get("score_delta", 0)
        ax.set_title("Tac dong Khac phuc len Muc do Truong thanh", fontsize=13, fontweight="bold")
        subtitle = f"Diem tong: {pre_total:.1f} \u2192 {post_total:.1f} ({total_delta:+.1f})"
        ax.text(0.5, 1.02, subtitle, transform=ax.transAxes, ha="center", fontsize=10, color="#555")

        ax.legend(loc="upper right", fontsize=9)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
    finally:
        plt.close()
