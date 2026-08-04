import { TUSHARE_CONFIG } from '../config.js';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import https from 'node:https';
import { chromium } from 'playwright';

type Market = 'CN' | 'US';

type PlanAReportArgs = {
  report_id: string;
  market: Market;
  symbol: string;
  period: string; // YYYYMMDD
  output?: { out_dir?: string; format?: 'pdf' };
  compare?: { mode?: 'auto_yoy' | 'manual'; compare_period?: string };
};

type NumberLike = number | null | undefined;

function isValidPeriod(p: string): boolean {
  return /^\d{8}$/.test(p);
}

function parseNum(v: any): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function formatPeriodLabel(period: string): string {
  if (!isValidPeriod(period)) return period;
  const y = period.slice(0, 4);
  const mmdd = period.slice(4);
  if (mmdd === '1231') return `${y}年年报`;
  if (mmdd === '0930') return `${y}年三季报`;
  if (mmdd === '0630') return `${y}年中报`;
  if (mmdd === '0331') return `${y}年一季报`;
  return `${y}-${period.slice(4, 6)}-${period.slice(6, 8)}`;
}

function subtractYear(period: string, deltaYears: number): string {
  const y = Number(period.slice(0, 4));
  const mmdd = period.slice(4);
  return `${String(y - deltaYears).padStart(4, '0')}${mmdd}`;
}

function formatPercent(v: NumberLike): string {
  if (v === null || v === undefined) return '—';
  return `${v.toFixed(2)}%`;
}

function yoyPercent(current: NumberLike, previous: NumberLike): number | null {
  if (current === null || current === undefined) return null;
  if (previous === null || previous === undefined) return null;
  if (previous === 0) return null;
  return (current / previous - 1) * 100;
}

function delta(current: NumberLike, previous: NumberLike): number | null {
  if (current === null || current === undefined) return null;
  if (previous === null || previous === undefined) return null;
  return current - previous;
}

