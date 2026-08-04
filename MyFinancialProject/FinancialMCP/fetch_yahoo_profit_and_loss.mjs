import https from 'node:https';

function mergeHeaders(base, extra) {
  return { ...(base ?? {}), ...(extra ?? {}) };
}

function getArg(name, fallbackIndex) {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) return process.argv[idx + 1];
  return process.argv[fallbackIndex] ?? null;
}

class CookieJar {
  constructor() {
    this.map = new Map();
  }

  addFromSetCookie(setCookieHeaderValue) {
    if (!setCookieHeaderValue) return;
    // Only persist the first "name=value" part.
    const first = String(setCookieHeaderValue).split(';', 1)[0];
    const eq = first.indexOf('=');
    if (eq <= 0) return;
    const name = first.slice(0, eq).trim();
    const value = first.slice(eq + 1).trim();
    if (!name) return;
    this.map.set(name, value);
  }

  ingestSetCookie(setCookieHeader) {
    if (!setCookieHeader) return;
    if (Array.isArray(setCookieHeader)) {
      for (const v of setCookieHeader) this.addFromSetCookie(v);
      return;
    }
    this.addFromSetCookie(setCookieHeader);
  }

  headerValue() {
    const parts = [];
    for (const [k, v] of this.map.entries()) parts.push(`${k}=${v}`);
    return parts.join('; ');
  }
}

