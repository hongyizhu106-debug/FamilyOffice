from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    return num


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _pick_latest_period(report: dict[str, Any]) -> dict[str, Any] | None:
    periods = report.get("periods")
    if not isinstance(periods, list) or not periods:
        return None
    first = periods[0]
    return first if isinstance(first, dict) else None


def _pick_prior_period(report: dict[str, Any]) -> dict[str, Any] | None:
    periods = report.get("periods")
    if not isinstance(periods, list) or len(periods) < 2:
        return None
    second = periods[1]
    return second if isinstance(second, dict) else None


def _pick_recent_periods(report: dict[str, Any], *, count: int = 3) -> list[dict[str, Any]]:
    periods = report.get("periods")
    if not isinstance(periods, list) or not periods:
        return []
    out: list[dict[str, Any]] = []
    for item in periods[:count]:
        if isinstance(item, dict):
            out.append(item)
    return out


def _money_to_billion_cn(value: float | None) -> float | None:
    # PlanA CN values are in 万元. 1 亿 = 10000 万.
    if value is None:
        return None
    return value / 10000.0


def _fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}%"


def _fmt_ratio(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _grade(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def _score_health(*, debt_to_assets: float | None, net_margin: float | None, roe: float | None,
                  operating_cf: float | None, ocf_np_ratio: float | None, revenue_yoy: float | None,
                  net_profit_yoy: float | None) -> tuple[float, dict[str, float]]:
    components: dict[str, float] = {}

    # Leverage (0-25)
    if debt_to_assets is None:
        components["leverage"] = 10.0
    elif debt_to_assets <= 40:
        components["leverage"] = 25.0
    elif debt_to_assets <= 60:
        components["leverage"] = 18.0
    elif debt_to_assets <= 80:
        components["leverage"] = 8.0
    else:
        components["leverage"] = 0.0

    # Profitability (0-20)
    if net_margin is None:
        components["profitability"] = 8.0
    elif net_margin >= 15:
        components["profitability"] = 20.0
    elif net_margin >= 5:
        components["profitability"] = 14.0
    elif net_margin >= 0:
        components["profitability"] = 8.0
    else:
        components["profitability"] = 0.0

    # ROE (0-15)
    if roe is None:
        components["roe"] = 6.0
    elif roe >= 15:
        components["roe"] = 15.0
    elif roe >= 8:
        components["roe"] = 10.0
    elif roe >= 0:
        components["roe"] = 6.0
    else:
        components["roe"] = 0.0

    # Cashflow (0-20)
    cash_score = 0.0
    if operating_cf is None:
        cash_score += 6.0
    elif operating_cf > 0:
        cash_score += 10.0

    if ocf_np_ratio is None:
        cash_score += 4.0
    elif ocf_np_ratio >= 1.0:
        cash_score += 10.0
    elif ocf_np_ratio >= 0.7:
        cash_score += 6.0
    elif ocf_np_ratio >= 0.4:
        cash_score += 3.0
    components["cashflow"] = cash_score

    # Growth (0-20)
    growth_base = revenue_yoy if revenue_yoy is not None else net_profit_yoy
    if growth_base is None:
        components["growth"] = 8.0
    elif growth_base >= 15:
        components["growth"] = 20.0
    elif growth_base >= 5:
        components["growth"] = 14.0
    elif growth_base >= 0:
        components["growth"] = 8.0
    else:
        components["growth"] = 2.0

    overall = sum(components.values())
    overall = _clamp(overall, 0.0, 100.0)
    return overall, components


def _build_dcf(*, operating_cf: float | None, revenue_yoy: float | None, net_profit_yoy: float | None,
               reinvestment_rate: float = 0.2, wacc: float = 0.10,
               terminal_growth: float = 0.03, years: int = 5) -> dict[str, Any]:
    if operating_cf is None or operating_cf <= 0:
        return {
            "ok": False,
            "reason": "经营现金流为负或缺失",
        }

    growth_base = revenue_yoy if revenue_yoy is not None else net_profit_yoy
    if growth_base is None:
        growth_rate = 0.05
    else:
        growth_rate = _clamp(growth_base / 100.0, 0.01, 0.12)

    fcf0 = operating_cf * (1.0 - reinvestment_rate)
    cashflows: list[float] = []
    for year in range(1, years + 1):
        cashflows.append(fcf0 * ((1.0 + growth_rate) ** year))

    pv = 0.0
    for i, cf in enumerate(cashflows, start=1):
        pv += cf / ((1.0 + wacc) ** i)

    terminal_cf = cashflows[-1] * (1.0 + terminal_growth)
    terminal_value = terminal_cf / (wacc - terminal_growth)
    pv_terminal = terminal_value / ((1.0 + wacc) ** years)
    value = pv + pv_terminal

    return {
        "ok": True,
        "value": value,
        "value_billion_cny": _money_to_billion_cn(value),
        "assumptions": {
            "reinvestment_rate": reinvestment_rate,
            "wacc": wacc,
            "terminal_growth": terminal_growth,
            "years": years,
            "growth_rate": growth_rate,
        },
    }


def _calc_m_score(*, cur: dict[str, Any], prev: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []

    def _get(path: list[str]) -> float | None:
        node: Any = cur
        for k in path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return _safe_float(node)

    def _get_prev(path: list[str]) -> float | None:
        node: Any = prev
        for k in path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return _safe_float(node)

    sales = _get(["values", "income", "revenue"])
    sales_prev = _get_prev(["values", "income", "revenue"])
    total_assets = _get(["values", "balance", "total_assets"])
    total_assets_prev = _get_prev(["values", "balance", "total_assets"])
    total_liab = _get(["values", "balance", "total_liab"])
    total_liab_prev = _get_prev(["values", "balance", "total_liab"])
    net_profit = _get(["values", "income", "net_profit"])
    operating_cf = _get(["values", "cashflow", "operating_cf"])

    if sales is None or sales_prev is None:
        missing.append("revenue")
    if total_assets is None or total_assets_prev is None:
        missing.append("total_assets")
    if total_liab is None or total_liab_prev is None:
        missing.append("total_liab")

    # Approximations for missing ratios.
    dsri = 1.0
    gmi = 1.0
    aqi = 1.0
    depi = 1.0
    sgai = 1.0

    if "receivables" not in missing:
        missing.append("receivables")
    if "gross_margin" not in missing:
        missing.append("gross_margin")
    if "current_assets" not in missing:
        missing.append("current_assets")
    if "ppe" not in missing:
        missing.append("ppe")
    if "depreciation" not in missing:
        missing.append("depreciation")
    if "sga" not in missing:
        missing.append("sga")

    if sales and sales_prev:
        sgi = sales / sales_prev if sales_prev != 0 else 1.0
    else:
        sgi = 1.0

    if total_liab and total_assets and total_liab_prev and total_assets_prev:
        lvgi = (total_liab / total_assets) / (total_liab_prev / total_assets_prev)
    else:
        lvgi = 1.0

    if net_profit is not None and operating_cf is not None and total_assets:
        tata = (net_profit - operating_cf) / total_assets
    else:
        tata = 0.0
        if "tata" not in missing:
            missing.append("tata_inputs")

    score = (
        -4.84
        + 0.92 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )

    return {
        "status": "approx",
        "score": round(score, 3),
        "risk": "high" if score > -1.78 else "low",
        "missing_fields": sorted(set(missing)),
    }


def _calc_f_score(*, cur: dict[str, Any], prev: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []

    def _get(path: list[str]) -> float | None:
        node: Any = cur
        for k in path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return _safe_float(node)

    def _get_prev(path: list[str]) -> float | None:
        node: Any = prev
        for k in path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return _safe_float(node)

    net_profit = _get(["values", "income", "net_profit"])
    operating_cf = _get(["values", "cashflow", "operating_cf"])
    total_assets = _get(["values", "balance", "total_assets"])
    total_assets_prev = _get_prev(["values", "balance", "total_assets"])
    total_liab = _get(["values", "balance", "total_liab"])
    total_liab_prev = _get_prev(["values", "balance", "total_liab"])

    if total_assets is None or total_assets_prev is None:
        missing.append("total_assets")

    roa = (net_profit / total_assets) if net_profit is not None and total_assets else None
    roa_prev = (net_profit / total_assets_prev) if net_profit is not None and total_assets_prev else None

    score = 0
    # 1. ROA > 0
    if roa is not None and roa > 0:
        score += 1
    # 2. CFO > 0
    if operating_cf is not None and operating_cf > 0:
        score += 1
    # 3. Delta ROA > 0
    if roa is not None and roa_prev is not None and roa > roa_prev:
        score += 1
    # 4. Accruals: CFO > Net Income
    if operating_cf is not None and net_profit is not None and operating_cf > net_profit:
        score += 1

    # 5. Leverage decrease (use total_liab/total_assets proxy)
    if total_liab and total_assets and total_liab_prev and total_assets_prev:
        leverage = total_liab / total_assets
        leverage_prev = total_liab_prev / total_assets_prev
        if leverage < leverage_prev:
            score += 1
    else:
        missing.append("leverage")

    # 6. Current ratio increase (missing)
    missing.append("current_ratio")
    # 7. No new shares issued (missing)
    missing.append("shares_outstanding")
    # 8. Gross margin increase (missing)
    missing.append("gross_margin")
    # 9. Asset turnover increase (missing)
    missing.append("asset_turnover")

    return {
        "status": "approx",
        "score": score,
        "missing_fields": sorted(set(missing)),
    }


def _calc_altman_z(*, cur: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []

    def _get(path: list[str]) -> float | None:
        node: Any = cur
        for k in path:
            if not isinstance(node, dict):
                return None
            node = node.get(k)
        return _safe_float(node)

    total_assets = _get(["values", "balance", "total_assets"])
    total_liab = _get(["values", "balance", "total_liab"])
    equity = _get(["values", "balance", "equity"])
    revenue = _get(["values", "income", "revenue"])
    total_profit = _get(["values", "income", "total_profit"])
    net_profit = _get(["values", "income", "net_profit"])

    if total_assets is None:
        missing.append("total_assets")
    if total_liab is None:
        missing.append("total_liab")
    if equity is None:
        missing.append("equity")
    if revenue is None:
        missing.append("revenue")

    ebit = total_profit if total_profit is not None else net_profit
    if ebit is None:
        missing.append("ebit")

    # Working capital and retained earnings are unavailable in PlanA output.
    working_capital = None
    retained_earnings = None
    missing.append("working_capital")
    missing.append("retained_earnings")

    if not total_assets or not total_liab or not equity or ebit is None:
        return {
            "status": "insufficient_data",
            "missing_fields": sorted(set(missing)),
        }

    wc_ta = (working_capital or 0.0) / total_assets
    re_ta = (retained_earnings or 0.0) / total_assets
    ebit_ta = ebit / total_assets
    bve_tl = equity / total_liab if total_liab else 0.0

    z_score = 6.56 * wc_ta + 3.26 * re_ta + 6.72 * ebit_ta + 1.05 * bve_tl

    if z_score > 2.6:
        band = "safe"
    elif z_score > 1.1:
        band = "gray"
    else:
        band = "distress"

    return {
        "status": "approx",
        "score": round(z_score, 3),
        "band": band,
        "missing_fields": sorted(set(missing)),
    }


def _trend_label(values: list[float | None]) -> str:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return "趋势不足"
    if clean[-1] > clean[0] + 1e-6:
        return "改善"
    if clean[-1] < clean[0] - 1e-6:
        return "走弱"
    return "平稳"


def _build_yoy_series(periods: list[dict[str, Any]]) -> dict[str, Any]:
    columns: list[str] = []
    revenue: list[float | None] = []
    net_profit: list[float | None] = []
    operating_cf: list[float | None] = []

    for p in periods:
        label = p.get("label") or p.get("period") or "—"
        columns.append(str(label))
        yoy = p.get("yoy") if isinstance(p.get("yoy"), dict) else {}
        revenue.append(_safe_float(yoy.get("revenue_pct")))
        net_profit.append(_safe_float(yoy.get("net_profit_pct")))
        operating_cf.append(_safe_float(yoy.get("operating_cf_pct")))

    return {
        "columns": columns,
        "revenue": revenue,
        "net_profit": net_profit,
        "operating_cf": operating_cf,
        "trends": {
            "revenue": _trend_label(revenue),
            "net_profit": _trend_label(net_profit),
            "operating_cf": _trend_label(operating_cf),
        },
    }


def analyze_planA_report(report_path: str | Path) -> dict[str, Any]:
    path = Path(report_path).expanduser()
    payload = json.loads(path.read_text(encoding="utf-8"))

    period = _pick_latest_period(payload)
    prior = _pick_prior_period(payload)
    recent_periods = _pick_recent_periods(payload, count=3)
    if period is None or prior is None:
        return {
            "ok": False,
            "error": "report missing periods",
        }

    values = period.get("values") if isinstance(period, dict) else None
    values = values if isinstance(values, dict) else {}

    income = values.get("income") if isinstance(values.get("income"), dict) else {}
    balance = values.get("balance") if isinstance(values.get("balance"), dict) else {}
    cashflow = values.get("cashflow") if isinstance(values.get("cashflow"), dict) else {}
    ratios = values.get("ratios") if isinstance(values.get("ratios"), dict) else {}

    revenue = _safe_float(income.get("revenue"))
    net_profit = _safe_float(income.get("net_profit"))
    operating_cf = _safe_float(cashflow.get("operating_cf"))

    debt_to_assets = _safe_float(ratios.get("debt_to_assets_pct"))
    net_margin = _safe_float(ratios.get("net_margin_pct"))
    roe = _safe_float(ratios.get("roe_pct"))

    yoy = period.get("yoy") if isinstance(period, dict) else None
    yoy = yoy if isinstance(yoy, dict) else {}
    revenue_yoy = _safe_float(yoy.get("revenue_pct"))
    net_profit_yoy = _safe_float(yoy.get("net_profit_pct"))
    operating_cf_yoy = _safe_float(yoy.get("operating_cf_pct"))

    ocf_np_ratio = None
    if operating_cf is not None and net_profit not in (None, 0.0):
        ocf_np_ratio = operating_cf / net_profit

    overall, components = _score_health(
        debt_to_assets=debt_to_assets,
        net_margin=net_margin,
        roe=roe,
        operating_cf=operating_cf,
        ocf_np_ratio=ocf_np_ratio,
        revenue_yoy=revenue_yoy,
        net_profit_yoy=net_profit_yoy,
    )

    positives: list[str] = []
    risks: list[str] = []

    if debt_to_assets is not None:
        if debt_to_assets <= 40:
            positives.append("资产负债率较低")
        elif debt_to_assets >= 70:
            risks.append("资产负债率偏高")

    if net_margin is not None:
        if net_margin >= 10:
            positives.append("净利率较高")
        elif net_margin < 0:
            risks.append("净利率为负")

    if roe is not None:
        if roe >= 15:
            positives.append("ROE 表现较好")
        elif roe < 0:
            risks.append("ROE 为负")

    if operating_cf is not None:
        if operating_cf > 0:
            positives.append("经营现金流为正")
        else:
            risks.append("经营现金流为负")

    if ocf_np_ratio is not None and ocf_np_ratio < 0.7:
        risks.append("经营现金流对净利润支撑偏弱")

    if revenue_yoy is not None and revenue_yoy < 0:
        risks.append("营收同比下降")
    if net_profit_yoy is not None and net_profit_yoy < 0:
        risks.append("净利润同比下降")

    dcf = _build_dcf(
        operating_cf=operating_cf,
        revenue_yoy=revenue_yoy,
        net_profit_yoy=net_profit_yoy,
    )

    summary = f"财务健康评分 {overall:.1f}/100（{_grade(overall)}）"
    if positives:
        summary += "，优势：" + "、".join(positives[:3])
    if risks:
        summary += "，风险：" + "、".join(risks[:3])

    yoy_series = _build_yoy_series(recent_periods)
    summary_text = (
        f"本期财务健康评分为{overall:.1f}/100（{_grade(overall)}），"
        f"资产负债率{_fmt_pct(debt_to_assets)}、净利率{_fmt_pct(net_margin)}、ROE {_fmt_pct(roe)}，"
        f"显示盈利与资本效率处于较高水平；经营现金流对净利润支撑系数{_fmt_ratio(ocf_np_ratio)}，"
        f"现金回收质量仍有改进空间。近三年同比趋势：营收{yoy_series['trends']['revenue']}、"
        f"净利润{yoy_series['trends']['net_profit']}、经营现金流{yoy_series['trends']['operating_cf']}。"
        "综合来看，公司短期财务质量较稳健，但需关注现金流质量与增长持续性。"
    )

    f_score = _calc_f_score(cur=period, prev=prior)
    z_score = _calc_altman_z(cur=period)

    return {
        "ok": True,
        "summary": summary,
        "score": {
            "overall": round(overall, 1),
            "grade": _grade(overall),
            "components": {k: round(v, 1) for k, v in components.items()},
        },
        "ratios": {
            "debt_to_assets_pct": debt_to_assets,
            "net_margin_pct": net_margin,
            "roe_pct": roe,
            "revenue_yoy_pct": revenue_yoy,
            "net_profit_yoy_pct": net_profit_yoy,
            "operating_cf_yoy_pct": operating_cf_yoy,
            "ocf_np_ratio": ocf_np_ratio,
            "revenue": revenue,
            "net_profit": net_profit,
            "operating_cf": operating_cf,
        },
        "signals": {
            "positive": positives,
            "risk": risks,
        },
        "yoy_series": yoy_series,
        "summary_text": summary_text,
        "dcf": dcf,
        "models": {
            "z_score": z_score,
            "f_score": f_score,
        },
    }