function formatNumber(v: NumberLike, digits = 2): string {
  if (v === null || v === undefined) return '—';
  return v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function buildAnalysisText(
  market: Market,
  displayPeriod: string,
  current: PeriodSnapshot,
  previous: PeriodSnapshot | null
): string {
  const lines: string[] = [];
  lines.push(`【PlanA 财务摘要】${current.period}（${formatPeriodLabel(displayPeriod)}）`);

  const yoy = {
    revenue: yoyPercent(current.income.revenue, previous?.income.revenue ?? null),
    net_profit: yoyPercent(current.income.net_profit, previous?.income.net_profit ?? null),
    operating_cf: yoyPercent(current.cashflow.operating_cf, previous?.cashflow.operating_cf ?? null),
    total_assets: yoyPercent(current.balance.total_assets, previous?.balance.total_assets ?? null),
    total_liab: yoyPercent(current.balance.total_liab, previous?.balance.total_liab ?? null)
  };

  const debtRatio = current.ratios.debt_to_assets_pct;
  const debtRatioPrev = previous?.ratios.debt_to_assets_pct ?? null;
  const debtRatioDelta = delta(debtRatio, debtRatioPrev);

  lines.push(
    `- 营收：${formatMoney(market, current.income.revenue)}（同比 ${formatPercent(yoy.revenue)}）`
  );
  lines.push(
    `- 归母/净利润：${formatMoney(market, current.income.net_profit)}（同比 ${formatPercent(yoy.net_profit)}）`
  );
  lines.push(
    `- 经营现金流：${formatMoney(market, current.cashflow.operating_cf)}（同比 ${formatPercent(yoy.operating_cf)}）`
  );
  lines.push(
    `- 总资产：${formatMoney(market, current.balance.total_assets)}（同比 ${formatPercent(yoy.total_assets)}）`
  );
  lines.push(
    `- 总负债：${formatMoney(market, current.balance.total_liab)}（同比 ${formatPercent(yoy.total_liab)}）`
  );
  lines.push(
    `- 资产负债率：${formatPercent(debtRatio)}（较上年 ${debtRatioDelta === null ? '—' : `${formatNumber(debtRatioDelta, 2)}pct`}）`
  );
  lines.push(
    `- 盈利能力：毛利率 ${formatPercent(current.ratios.gross_margin_pct)}；净利率 ${formatPercent(current.ratios.net_margin_pct)}；ROE ${formatPercent(current.ratios.roe_pct)}；ROA ${formatPercent(current.ratios.roa_pct)}`
  );
  lines.push(
    `- 偿债能力：流动比率 ${formatNumber(current.ratios.current_ratio, 2)}；速动比率 ${formatNumber(current.ratios.quick_ratio, 2)}`
  );

  return lines.join('\n');
}

function formatMoneyCNFromWanYuanToYi(v: NumberLike): string {
  if (v === null || v === undefined) return '—';
  const yi = v / 10000;
  const abs = Math.abs(yi);
  const formatted = abs.toLocaleString('zh-CN', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  return `${yi < 0 ? '-' : ''}${formatted}亿`;
}

function formatMoneyUS(v: NumberLike): string {
  if (v === null || v === undefined) return '—';
  const abs = Math.abs(v);
  let unit = '';
  let scaled = v;
  if (abs >= 1e9) {
    unit = 'B';
    scaled = v / 1e9;
  } else if (abs >= 1e6) {
    unit = 'M';
    scaled = v / 1e6;
  } else if (abs >= 1e3) {
    unit = 'K';
    scaled = v / 1e3;
  }
  const formatted = Math.abs(scaled).toLocaleString('en-US', { maximumFractionDigits: 2, minimumFractionDigits: 2 });
  return `${scaled < 0 ? '-' : ''}${formatted}${unit}`;
}

function formatMoney(market: Market, v: NumberLike): string {
  return market === 'CN' ? formatMoneyCNFromWanYuanToYi(v) : formatMoneyUS(v);
}

function escapeHtml(s: string): string {
  return s
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

async function tushareFetch(api_name: string, token: string, params: Record<string, any>, fields?: string): Promise<any[]> {
  const payload: any = { api_name, token, params };
  if (fields) payload.fields = fields;

  const response = await fetch(TUSHARE_CONFIG.API_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(TUSHARE_CONFIG.TIMEOUT)
  });

  if (!response.ok) {
    throw new Error(`Tushare API请求失败: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  if (data.code !== 0) {
    throw new Error(`Tushare API错误: ${data.msg || '未知错误'}`);
  }

  if (!data.data?.items?.length) return [];

  const out: any[] = [];
  const fieldsArr: string[] = data.data.fields;
  for (const row of data.data.items) {
    const obj: any = {};
    fieldsArr.forEach((f, idx) => (obj[f] = row[idx]));
    out.push(obj);
  }
  return out;
}

function mergeHeaders(base: Record<string, string> | undefined, extra: Record<string, string> | undefined) {
  return { ...(base ?? {}), ...(extra ?? {}) };
}

class CookieJar {
  private map = new Map<string, string>();

  addFromSetCookie(setCookieHeaderValue: string | undefined) {
    if (!setCookieHeaderValue) return;
    const first = String(setCookieHeaderValue).split(';', 1)[0];
    const eq = first.indexOf('=');
    if (eq <= 0) return;
    const name = first.slice(0, eq).trim();
    const value = first.slice(eq + 1).trim();
    if (!name) return;
    this.map.set(name, value);
  }

  ingestSetCookie(setCookieHeader: string[] | string | undefined) {
    if (!setCookieHeader) return;
    if (Array.isArray(setCookieHeader)) {
      for (const v of setCookieHeader) this.addFromSetCookie(v);
      return;
    }
    this.addFromSetCookie(setCookieHeader);
  }

  headerValue() {
    const parts: string[] = [];
    for (const [k, v] of this.map.entries()) parts.push(`${k}=${v}`);
    return parts.join('; ');
  }
}

function request(
  url: string,
  {
    headers = {},
    timeoutMs = 15000,
    jar,
    maxRedirects = 5
  }: { headers?: Record<string, string>; timeoutMs?: number; jar?: CookieJar; maxRedirects?: number } = {}
) {
  const defaultHeaders = {
    'user-agent':
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
    accept: 'application/json,text/plain,*/*',
    'accept-language': 'en-US,en;q=0.9'
  };

  return new Promise<{ statusCode: number; headers: Record<string, string | string[] | undefined>; body: string }>((resolve, reject) => {
    const effectiveHeaders: Record<string, string> = mergeHeaders(defaultHeaders, headers);
    if (jar) {
      const cookie = jar.headerValue();
      if (cookie) effectiveHeaders.cookie = cookie;
    }

    const req = https.get(
      url,
      {
        headers: effectiveHeaders,
        maxHeaderSize: 128 * 1024
      },
      (res) => {
        jar?.ingestSetCookie(res.headers['set-cookie']);

        const status = res.statusCode ?? 0;
        const location = res.headers.location;
        if (status >= 300 && status < 400 && location) {
          if (maxRedirects <= 0) {
            res.resume();
            return reject(new Error(`Too many redirects for ${url}`));
          }
          const redirected = new URL(location, url).toString();
          res.resume();
          return resolve(request(redirected, { headers, timeoutMs, jar, maxRedirects: maxRedirects - 1 }));
        }

        let data = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          if (status >= 400) {
            return reject(new Error(`HTTP ${status} ${res.statusMessage ?? ''} for ${url}\n${data.slice(0, 500)}`));
          }
          resolve({ statusCode: status, headers: res.headers, body: data });
        });
      }
    );

    const hardTimer = setTimeout(() => {
      req.destroy(new Error(`Request timeout after ${timeoutMs}ms for ${url}`));
    }, timeoutMs);

    req.on('close', () => clearTimeout(hardTimer));
    req.on('error', (err) => {
      clearTimeout(hardTimer);
      reject(err);
    });
  });
}

async function fetchJson(url: string, opts?: { headers?: Record<string, string>; timeoutMs?: number; jar?: CookieJar }) {
  const { body } = await request(url, opts);
  try {
    return JSON.parse(body);
  } catch (e: any) {
    throw new Error(`Failed to parse JSON for ${url}: ${e.message}`);
  }
}

async function getYahooCrumbAndCookies(ticker: string) {
  const jar = new CookieJar();

  const warmups = [
    `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}`,
    `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}?p=${encodeURIComponent(ticker)}`
  ];
  for (const u of warmups) {
    try {
      await request(u, {
        jar,
        headers: {
          accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        },
        timeoutMs: 10000
      });
      break;
    } catch {
      // keep trying
    }
  }

  const crumbRes = await request('https://query1.finance.yahoo.com/v1/test/getcrumb', {
    jar,
    headers: { accept: 'text/plain,*/*' },
    timeoutMs: 10000
  });

  const crumb = (crumbRes.body ?? '').trim();
  if (!crumb || crumb.toLowerCase().includes('html')) {
    throw new Error(`Failed to obtain Yahoo crumb for ${ticker}. Response: ${crumb.slice(0, 80)}`);
  }
  return { jar, crumb };
}

function pickFirst(rows: any[]): any | null {
  if (!rows || rows.length === 0) return null;
  return rows[0];
}

type YahooStatements = {
  income: any[];
  balance: any[];
  cashflow: any[];
  currency?: string | null;
};

type EastmoneyCache = {
  incomeBy: Map<string, Record<string, any>>;
  balanceBy: Map<string, Record<string, any>>;
  cashBy: Map<string, Record<string, any>>;
  periods: string[];
};

const yahooCache = new Map<string, YahooStatements>();
const eastmoneyCache = new Map<string, EastmoneyCache>();

function normalizeYahooTicker(symbol: string): string {
  const upper = symbol.trim().toUpperCase();
  if (upper.endsWith('.SH')) return `${upper.slice(0, -3)}.SS`;
  return upper;
}

function normalizeCnSymbol(symbol: string): string {
  const upper = symbol.trim().toUpperCase();
  if (!upper) return '';
  if (upper.includes('.')) return upper.split('.', 1)[0];
  return upper;
}

function periodToEpochMs(period: string): number {
  if (!isValidPeriod(period)) return 0;
  const y = Number(period.slice(0, 4));
  const m = Number(period.slice(4, 6)) - 1;
  const d = Number(period.slice(6, 8));
  return Date.UTC(y, m, d);
}

function pickNearestByEndDate(items: any[], targetPeriod: string): any | null {
  if (!Array.isArray(items) || items.length === 0) return null;
  const target = periodToEpochMs(targetPeriod);
  let best: any | null = null;
  let bestDelta = Number.POSITIVE_INFINITY;
  for (const item of items) {
    const raw = item?.endDate?.raw;
    if (!raw) continue;
    const epochMs = Number(raw) * 1000;
    if (!Number.isFinite(epochMs)) continue;
    const delta = Math.abs(epochMs - target);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = item;
    }
  }
  return best;
}

async function fetchYahooStatements(symbol: string): Promise<YahooStatements> {
  const ticker = normalizeYahooTicker(symbol);
  if (yahooCache.has(ticker)) return yahooCache.get(ticker)!;

  let json: any | null = null;
  try {
    const { jar, crumb } = await getYahooCrumbAndCookies(ticker);
    const url = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(
      ticker
    )}?modules=incomeStatementHistoryQuarterly,balanceSheetHistoryQuarterly,cashflowStatementHistoryQuarterly,price&crumb=${encodeURIComponent(crumb)}`;
    json = await fetchJson(url, { jar });
  } catch {
    const url = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(
      ticker
    )}?modules=incomeStatementHistoryQuarterly,balanceSheetHistoryQuarterly,cashflowStatementHistoryQuarterly,price`;
    json = await fetchJson(url);
  }

  const result = json?.quoteSummary?.result?.[0];
  if (!result) {
    const err = json?.quoteSummary?.error?.description || '未知错误';
    throw new Error(`Yahoo返回异常: ${err}`);
  }

  const income = result?.incomeStatementHistoryQuarterly?.incomeStatementHistory || [];
  const balance = result?.balanceSheetHistoryQuarterly?.balanceSheetStatements || [];
  const cashflow = result?.cashflowStatementHistoryQuarterly?.cashflowStatements || [];
  const currency = result?.price?.currency ?? null;

  const payload = { income, balance, cashflow, currency };
  yahooCache.set(ticker, payload);
  return payload;
}

async function eastmoneyFetch(reportName: string, securityCode: string, pageSize: number = 80) {
  const params = new URLSearchParams({
    reportName,
    columns: 'ALL',
    filter: `(SECURITY_CODE="${securityCode}")`,
    pageNumber: '1',
    pageSize: String(pageSize),
    sortColumns: 'REPORT_DATE',
    sortTypes: '-1'
  });
  const url = `https://datacenter-web.eastmoney.com/api/data/v1/get?${params.toString()}`;
  const response = await fetch(url, {
    headers: {
      'user-agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
      accept: 'application/json,text/plain,*/*'
    },
    signal: AbortSignal.timeout(TUSHARE_CONFIG.TIMEOUT)
  });
  if (!response.ok) {
    throw new Error(`Eastmoney请求失败: ${response.status} ${response.statusText}`);
  }
  const payload: any = await response.json();
  const rows = payload?.result?.data;
  return Array.isArray(rows) ? rows.filter((r: any) => r && typeof r === 'object') : [];
}

function toPeriod(dateStr: string | null | undefined): string | null {
  if (!dateStr) return null;
  const s = String(dateStr).trim();
  if (!s) return null;
  const base = s.split(' ')[0];
  if (base.includes('-')) {
    const parts = base.split('-');
    if (parts.length === 3) return parts.join('');
  }
  if (base.length >= 8 && /^\d{8}/.test(base)) return base.slice(0, 8);
  return null;
}

function indexByPeriod(rows: Array<Record<string, any>>): Map<string, Record<string, any>> {
  const out = new Map<string, Record<string, any>>();
  for (const r of rows) {
    const p = toPeriod(r?.REPORT_DATE);
    if (!p) continue;
    out.set(p, r);
  }
  return out;
}

async function getEastmoneyCache(symbol: string): Promise<EastmoneyCache> {
  const code = normalizeCnSymbol(symbol);
  if (!code) throw new Error('CN代码为空');
  if (eastmoneyCache.has(code)) return eastmoneyCache.get(code)!;

  const [incomeRows, balanceRows, cashRows] = await Promise.all([
    eastmoneyFetch('RPT_F10_FINANCE_GINCOME', code),
    eastmoneyFetch('RPT_F10_FINANCE_GBALANCE', code),
    eastmoneyFetch('RPT_F10_FINANCE_GCASHFLOW', code)
  ]);

  const incomeBy = indexByPeriod(incomeRows as any);
  const balanceBy = indexByPeriod(balanceRows as any);
  const cashBy = indexByPeriod(cashRows as any);
  const periodSet = new Set<string>([...incomeBy.keys(), ...balanceBy.keys(), ...cashBy.keys()]);
  const periods = Array.from(periodSet).filter(p => /^\d{8}$/.test(p)).sort((a, b) => (a < b ? 1 : -1));

  const payload: EastmoneyCache = { incomeBy, balanceBy, cashBy, periods };
  eastmoneyCache.set(code, payload);
  return payload;
}

function pickNearestPeriod(periods: string[], target: string): string | null {
  if (!periods.length) return null;
  if (periods.includes(target)) return target;
  const targetInt = Number(target);
  const notAfter = periods.filter(p => Number(p) <= targetInt);
  if (notAfter.length > 0) return notAfter[0];
  return periods[0] ?? null;
}

async function fetchSnapshotCNEastmoney(symbol: string, period: string): Promise<PeriodSnapshot> {
  const cache = await getEastmoneyCache(symbol);
  const picked = pickNearestPeriod(cache.periods, period);
  if (!picked) {
    throw new Error('Eastmoney无可用报告期');
  }

  const inc = cache.incomeBy.get(picked) ?? {};
  const bal = cache.balanceBy.get(picked) ?? {};
  const cf = cache.cashBy.get(picked) ?? {};

  const revenue = parseNum(inc.TOTAL_OPERATE_INCOME);
  const totalProfit = parseNum(inc.TOTAL_PROFIT);
  const netProfit = parseNum(inc.PARENT_NETPROFIT ?? inc.NETPROFIT);

  const totalAssets = parseNum(bal.TOTAL_ASSETS);
  const totalLiab = parseNum(bal.TOTAL_LIABILITIES);
  const equity = parseNum(bal.TOTAL_EQUITY ?? bal.TOTAL_PARENT_EQUITY);

  const operatingCf = parseNum(cf.NETCASH_OPERATE);

  const toWan = (v: number | null) => (v === null ? null : v / 10000.0);

  const revenueW = toWan(revenue);
  const totalProfitW = toWan(totalProfit);
  const netProfitW = toWan(netProfit);
  const totalAssetsW = toWan(totalAssets);
  const totalLiabW = toWan(totalLiab);
  const equityW = toWan(equity);
  const operatingCfW = toWan(operatingCf);

  const debtRatio = totalAssets && totalLiab ? (totalLiab / totalAssets) * 100 : null;
  const netMargin = revenue ? (netProfit ?? 0) / revenue * 100 : null;
  const roe = equity ? (netProfit ?? 0) / equity * 100 : null;

  return {
    period,
    income: {
      revenue: revenueW,
      total_profit: totalProfitW,
      net_profit: netProfitW
    },
    balance: {
      total_assets: totalAssetsW,
      total_liab: totalLiabW,
      equity: equityW
    },
    cashflow: {
      operating_cf: operatingCfW
    },
    ratios: {
      debt_to_assets_pct: debtRatio,
      current_ratio: null,
      quick_ratio: null,
      gross_margin_pct: null,
      net_margin_pct: netMargin,
      roe_pct: roe,
      roa_pct: null,
      basic_eps: null,
      diluted_eps: null,
      bps: null,
      ocfps: null
    }
  };
}

async function fetchSnapshotCNYahoo(symbol: string, period: string): Promise<PeriodSnapshot> {
  const statements = await fetchYahooStatements(symbol);
  const incomeRow = pickNearestByEndDate(statements.income, period);
  const balanceRow = pickNearestByEndDate(statements.balance, period);
  const cashflowRow = pickNearestByEndDate(statements.cashflow, period);

  const totalAssets = parseNum(balanceRow?.totalAssets?.raw ?? balanceRow?.totalAssets);
  const totalLiab = parseNum(balanceRow?.totalLiab?.raw ?? balanceRow?.totalLiab);
  const equity = parseNum(balanceRow?.totalStockholderEquity?.raw ?? balanceRow?.totalStockholderEquity);

  const revenue = parseNum(incomeRow?.totalRevenue?.raw ?? incomeRow?.totalRevenue);
  const netProfit = parseNum(incomeRow?.netIncome?.raw ?? incomeRow?.netIncome);
  const totalProfit = parseNum(incomeRow?.incomeBeforeTax?.raw ?? incomeRow?.incomeBeforeTax ?? incomeRow?.ebit?.raw ?? incomeRow?.ebit);

  const operatingCf = parseNum(
    cashflowRow?.totalCashFromOperatingActivities?.raw ?? cashflowRow?.totalCashFromOperatingActivities
  );

  const debtRatio = totalAssets && totalLiab ? (totalLiab / totalAssets) * 100 : null;
  const netMargin = revenue ? (netProfit ?? 0) / revenue * 100 : null;
  const grossMargin = revenue ? (parseNum(incomeRow?.grossProfit?.raw ?? incomeRow?.grossProfit) ?? 0) / revenue * 100 : null;
  const roe = equity ? (netProfit ?? 0) / equity * 100 : null;
  const roa = totalAssets ? (netProfit ?? 0) / totalAssets * 100 : null;

  return {
    period,
    income: {
      revenue,
      total_profit: totalProfit,
      net_profit: netProfit
    },
    balance: {
      total_assets: totalAssets,
      total_liab: totalLiab,
      equity
    },
    cashflow: {
      operating_cf: operatingCf
    },
    ratios: {
      debt_to_assets_pct: debtRatio,
      current_ratio: null,
      quick_ratio: null,
      gross_margin_pct: grossMargin,
      net_margin_pct: netMargin,
      roe_pct: roe,
      roa_pct: roa,
      basic_eps: null,
      diluted_eps: null,
      bps: null,
      ocfps: null
    }
  };
}

async function fetchSnapshotCNWithFallback(
  symbol: string,
  period: string,
  token?: string
): Promise<{ snapshot: PeriodSnapshot; source: 'tushare' | 'eastmoney' | 'yahoo' }> {
  if (token) {
    try {
      const snapshot = await fetchSnapshotCN(symbol, period, token);
      return { snapshot, source: 'tushare' };
    } catch {
      try {
        const snapshot = await fetchSnapshotCNEastmoney(symbol, period);
        return { snapshot, source: 'eastmoney' };
      } catch {
        const snapshot = await fetchSnapshotCNYahoo(symbol, period);
        return { snapshot, source: 'yahoo' };
      }
    }
  }

  try {
    const snapshot = await fetchSnapshotCNEastmoney(symbol, period);
    return { snapshot, source: 'eastmoney' };
  } catch {
    const snapshot = await fetchSnapshotCNYahoo(symbol, period);
    return { snapshot, source: 'yahoo' };
  }
}

function findByKeywords(items: Array<{ ind_name: string; ind_value: number }>, keywords: string[]): number | null {
  for (const item of items) {
    const name = item.ind_name || '';
    for (const kw of keywords) {
      if (name.includes(kw)) return parseNum(item.ind_value);
    }
  }
  return null;
}

type PeriodSnapshot = {
  period: string;
  income: {
    revenue: number | null;
    total_profit: number | null;
    net_profit: number | null;
  };
  balance: {
    total_assets: number | null;
    total_liab: number | null;
    equity: number | null;
  };
  cashflow: {
    operating_cf: number | null;
  };
  ratios: {
    debt_to_assets_pct: number | null;
    current_ratio: number | null;
    quick_ratio: number | null;
    gross_margin_pct: number | null;
    net_margin_pct: number | null;
    roe_pct: number | null;
    roa_pct: number | null;
    basic_eps: number | null;
    diluted_eps: number | null;
    bps: number | null;
    ocfps: number | null;
  };
};

async function fetchSnapshotCN(symbol: string, period: string, token: string): Promise<PeriodSnapshot> {
  const incomeRows = await tushareFetch(
    'income',
    token,
    { ts_code: symbol, period },
    'end_date,total_revenue,revenue,total_profit,n_income,n_income_attr_p'
  );
  const income = pickFirst(incomeRows);

  const balanceRows = await tushareFetch(
    'balancesheet',
    token,
    { ts_code: symbol, period },
    'end_date,total_assets,total_liab,total_hldr_eqy_exc_min_int'
  );
  const balance = pickFirst(balanceRows);

  const cashflowRows = await tushareFetch(
    'cashflow',
    token,
    { ts_code: symbol, period },
    'end_date,n_cashflow_act'
  );
  const cashflow = pickFirst(cashflowRows);

  const indRows = await tushareFetch(
    'fina_indicator',
    token,
    { ts_code: symbol, period },
    'end_date,debt_to_assets,current_ratio,quick_ratio,grossprofit_margin,netprofit_margin,roe,roa,basic_eps,diluted_eps,bps,ocfps'
  );
  const ind = pickFirst(indRows);

  const totalAssets = parseNum(balance?.total_assets);
  const totalLiab = parseNum(balance?.total_liab);

  return {
    period,
    income: {
      revenue: parseNum(income?.total_revenue ?? income?.revenue),
      total_profit: parseNum(income?.total_profit),
      net_profit: parseNum(income?.n_income_attr_p ?? income?.n_income)
    },
    balance: {
      total_assets: totalAssets,
      total_liab: totalLiab,
      equity: parseNum(balance?.total_hldr_eqy_exc_min_int)
    },
    cashflow: {
      operating_cf: parseNum(cashflow?.n_cashflow_act)
    },
    ratios: {
      debt_to_assets_pct: parseNum(ind?.debt_to_assets) ?? (totalAssets && totalLiab ? (totalLiab / totalAssets) * 100 : null),
      current_ratio: parseNum(ind?.current_ratio),
      quick_ratio: parseNum(ind?.quick_ratio),
      gross_margin_pct: parseNum(ind?.grossprofit_margin),
      net_margin_pct: parseNum(ind?.netprofit_margin),
      roe_pct: parseNum(ind?.roe),
      roa_pct: parseNum(ind?.roa),
      basic_eps: parseNum(ind?.basic_eps),
      diluted_eps: parseNum(ind?.diluted_eps),
      bps: parseNum(ind?.bps),
      ocfps: parseNum(ind?.ocfps)
    }
  };
}

async function fetchSnapshotUS(symbol: string, period: string, token: string): Promise<PeriodSnapshot> {
  // us_income/us_balancesheet/us_cashflow: 以 ind_name/ind_value 形式返回
  const incomeList = await tushareFetch('us_income', token, { ts_code: symbol, period });
  const balanceList = await tushareFetch('us_balancesheet', token, { ts_code: symbol, period });
  const cashflowList = await tushareFetch('us_cashflow', token, { ts_code: symbol, period });
  const indRows = await tushareFetch(
    'us_fina_indicator',
    token,
    { ts_code: symbol, period },
    'end_date,debt_to_assets,current_ratio,quick_ratio,grossprofit_margin,netprofit_margin,roe,roa,basic_eps,diluted_eps,bps,ocfps'
  );

  const ind = pickFirst(indRows);

  const incomeItems = incomeList
    .map(r => ({ ind_name: r.ind_name, ind_value: r.ind_value }))
    .filter(r => typeof r.ind_name === 'string');

  const balanceItems = balanceList
    .map(r => ({ ind_name: r.ind_name, ind_value: r.ind_value }))
    .filter(r => typeof r.ind_name === 'string');

  const cashflowItems = cashflowList
    .map(r => ({ ind_name: r.ind_name, ind_value: r.ind_value }))
    .filter(r => typeof r.ind_name === 'string');

  const totalAssets = findByKeywords(balanceItems as any, ['Total Assets']);
  const totalLiabilities = findByKeywords(balanceItems as any, ['Total Liabilities']);
  const equity = findByKeywords(balanceItems as any, ['Total Equity', 'Stockholder Equity']);

  const revenue = findByKeywords(incomeItems as any, ['Total Revenue', 'Revenue', 'Net Sales']);
  const netIncome = findByKeywords(incomeItems as any, ['Net Income']);
  const totalProfit = findByKeywords(incomeItems as any, ['Income Before Tax', 'Pretax Income']);

  const operatingCF = findByKeywords(cashflowItems as any, [
    'Net Cash Provided by Operating Activities',
    'Net Cash from Operating Activities',
    'Operating Cash Flow'
  ]);

  return {
    period,
    income: {
      revenue,
      total_profit: totalProfit,
      net_profit: netIncome
    },
    balance: {
      total_assets: totalAssets,
      total_liab: totalLiabilities,
      equity
    },
    cashflow: {
      operating_cf: operatingCF
    },
    ratios: {
      debt_to_assets_pct: parseNum(ind?.debt_to_assets) ?? (totalAssets && totalLiabilities ? (totalLiabilities / totalAssets) * 100 : null),
      current_ratio: parseNum(ind?.current_ratio),
      quick_ratio: parseNum(ind?.quick_ratio),
      gross_margin_pct: parseNum(ind?.grossprofit_margin),
      net_margin_pct: parseNum(ind?.netprofit_margin),
      roe_pct: parseNum(ind?.roe),
      roa_pct: parseNum(ind?.roa),
      basic_eps: parseNum(ind?.basic_eps),
      diluted_eps: parseNum(ind?.diluted_eps),
      bps: parseNum(ind?.bps),
      ocfps: parseNum(ind?.ocfps)
    }
  };
}

function buildDisplayPeriods(period: string): string[] {
  const y = Number(period.slice(0, 4));
  const mmdd = period.slice(4);
  if (mmdd === '1231') {
    return [period, `${y - 1}1231`, `${y - 2}1231`].map(String);
  }
  // 截图风格：季度/中报/三季报 + 近两年年报
  return [period, `${y - 1}1231`, `${y - 2}1231`].map(String);
}

function buildComparePeriodForColumn(displayPeriod: string, isFirstColumnQuarterLike: boolean, firstInputMmdd: string): string {
  const mmdd = displayPeriod.slice(4);
  if (isFirstColumnQuarterLike && mmdd !== '1231') {
    // 第一列为季度/中报/三季报：同比对比上一年同季度
    return subtractYear(displayPeriod, 1);
  }
  // 年报列：同比对比上一年年报
  return subtractYear(displayPeriod, 1);
}

function renderHtml(opts: {
  reportTitle: string;
  subtitle: string;
  market: Market;
  displayPeriods: string[];
  snapshots: Record<string, PeriodSnapshot>;
  compareSnapshots: Record<string, PeriodSnapshot | null>;
  dataSourceLabel: string;
}): string {
  const { reportTitle, subtitle, market, displayPeriods, snapshots, compareSnapshots, dataSourceLabel } = opts;

  const cols = displayPeriods.map(p => ({ period: p, label: formatPeriodLabel(p) }));

  function cellMoney(getter: (s: PeriodSnapshot) => NumberLike, period: string): string {
    const v = getter(snapshots[period]);
    return formatMoney(market, v);
  }

  function cellPercent(getter: (s: PeriodSnapshot) => NumberLike, period: string): string {
    const v = getter(snapshots[period]);
    return v === null || v === undefined ? '—' : `${v.toFixed(2)}`;
  }

  function rowHtml(label: string, valueCells: string[]): string {
    return `<tr><td class="label">${escapeHtml(label)}</td>${valueCells.map(v => `<td class="val">${escapeHtml(v)}</td>`).join('')}</tr>`;
  }

  function yoyRowHtml(valueGetter: (s: PeriodSnapshot) => NumberLike, label = '同比(%)'): string {
    const yoyCells = cols.map(({ period }) => {
      const cur = valueGetter(snapshots[period]);
      const prevSnap = compareSnapshots[period];
      const prev = prevSnap ? valueGetter(prevSnap) : null;
      const y = yoyPercent(cur, prev);
      const txt = y === null ? '—' : y.toFixed(2);
      return txt;
    });
    return rowHtml(label, yoyCells);
  }

  const currencyLabel = market === 'CN' ? '人民币' : '美元';

  const css = `
  @page { size: A4; margin: 16mm; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif; color:#111; }
  h1 { font-size: 20px; margin: 0 0 6px; }
  .meta { color:#555; font-size: 12px; margin-bottom: 14px; }
  .section { margin: 14px 0 18px; }
  .section-title { font-size: 14px; font-weight: 700; margin: 10px 0 8px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { border: 1px solid #e5e7eb; padding: 8px 8px; vertical-align: middle; }
  th { background: #f5f7fb; text-align: center; font-weight: 700; }
  td.label { width: 32%; background: #fff; font-weight: 600; }
  td.val { text-align: right; }
  .group { background: #f0f6ff; font-weight: 800; text-align: left; }
  .note { margin-top: 10px; font-size: 11px; color:#666; }
  `;

  const header = `
  <h1>${escapeHtml(reportTitle)}</h1>
  <div class="meta">${escapeHtml(subtitle)} | 单位：${escapeHtml(currencyLabel)}</div>
  `;

  const tableHead = `
    <tr>
      <th style="text-align:left">指标名称</th>
      ${cols.map(c => `<th>${escapeHtml(c.label)}<div style="font-weight:400;color:#667;font-size:11px;margin-top:2px;">${escapeHtml(currencyLabel)}</div></th>`).join('')}
    </tr>
  `;

  const incomeRows = [
    `<tr><td class="group" colspan="${cols.length + 1}">利润表</td></tr>`,
    rowHtml('营业总收入', cols.map(c => cellMoney(s => s.income.revenue, c.period))),
    yoyRowHtml(s => s.income.revenue),
    rowHtml('利润总额', cols.map(c => cellMoney(s => s.income.total_profit, c.period))),
    yoyRowHtml(s => s.income.total_profit),
    rowHtml('净利润', cols.map(c => cellMoney(s => s.income.net_profit, c.period))),
    yoyRowHtml(s => s.income.net_profit)
  ].join('');

  const balanceRows = [
    `<tr><td class="group" colspan="${cols.length + 1}">资产负债表</td></tr>`,
    rowHtml('资产合计', cols.map(c => cellMoney(s => s.balance.total_assets, c.period))),
    yoyRowHtml(s => s.balance.total_assets),
    rowHtml('负债总计', cols.map(c => cellMoney(s => s.balance.total_liab, c.period))),
    yoyRowHtml(s => s.balance.total_liab),
    rowHtml('所有者权益总计', cols.map(c => cellMoney(s => s.balance.equity, c.period))),
    yoyRowHtml(s => s.balance.equity)
  ].join('');

  const cashflowRows = [
    `<tr><td class="group" colspan="${cols.length + 1}">现金流量表</td></tr>`,
    rowHtml('经营活动产生的现金流量净额', cols.map(c => cellMoney(s => s.cashflow.operating_cf, c.period))),
    yoyRowHtml(s => s.cashflow.operating_cf)
  ].join('');

  const perShareRows = [
    `<tr><td class="group" colspan="${cols.length + 1}">每股指标</td></tr>`,
    rowHtml('基本每股收益', cols.map(c => {
      const v = snapshots[c.period].ratios.basic_eps;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    rowHtml('稀释每股收益', cols.map(c => {
      const v = snapshots[c.period].ratios.diluted_eps;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    rowHtml('每股净资产', cols.map(c => {
      const v = snapshots[c.period].ratios.bps;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    rowHtml('每股经营现金流', cols.map(c => {
      const v = snapshots[c.period].ratios.ocfps;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    }))
  ].join('');

  const ratioRows = [
    `<tr><td class="group" colspan="${cols.length + 1}">盈利能力</td></tr>`,
    rowHtml('毛利率(%)', cols.map(c => {
      const v = snapshots[c.period].ratios.gross_margin_pct;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    rowHtml('净利率(%)', cols.map(c => {
      const v = snapshots[c.period].ratios.net_margin_pct;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    rowHtml('ROE(%)', cols.map(c => {
      const v = snapshots[c.period].ratios.roe_pct;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    rowHtml('ROA(%)', cols.map(c => {
      const v = snapshots[c.period].ratios.roa_pct;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    `<tr><td class="group" colspan="${cols.length + 1}">偿债能力</td></tr>`,
    rowHtml('资产负债率(%)', cols.map(c => {
      const v = snapshots[c.period].ratios.debt_to_assets_pct;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    rowHtml('流动比率', cols.map(c => {
      const v = snapshots[c.period].ratios.current_ratio;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    })),
    rowHtml('速动比率', cols.map(c => {
      const v = snapshots[c.period].ratios.quick_ratio;
      return v === null || v === undefined ? '—' : v.toFixed(2);
    }))
  ].join('');

  const html = `<!doctype html>
  <html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(reportTitle)}</title>
    <style>${css}</style>
  </head>
  <body>
    ${header}
    <div class="section">
      <table>
        <thead>${tableHead}</thead>
        <tbody>
          ${incomeRows}
          ${balanceRows}
          ${cashflowRows}
          ${perShareRows}
          ${ratioRows}
        </tbody>
      </table>
      <div class="note">数据来源：${escapeHtml(dataSourceLabel)}；同比口径：同季度/同年报对比上一年同口径报告期。</div>
    </div>
  </body>
  </html>`;

  return html;
}

async function htmlToPdf(htmlPath: string, pdfPath: string): Promise<void> {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(pathToFileURL(htmlPath).toString(), { waitUntil: 'load' });
  await page.pdf({ path: pdfPath, format: 'A4', printBackground: true });
  await browser.close();
}

export const planAReportPdf = {
  name: 'planA_report_pdf',
  description: '按 PlanA 输出规范生成财务数据 PDF（支持境内CN与美股US；含季度/年报同比）',
  parameters: {
    type: 'object',
    properties: {
      report_id: { type: 'string', description: '报告标识，用于文件命名与追踪' },
      market: { type: 'string', enum: ['CN', 'US'], description: '市场：CN(A股) 或 US(美股)' },
      symbol: { type: 'string', description: '代码：CN用ts_code(如000001.SZ)，US用ticker(如NVDA)' },
      period: { type: 'string', description: '报告期YYYYMMDD（如20250930/20241231）' },
      output: {
        type: 'object',
        properties: {
          out_dir: { type: 'string', description: '输出目录（默认 PlanA/_out）' },
          format: { type: 'string', enum: ['pdf'], default: 'pdf' }
        }
      },
      compare: {
        type: 'object',
        properties: {
          mode: { type: 'string', enum: ['auto_yoy', 'manual'], default: 'auto_yoy' },
          compare_period: { type: 'string', description: '手动指定对比期YYYYMMDD（仅用于第一列同比）' }
        }
      }
    },
    required: ['report_id', 'market', 'symbol', 'period']
  },

  async run(args: PlanAReportArgs) {
    try {
      if (!TUSHARE_CONFIG.API_TOKEN && args.market === 'US') {
        throw new Error('US市场需要TUSHARE_TOKEN环境变量（或在HTTP请求头中透传）');
      }

      if (!isValidPeriod(args.period)) {
        throw new Error(`period 格式错误: ${args.period}，应为YYYYMMDD`);
      }

      const outDir = args.output?.out_dir ? String(args.output.out_dir) : './PlanA/_out';
      const absOutDir = resolve(process.cwd(), outDir);
      await mkdir(absOutDir, { recursive: true });

      const now = new Date();
      const chinaTime = new Date(now.getTime() + 8 * 60 * 60 * 1000);
      const pad2 = (n: number) => String(n).padStart(2, '0');
      const ts = `${chinaTime.getUTCFullYear()}${pad2(chinaTime.getUTCMonth() + 1)}${pad2(chinaTime.getUTCDate())}_${pad2(chinaTime.getUTCHours())}${pad2(chinaTime.getUTCMinutes())}${pad2(chinaTime.getUTCSeconds())}`;

      const displayPeriods = buildDisplayPeriods(args.period);

      // 为了让每个列都有“同比(%)”，需要额外获取上一年同口径数据
      const needed = new Set<string>();
      for (const p of displayPeriods) {
        needed.add(p);
        // 同比对比期（默认上一年同日）
        needed.add(subtractYear(p, 1));
      }
      // 第一列（季度类）手动对比期（可选）
      if (args.compare?.mode === 'manual' && args.compare.compare_period && isValidPeriod(args.compare.compare_period)) {
        needed.add(String(args.compare.compare_period));
      }

      const token = TUSHARE_CONFIG.API_TOKEN || undefined;
      const dataSources = new Set<string>();
      const snapshots: Record<string, PeriodSnapshot> = {};
      for (const p of needed) {
        if (args.market === 'CN') {
          const res = await fetchSnapshotCNWithFallback(args.symbol, p, token);
          snapshots[p] = res.snapshot;
          dataSources.add(res.source);
        } else {
          snapshots[p] = await fetchSnapshotUS(args.symbol, p, token || '');
          dataSources.add('tushare');
        }
      }

      // 为每个展示列准备对比快照
      const compareSnapshots: Record<string, PeriodSnapshot | null> = {};
      const isQuarterLike = args.period.slice(4) !== '1231';
      for (const p of displayPeriods) {
        let cp = subtractYear(p, 1);
        // 如果用户手动指定了“第一列”的对比期
        if (p === displayPeriods[0] && args.compare?.mode === 'manual' && args.compare.compare_period && isValidPeriod(args.compare.compare_period)) {
          cp = String(args.compare.compare_period);
        }
        compareSnapshots[p] = snapshots[cp] ?? null;
      }

      const reportTitle = `${args.symbol} 财务数据`;
      const subtitle = `报告期：${formatPeriodLabel(displayPeriods[0])}（PlanA）`;

      const html = renderHtml({
        reportTitle,
        subtitle,
        market: args.market,
        displayPeriods,
        snapshots,
        compareSnapshots,
        dataSourceLabel: dataSources.size === 1
          ? (dataSources.has('eastmoney')
              ? 'Eastmoney（公开接口）'
              : (dataSources.has('yahoo') ? 'Yahoo Finance（非官方）' : 'Tushare'))
          : 'Tushare + Eastmoney/Yahoo'
      });

      const baseName = `${args.report_id}_${args.market}_${args.symbol}_${args.period}_${ts}`;
      const htmlPath = resolve(absOutDir, `${baseName}.html`);
      const pdfPath = resolve(absOutDir, `${baseName}.pdf`);
      const jsonPath = resolve(absOutDir, `${baseName}.report.json`);

      await writeFile(htmlPath, html, 'utf-8');
      await htmlToPdf(htmlPath, pdfPath);

      const analysisText = buildAnalysisText(
        args.market,
        displayPeriods[0],
        snapshots[displayPeriods[0]],
        compareSnapshots[displayPeriods[0]]
      );

      const periodsForJson = displayPeriods.map(p => {
        const cur = snapshots[p];
        const prev = compareSnapshots[p];
        return {
          period: p,
          label: formatPeriodLabel(p),
          values: cur,
          yoy: {
            revenue_pct: yoyPercent(cur.income.revenue, prev?.income.revenue ?? null),
            total_profit_pct: yoyPercent(cur.income.total_profit, prev?.income.total_profit ?? null),
            net_profit_pct: yoyPercent(cur.income.net_profit, prev?.income.net_profit ?? null),
            operating_cf_pct: yoyPercent(cur.cashflow.operating_cf, prev?.cashflow.operating_cf ?? null),
            total_assets_pct: yoyPercent(cur.balance.total_assets, prev?.balance.total_assets ?? null),
            total_liab_pct: yoyPercent(cur.balance.total_liab, prev?.balance.total_liab ?? null),
            equity_pct: yoyPercent(cur.balance.equity, prev?.balance.equity ?? null)
          },
          delta: {
            debt_to_assets_pct_points: delta(cur.ratios.debt_to_assets_pct, prev?.ratios.debt_to_assets_pct ?? null),
            roe_pct_points: delta(cur.ratios.roe_pct, prev?.ratios.roe_pct ?? null),
            roa_pct_points: delta(cur.ratios.roa_pct, prev?.ratios.roa_pct ?? null),
            gross_margin_pct_points: delta(cur.ratios.gross_margin_pct, prev?.ratios.gross_margin_pct ?? null),
            net_margin_pct_points: delta(cur.ratios.net_margin_pct, prev?.ratios.net_margin_pct ?? null)
          },
          compare_period: prev?.period ?? null
        };
      });

      const reportJson = {
        report_id: args.report_id,
        market: args.market,
        symbol: args.symbol,
        input_period: args.period,
        display_periods: displayPeriods,
        generated_at_china: ts,
        data_source: dataSources.size === 1
          ? (dataSources.has('eastmoney')
              ? 'eastmoney'
              : (dataSources.has('yahoo') ? 'yahoo' : 'tushare'))
          : 'mixed',
        analysis_text: analysisText,
        periods: periodsForJson,
        note: {
          cn_money_unit_assumption: 'CN金额字段默认单位为万元，展示转换为“亿”',
          us_money_unit_assumption: 'US金额字段按原始数值展示并自动缩放(K/M/B)'
        }
      };
      await writeFile(jsonPath, JSON.stringify(reportJson, null, 2), 'utf-8');

      return {
        meta: {
          pdf_path: pdfPath,
          html_path: htmlPath,
          json_path: jsonPath,
          analysis_text: analysisText,
          display_periods: displayPeriods
        },
        content: [
          {
            type: 'text',
            text: [
              `✅ PlanA PDF 已生成`,
              `- PDF: ${pdfPath}`,
              `- HTML: ${htmlPath}`,
              `- JSON: ${jsonPath}`,
              `- 展示列: ${displayPeriods.map(formatPeriodLabel).join(' | ')}`
            ].join('\n')
          }
        ]
      };
    } catch (error) {
      return {
        content: [
          {
            type: 'text',
            text: `❌ PlanA 报告生成失败: ${error instanceof Error ? error.message : String(error)}`
          }
        ],
        isError: true
      };
    }
  }
};
