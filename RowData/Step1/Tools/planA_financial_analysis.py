from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PlanAResult:
    ok: bool
    analysis_text: str | None = None
    pdf_path: str | None = None
    html_path: str | None = None
    json_path: str | None = None
    error: str | None = None


def _guess_financial_mcp_dir() -> Path | None:
    env = os.getenv('FINANCIAL_MCP_DIR') or os.getenv('MY_FINANCIAL_MCP_DIR')
    if env:
        p = Path(env).expanduser().resolve()
        if p.exists():
            return p

    # Heuristic for this machine layout: d:\新建文件夹\MyFinancialProject\FinancialMCP
    anchor = Path(__file__).resolve().anchor  # e.g. 'd:\\'
    candidates = [
        Path(anchor) / '新建文件夹' / 'MyFinancialProject' / 'FinancialMCP',
        Path(anchor) / 'MyFinancialProject' / 'FinancialMCP',
    ]
    for c in candidates:
        if (c / 'package.json').exists() and (c / 'build' / 'tools' / 'planAReportPdf.js').exists():
            return c
    return None


def _get_tushare_token() -> str | None:
    token = os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_API_TOKEN")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _get_node_executable() -> str | None:
    node_env = os.getenv("NODE_EXE") or os.getenv("NODE_PATH")
    if node_env:
        node_path = Path(node_env).expanduser().resolve()
        if node_path.exists():
            return str(node_path)
    return shutil.which("node")


def _normalize_cn_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if "." in s:
        s = s.split(".", 1)[0]
    return s


def _eastmoney_fetch(report_name: str, security_code: str, page_size: int = 5) -> list[dict[str, Any]]:
    base = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": report_name,
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{security_code}")',
        "pageNumber": 1,
        "pageSize": page_size,
        "sortColumns": "REPORT_DATE",
        "sortTypes": -1,
    }
    url = f"{base}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=20) as resp:  # nosec B310
        raw = resp.read().decode("utf-8", errors="ignore")
    payload = json.loads(raw)
    data = payload.get("result", {}).get("data")
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


def _to_period(date_str: str | None) -> str | None:
    if not isinstance(date_str, str):
        return None
    s = date_str.strip()
    if not s:
        return None
    if "-" in s:
        parts = s.split(" ")[0].split("-")
        if len(parts) == 3:
            return "".join(parts)
    if len(s) >= 8 and s[:8].isdigit():
        return s[:8]
    return None