function request(url, { headers = {}, timeoutMs = 15000, jar, maxRedirects = 5 } = {}) {
  const defaultHeaders = {
    'user-agent':
      'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
    accept: 'application/json,text/plain,*/*',
    'accept-language': 'en-US,en;q=0.9',
  };

  return new Promise((resolve, reject) => {
    const effectiveHeaders = mergeHeaders(defaultHeaders, headers);
    if (jar) {
      const cookie = jar.headerValue();
      if (cookie) effectiveHeaders.cookie = cookie;
    }

    const req = https.get(
      url,
      {
        headers: effectiveHeaders,
        // Yahoo often returns very large Set-Cookie headers (consent/geo), which can overflow Node defaults.
        maxHeaderSize: 128 * 1024,
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
        return resolve(
          request(redirected, { headers, timeoutMs, jar, maxRedirects: maxRedirects - 1 }),
        );
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
      },
    );

    // Hard timeout (covers DNS/connect stalls too)
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

async function fetchJson(url, opts) {
  const { body } = await request(url, opts);
  try {
    return JSON.parse(body);
  } catch (e) {
    throw new Error(`Failed to parse JSON for ${url}: ${e.message}`);
  }
}

async function getYahooCrumbAndCookies(ticker) {
  const jar = new CookieJar();

  // Warm up cookies by visiting a lightweight quote page. Some regions may redirect to consent.
  // Avoid /financials since it can 404/redirect in some networks.
  const warmups = [
    `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}`,
    `https://finance.yahoo.com/quote/${encodeURIComponent(ticker)}?p=${encodeURIComponent(ticker)}`,
  ];
  for (const u of warmups) {
    try {
      await request(u, {
        jar,
        headers: {
          accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        timeoutMs: 10000,
      });
      break;
    } catch {
      // keep trying other warmup URLs
    }
  }

  // Fetch crumb tied to the cookie jar.
  const crumbRes = await request('https://query1.finance.yahoo.com/v1/test/getcrumb', {
    jar,
    headers: { accept: 'text/plain,*/*' },
    timeoutMs: 10000,
  });

  const crumb = (crumbRes.body ?? '').trim();
  if (!crumb || crumb.toLowerCase().includes('html')) {
    throw new Error(`Failed to obtain Yahoo crumb for ${ticker}. Response: ${crumb.slice(0, 80)}`);
  }
  return { jar, crumb };
}

async function fetchYahooIncomeStatementAnnualQuoteSummary(ticker, { jar, crumb } = {}) {
  const modules = ['incomeStatementHistory'];
  const crumbPart = crumb ? `&crumb=${encodeURIComponent(crumb)}` : '';
  const url = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(
    ticker,
  )}?modules=${modules.join(',')}${crumbPart}`;

  const json = await fetchJson(url, jar ? { jar } : undefined);
  const result = json?.quoteSummary?.result?.[0];
  const items = result?.incomeStatementHistory?.incomeStatementHistory;

  if (!Array.isArray(items) || items.length === 0) {
    const err = json?.quoteSummary?.error;
    const errMsg = err ? `${err.code ?? ''} ${err.description ?? ''}`.trim() : 'No incomeStatementHistory';
    throw new Error(`Yahoo response missing incomeStatementHistory for ${ticker}. ${errMsg}`);
  }

  const normalized = items
    .map((x) => {
      const fiscalYear = toYear(x?.endDate?.raw);
      const totalRevenue = x?.totalRevenue?.raw ?? null;
      const netIncome = x?.netIncome?.raw ?? null;
      return { fiscalYear, totalRevenue, netIncome };
    })
    .filter((x) => x.fiscalYear)
    .sort((a, b) => Number(b.fiscalYear) - Number(a.fiscalYear));

  return normalized.slice(0, 5);
}

function toYear(epochSeconds) {
  if (!epochSeconds) return '';
  const d = new Date(epochSeconds * 1000);
  return String(d.getUTCFullYear());
}

function fmtNumber(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '';
  return new Intl.NumberFormat('en-US').format(n);
}

function yyyymmddToEpochSeconds(yyyymmdd) {
  if (!yyyymmdd) return null;
  const s = String(yyyymmdd);
  if (!/^\d{8}$/.test(s)) return null;
  const year = Number(s.slice(0, 4));
  const month = Number(s.slice(4, 6));
  const day = Number(s.slice(6, 8));
  const ms = Date.UTC(year, month - 1, day, 0, 0, 0);
  return Math.floor(ms / 1000);
}

function findTimeseriesArray(timeseriesResults, key) {
  if (!Array.isArray(timeseriesResults)) return null;
  for (const r of timeseriesResults) {
    const arr = r?.[key];
    if (Array.isArray(arr)) return arr;
  }
  return null;
}

function pickTimeseriesValues(timeseriesResults, key) {
  const arr = findTimeseriesArray(timeseriesResults, key);
  if (!Array.isArray(arr)) return [];
  return arr
    .map((x) => {
      const end = x?.asOfDate ?? x?.endDate ?? null;
      const fiscalYear = end ? String(new Date(end).getUTCFullYear()) : '';
      const raw = x?.reportedValue?.raw ?? x?.reportedValue?.fmt ?? x?.reportedValue ?? x?.value?.raw ?? x?.value ?? null;
      const val = typeof raw === 'number' ? raw : (raw !== null && raw !== undefined && raw !== '' ? Number(raw) : null);
      return { fiscalYear, end, val: Number.isFinite(val) ? val : null };
    })
    .filter((r) => r.fiscalYear)
    .sort((a, b) => Number(b.fiscalYear) - Number(a.fiscalYear));
}

function pickFirstNonEmptySeries(timeseriesResults, keys) {
  for (const k of keys) {
    const rows = pickTimeseriesValues(timeseriesResults, k);
    if (rows.length > 0) return { key: k, rows };
  }
  return { key: null, rows: [] };
}

async function fetchYahooTimeseriesAnnual(ticker) {
  // This endpoint is often accessible without the crumb/cookie dance.
  const period2 = Math.floor(Date.now() / 1000);
  // ~12 years back to ensure we get several FY points.
  const period1 = yyyymmddToEpochSeconds('20130101') ?? (period2 - 12 * 365 * 24 * 3600);

  // Yahoo tag names vary by company; request a few candidates.
  const revenueCandidates = ['annualTotalRevenue', 'annualRevenues', 'annualRevenue'];
  const netIncomeCandidates = [
    'annualNetIncome',
    'annualNetIncomeCommonStockholders',
    'annualNetIncomeLoss',
    'annualNetIncomeApplicableToCommonShares',
    'annualProfitLoss',
  ];
  const types = [...revenueCandidates, ...netIncomeCandidates];
  const url = `https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/${encodeURIComponent(
    ticker,
  )}?type=${encodeURIComponent(types.join(','))}&merge=false&period1=${period1}&period2=${period2}`;

  const json = await fetchJson(url);
  const results = json?.timeseries?.result;
  if (!Array.isArray(results) || results.length === 0) {
    throw new Error(`Yahoo response missing timeseries.result for ${ticker}`);
  }

  const revenuePick = pickFirstNonEmptySeries(results, revenueCandidates);
  const netIncomePick = pickFirstNonEmptySeries(results, netIncomeCandidates);
  const revenueRows = revenuePick.rows;
  const netIncomeRows = netIncomePick.rows;

  if (revenueRows.length === 0 && netIncomeRows.length === 0) {
    throw new Error(`Yahoo timeseries has no annualTotalRevenue/annualNetIncome for ${ticker}`);
  }

  // If we're explicitly looking for net income and it's not present, force fallback.
  const hasAnyNetIncomeValue = netIncomeRows.some((r) => r.val !== null && r.val !== undefined);
  if (!hasAnyNetIncomeValue) {
    throw new Error(`Yahoo timeseries returned no usable net income values for ${ticker}`);
  }

  const years = new Set([...revenueRows, ...netIncomeRows].map((r) => r.fiscalYear));
  const merged = Array.from(years)
    .map((y) => {
      const totalRevenue = revenueRows.find((r) => r.fiscalYear === y)?.val ?? null;
      const netIncome = netIncomeRows.find((r) => r.fiscalYear === y)?.val ?? null;
      return { fiscalYear: y, totalRevenue, netIncome };
    })
    .sort((a, b) => Number(b.fiscalYear) - Number(a.fiscalYear));

  return merged.slice(0, 5);
}

async function fetchYahooIncomeStatementAnnual(ticker) {
  // Prefer the less fragile timeseries endpoint; fall back to quoteSummary if needed.
  try {
    return await fetchYahooTimeseriesAnnual(ticker);
  } catch (e) {
    const firstErr = e?.message ?? String(e);
    try {
      // First try quoteSummary directly (often works without crumb).
      try {
        return await fetchYahooIncomeStatementAnnualQuoteSummary(ticker);
      } catch (directErr) {
        const msg = directErr?.message ?? String(directErr);
        // Only do the crumb/cookie flow if we hit 401.
        if (!/HTTP\s+401\b/i.test(msg) && !/Unauthorized/i.test(msg) && !/Invalid Crumb/i.test(msg)) {
          throw directErr;
        }
      }

      const { jar, crumb } = await getYahooCrumbAndCookies(ticker);
      return await fetchYahooIncomeStatementAnnualQuoteSummary(ticker, { jar, crumb });
    } catch (fallbackErr) {
      const secondErr = fallbackErr?.message ?? String(fallbackErr);
      throw new Error(`Yahoo fetch failed. timeseries: ${firstErr}; quoteSummary fallback: ${secondErr}`);
    }
  }
}

async function main() {
  const ticker = (getArg('--ticker', 2) ?? 'CI').toUpperCase();
  console.log(`Yahoo Finance API: fundamentals-timeseries (annualTotalRevenue/annualNetIncome) with quoteSummary fallback`);
  console.log(`Ticker: ${ticker}`);

  const rows = await fetchYahooIncomeStatementAnnual(ticker);

  console.log('');
  console.log('FiscalYear | TotalRevenue | NetIncome | Currency');
  console.log('---|---:|---:|---');
  for (const r of rows) {
    console.log(`${r.fiscalYear} | ${fmtNumber(r.totalRevenue)} | ${fmtNumber(r.netIncome)} | USD`);
  }
}

main().catch((err) => {
  console.error('Failed:', err?.message ?? err);
  process.exitCode = 1;
});