def _parse_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _yoy_percent(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None:
        return None
    if prev == 0:
        return None
    return round(((cur - prev) / abs(prev)) * 100.0, 4)


def _delta(cur: float | None, prev: float | None) -> float | None:
    if cur is None or prev is None:
        return None
    return round(cur - prev, 4)


def _build_periods_from_cn_data(period: str, records: dict[str, dict[str, Any]]) -> list[str]:
    base = (period or "").strip()
    if len(base) == 8 and base.isdigit():
        y = int(base[:4])
        md = base[4:]
        candidates = [f"{y}{md}", f"{y-1}{md}", f"{y-2}{md}"]
    else:
        candidates = []

    out: list[str] = []
    for p in candidates:
        if p in records:
            out.append(p)

    available = [p for p in records.keys() if len(p) == 8 and p.isdigit()]
    available.sort(reverse=True)

    if not out and len(base) == 8 and base.isdigit():
        base_int = int(base)
        not_after = [p for p in available if int(p) <= base_int]
        if not_after:
            out = not_after[:3]

    if not out:
        out = available[:3]

    # Ensure up to 3 columns, prefer available data, then fall back to inferred years.
    if len(out) < 3:
        for p in available:
            if len(out) >= 3:
                break
            if p not in out:
                out.append(p)

    if len(out) < 3 and len(base) == 8 and base.isdigit():
        y = int(base[:4])
        md = base[4:]
        for p in [f"{y-1}{md}", f"{y-2}{md}"]:
            if len(out) >= 3:
                break
            if p not in out:
                out.append(p)

    return out[:3]


def _generate_planA_analysis_public_cn(*, symbol: str, period: str, report_id: str) -> PlanAResult:
    security_code = _normalize_cn_symbol(symbol)
    if not security_code:
        return PlanAResult(ok=False, error="CN 代码为空")

    def index_by_period(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            p = _to_period(r.get("REPORT_DATE"))
            if not p:
                continue
            out[p] = r
        return out

    def fetch_all(page_size: int) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        income_rows = _eastmoney_fetch("RPT_F10_FINANCE_GINCOME", security_code, page_size=page_size)
        balance_rows = _eastmoney_fetch("RPT_F10_FINANCE_GBALANCE", security_code, page_size=page_size)
        cashflow_rows = _eastmoney_fetch("RPT_F10_FINANCE_GCASHFLOW", security_code, page_size=page_size)

        income_by = index_by_period(income_rows)
        balance_by = index_by_period(balance_rows)
        cash_by = index_by_period(cashflow_rows)
        all_periods = {**income_by, **balance_by, **cash_by}
        return income_by, balance_by, cash_by, all_periods

    income_by, balance_by, cash_by, all_periods = fetch_all(page_size=10)

    base_period = (period or "").strip()
    if base_period.isdigit() and len(base_period) == 8 and base_period not in all_periods:
        income_by, balance_by, cash_by, all_periods = fetch_all(page_size=80)
    if not all_periods:
        return PlanAResult(ok=False, error="公开数据源无返回，请检查代码或稍后重试")

    display_periods = _build_periods_from_cn_data(period, all_periods)

    periods_payload: list[dict[str, Any]] = []
    for p in display_periods:
        inc = income_by.get(p, {})
        bal = balance_by.get(p, {})
        cf = cash_by.get(p, {})

        revenue = _parse_float(inc.get("TOTAL_OPERATE_INCOME"))
        total_profit = _parse_float(inc.get("TOTAL_PROFIT"))
        net_profit = _parse_float(inc.get("PARENT_NETPROFIT"))
        if net_profit is None:
            net_profit = _parse_float(inc.get("NETPROFIT"))

        total_assets = _parse_float(bal.get("TOTAL_ASSETS"))
        total_liab = _parse_float(bal.get("TOTAL_LIABILITIES"))
        equity = _parse_float(bal.get("TOTAL_EQUITY"))
        if equity is None:
            equity = _parse_float(bal.get("TOTAL_PARENT_EQUITY"))

        operating_cf = _parse_float(cf.get("NETCASH_OPERATE"))

        # Eastmoney values are in 元. Convert to 万元 for Step4 formatter (which divides by 10000 to show 亿).
        def to_wan(v: float | None) -> float | None:
            return None if v is None else v / 10000.0

        revenue_w = to_wan(revenue)
        total_profit_w = to_wan(total_profit)
        net_profit_w = to_wan(net_profit)
        total_assets_w = to_wan(total_assets)
        total_liab_w = to_wan(total_liab)
        equity_w = to_wan(equity)
        operating_cf_w = to_wan(operating_cf)

        debt_ratio = None
        if total_assets and total_liab:
            debt_ratio = round((total_liab / total_assets) * 100.0, 4)

        net_margin = None
        if revenue and net_profit is not None and revenue != 0:
            net_margin = round((net_profit / revenue) * 100.0, 4)

        roe = None
        if equity and net_profit is not None and equity != 0:
            roe = round((net_profit / equity) * 100.0, 4)

        prev_period = None
        if len(p) == 8 and p.isdigit():
            prev_period = f"{int(p[:4]) - 1}{p[4:]}"

        prev_inc = income_by.get(prev_period or "", {})
        prev_bal = balance_by.get(prev_period or "", {})
        prev_cf = cash_by.get(prev_period or "", {})

        prev_revenue = _parse_float(prev_inc.get("TOTAL_OPERATE_INCOME"))
        prev_total_profit = _parse_float(prev_inc.get("TOTAL_PROFIT"))
        prev_net_profit = _parse_float(prev_inc.get("PARENT_NETPROFIT"))
        if prev_net_profit is None:
            prev_net_profit = _parse_float(prev_inc.get("NETPROFIT"))
        prev_assets = _parse_float(prev_bal.get("TOTAL_ASSETS"))
        prev_liab = _parse_float(prev_bal.get("TOTAL_LIABILITIES"))
        prev_equity = _parse_float(prev_bal.get("TOTAL_EQUITY"))
        if prev_equity is None:
            prev_equity = _parse_float(prev_bal.get("TOTAL_PARENT_EQUITY"))
        prev_ocf = _parse_float(prev_cf.get("NETCASH_OPERATE"))

        periods_payload.append(
            {
                "period": p,
                "label": f"{p[:4]}年年报" if p.endswith("1231") else p,
                "values": {
                    "period": p,
                    "income": {
                        "revenue": revenue_w,
                        "total_profit": total_profit_w,
                        "net_profit": net_profit_w,
                    },
                    "balance": {
                        "total_assets": total_assets_w,
                        "total_liab": total_liab_w,
                        "equity": equity_w,
                    },
                    "cashflow": {
                        "operating_cf": operating_cf_w,
                    },
                    "ratios": {
                        "debt_to_assets_pct": debt_ratio,
                        "current_ratio": None,
                        "quick_ratio": None,
                        "gross_margin_pct": None,
                        "net_margin_pct": net_margin,
                        "roe_pct": roe,
                        "roa_pct": None,
                        "basic_eps": None,
                        "diluted_eps": None,
                        "bps": None,
                        "ocfps": None,
                    },
                },
                "yoy": {
                    "revenue_pct": _yoy_percent(revenue, prev_revenue),
                    "total_profit_pct": _yoy_percent(total_profit, prev_total_profit),
                    "net_profit_pct": _yoy_percent(net_profit, prev_net_profit),
                    "operating_cf_pct": _yoy_percent(operating_cf, prev_ocf),
                    "total_assets_pct": _yoy_percent(total_assets, prev_assets),
                    "total_liab_pct": _yoy_percent(total_liab, prev_liab),
                    "equity_pct": _yoy_percent(equity, prev_equity),
                },
                "delta": {
                    "debt_to_assets_pct_points": None,
                    "roe_pct_points": None,
                    "roa_pct_points": None,
                    "gross_margin_pct_points": None,
                    "net_margin_pct_points": None,
                },
                "compare_period": prev_period,
            }
        )

    first = periods_payload[0]
    analysis_text = (
        f"【PlanA 财务摘要】{first['period']}（{first['label']}）\n"
        f"- 营收：{first['values']['income']['revenue'] if first['values']['income']['revenue'] is not None else '—'}（同比 {first['yoy']['revenue_pct'] if first['yoy']['revenue_pct'] is not None else '—'}）\n"
        f"- 归母/净利润：{first['values']['income']['net_profit'] if first['values']['income']['net_profit'] is not None else '—'}（同比 {first['yoy']['net_profit_pct'] if first['yoy']['net_profit_pct'] is not None else '—'}）\n"
        f"- 经营现金流：{first['values']['cashflow']['operating_cf'] if first['values']['cashflow']['operating_cf'] is not None else '—'}（同比 {first['yoy']['operating_cf_pct'] if first['yoy']['operating_cf_pct'] is not None else '—'}）\n"
        f"- 总资产：{first['values']['balance']['total_assets'] if first['values']['balance']['total_assets'] is not None else '—'}（同比 {first['yoy']['total_assets_pct'] if first['yoy']['total_assets_pct'] is not None else '—'}）\n"
        f"- 总负债：{first['values']['balance']['total_liab'] if first['values']['balance']['total_liab'] is not None else '—'}（同比 {first['yoy']['total_liab_pct'] if first['yoy']['total_liab_pct'] is not None else '—'}）\n"
        f"- 资产负债率：{first['values']['ratios']['debt_to_assets_pct'] if first['values']['ratios']['debt_to_assets_pct'] is not None else '—'}（较上年 —）\n"
        f"- 盈利能力：毛利率 —；净利率 {first['values']['ratios']['net_margin_pct'] if first['values']['ratios']['net_margin_pct'] is not None else '—'}；ROE {first['values']['ratios']['roe_pct'] if first['values']['ratios']['roe_pct'] is not None else '—'}；ROA —\n"
        f"- 偿债能力：流动比率 —；速动比率 —"
    )

    out_dir = Path(__file__).resolve().parents[1] / "Rubbish" / "planA_public"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{report_id}_CN_{security_code}_{period}_public.report.json"
    html_path = out_dir / f"{report_id}_CN_{security_code}_{period}_public.html"
    report_payload = {
        "report_id": report_id,
        "market": "CN",
        "symbol": security_code,
        "input_period": period,
        "display_periods": display_periods,
        "analysis_text": analysis_text,
        "periods": periods_payload,
        "note": {
            "cn_money_unit_assumption": "公开数据源（Eastmoney），金额已转换为万元后再展示为“亿”",
            "us_money_unit_assumption": "—",
        },
    }
    json_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    columns = [p.get("label") for p in periods_payload if isinstance(p, dict)]
    def _safe(v: Any) -> str:
        return "—" if v is None else str(v)

    rows = [
        ("营业总收入(亿)", [p.get("values", {}).get("income", {}).get("revenue") for p in periods_payload]),
        ("同比(%)", [p.get("yoy", {}).get("revenue_pct") for p in periods_payload]),
        ("利润总额(亿)", [p.get("values", {}).get("income", {}).get("total_profit") for p in periods_payload]),
        ("同比(%)", [p.get("yoy", {}).get("total_profit_pct") for p in periods_payload]),
        ("净利润(亿)", [p.get("values", {}).get("income", {}).get("net_profit") for p in periods_payload]),
        ("同比(%)", [p.get("yoy", {}).get("net_profit_pct") for p in periods_payload]),
        ("资产合计(亿)", [p.get("values", {}).get("balance", {}).get("total_assets") for p in periods_payload]),
        ("同比(%)", [p.get("yoy", {}).get("total_assets_pct") for p in periods_payload]),
        ("负债总计(亿)", [p.get("values", {}).get("balance", {}).get("total_liab") for p in periods_payload]),
        ("同比(%)", [p.get("yoy", {}).get("total_liab_pct") for p in periods_payload]),
        ("经营现金流(亿)", [p.get("values", {}).get("cashflow", {}).get("operating_cf") for p in periods_payload]),
        ("同比(%)", [p.get("yoy", {}).get("operating_cf_pct") for p in periods_payload]),
        ("资产负债率(%)", [p.get("values", {}).get("ratios", {}).get("debt_to_assets_pct") for p in periods_payload]),
        ("净利率(%)", [p.get("values", {}).get("ratios", {}).get("net_margin_pct") for p in periods_payload]),
        ("ROE(%)", [p.get("values", {}).get("ratios", {}).get("roe_pct") for p in periods_payload]),
    ]

    html = [
        "<!doctype html>",
        "<html lang=\"zh-CN\">",
        "<head>",
        "<meta charset=\"utf-8\" />",
        f"<title>PlanA 财务摘要 {security_code}</title>",
        "<style>",
        "body{font-family:Microsoft YaHei,Arial,sans-serif;padding:24px;}",
        "table{border-collapse:collapse;width:100%;font-size:12px;}",
        "th,td{border:1px solid #ddd;padding:8px;text-align:right;}",
        "th:first-child,td:first-child{text-align:left;}",
        "thead th{background:#1a2b4a;color:#fff;}",
        "</style>",
        "</head>",
        "<body>",
        f"<h2>PlanA 财务摘要（{security_code}）</h2>",
        f"<pre>{analysis_text}</pre>",
        "<h3>财务表格</h3>",
        "<table>",
        "<thead><tr><th>指标</th>" + "".join(f"<th>{c}</th>" for c in columns) + "</tr></thead>",
        "<tbody>",
    ]
    for label, values in rows:
        html.append("<tr>")
        html.append(f"<td>{label}</td>")
        for v in values:
            html.append(f"<td>{_safe(v)}</td>")
        html.append("</tr>")
    html.extend(["</tbody></table>", "</body>", "</html>"])
    html_path.write_text("\n".join(html), encoding="utf-8")

    return PlanAResult(
        ok=True,
        analysis_text=analysis_text,
        json_path=str(json_path),
        html_path=str(html_path),
    )


def _parse_json_from_output(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    lines = [ln for ln in text.splitlines() if ln.strip()]
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].lstrip().startswith("{"):
            candidate = "\n".join(lines[i:])
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
    return None


def _planA_report_has_values(report_payload: dict[str, Any]) -> bool:
    if not isinstance(report_payload, dict):
        return False
    periods = report_payload.get("periods")
    if not isinstance(periods, list) or not periods:
        return False

    def has_number(v: Any) -> bool:
        if isinstance(v, bool):
            return False
        if isinstance(v, (int, float)):
            return True
        return False

    for p in periods:
        if not isinstance(p, dict):
            continue
        values = p.get("values")
        if isinstance(values, dict):
            for group in ("income", "balance", "cashflow", "ratios"):
                g = values.get(group)
                if isinstance(g, dict):
                    if any(has_number(v) for v in g.values()):
                        return True
        for group in ("yoy", "delta"):
            g = p.get(group)
            if isinstance(g, dict):
                if any(has_number(v) for v in g.values()):
                    return True
    return False


def generate_planA_analysis(*, market: str, symbol: str, period: str, report_id: str) -> PlanAResult:
    """Call FinancialMCP PlanA generator and return its analysis + file paths.

    Requirements:
    - Node.js available in PATH
    - FinancialMCP installed deps (playwright)
    - TUSHARE_TOKEN env var configured

    Optional config:
    - FINANCIAL_MCP_DIR env var pointing to FinancialMCP folder
    """

    mcp_dir = _guess_financial_mcp_dir()
    if not mcp_dir:
        return PlanAResult(ok=False, error='未找到 FinancialMCP 目录：请设置环境变量 FINANCIAL_MCP_DIR')

    market = (market or "").strip().upper() or "CN"
    token = _get_tushare_token()

    node_exe = _get_node_executable()
    if not node_exe:
        if market == "CN":
            return _generate_planA_analysis_public_cn(symbol=symbol, period=period, report_id=report_id)
        return PlanAResult(ok=False, error='未找到 Node.js：请安装 Node.js 或设置 NODE_EXE 环境变量')

    cli_path = mcp_dir / "scripts" / "planA_report_cli.mjs"
    if not cli_path.exists():
        return PlanAResult(ok=False, error=f"未找到 PlanA CLI：{cli_path}")

    job = {
        'report_id': report_id,
        'market': market,
        'symbol': symbol,
        'period': period,
        'output': {'out_dir': './PlanA/_out', 'format': 'pdf'},
        'compare': {'mode': 'auto_yoy'},
    }

    try:
        with tempfile.TemporaryDirectory(prefix='planA_job_') as td:
            job_path = Path(td) / 'job.json'
            job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')

            cmd = [node_exe, str(cli_path), '--job', str(job_path)]
            env = os.environ.copy()
            if token:
                env["TUSHARE_TOKEN"] = token
            proc = subprocess.run(
                cmd,
                cwd=str(mcp_dir),
                capture_output=True,
                text=True,
                env=env,
                timeout=180,
            )

            if proc.returncode != 0:
                stderr = (proc.stderr or '').strip()
                stdout = (proc.stdout or '').strip()
                msg = stderr or stdout or f'PlanA CLI exited with code {proc.returncode}'
                if market == "CN":
                    return _generate_planA_analysis_public_cn(symbol=symbol, period=period, report_id=report_id)
                return PlanAResult(ok=False, error=msg)

            stdout = (proc.stdout or '').strip()
            payload = _parse_json_from_output(stdout)
            if payload is None:
                stderr = (proc.stderr or '').strip()
                msg = stderr or stdout or 'PlanA 未返回可解析的 JSON 输出'
                if market == "CN":
                    return _generate_planA_analysis_public_cn(symbol=symbol, period=period, report_id=report_id)
                return PlanAResult(ok=False, error=msg)
            if not payload.get('ok'):
                if market == "CN":
                    return _generate_planA_analysis_public_cn(symbol=symbol, period=period, report_id=report_id)
                return PlanAResult(ok=False, error=str(payload))

            json_path = payload.get('json_path')
            if isinstance(json_path, str) and json_path.strip():
                try:
                    report_payload = json.loads(Path(json_path).read_text(encoding='utf-8'))
                except Exception:
                    report_payload = None
                if report_payload is not None and not _planA_report_has_values(report_payload):
                    if market == "CN":
                        return _generate_planA_analysis_public_cn(symbol=symbol, period=period, report_id=report_id)
                    return PlanAResult(
                        ok=False,
                        error='PlanA 数据为空：请配置 TUSHARE_TOKEN 并重试生成',
                    )

            return PlanAResult(
                ok=True,
                analysis_text=payload.get('analysis_text'),
                pdf_path=payload.get('pdf_path'),
                html_path=payload.get('html_path'),
                json_path=payload.get('json_path'),
            )
    except subprocess.TimeoutExpired:
        if market == "CN":
            return _generate_planA_analysis_public_cn(symbol=symbol, period=period, report_id=report_id)
        return PlanAResult(ok=False, error='PlanA 生成超时（>180s），请稍后重试或检查网络/Token）')
    except Exception as e:  # noqa: BLE001
        if market == "CN":
            return _generate_planA_analysis_public_cn(symbol=symbol, period=period, report_id=report_id)
        return PlanAResult(ok=False, error=str(e))
