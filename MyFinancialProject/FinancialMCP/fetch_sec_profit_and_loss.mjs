import https from 'node:https';

function getArg(name, fallbackIndex) {
  const idx = process.argv.indexOf(name);
  if (idx !== -1 && process.argv[idx + 1]) return process.argv[idx + 1];
  return process.argv[fallbackIndex] ?? null;
}

function fmtNumber(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '';
  return new Intl.NumberFormat('en-US').format(n);
}

function padCik(cik) {
  const s = String(cik ?? '').replace(/\D/g, '');
  return s.padStart(10, '0');
}

function request(url, { headers = {}, timeoutMs = 20000, maxRedirects = 5 } = {}) {
  const defaultHeaders = {
    // SEC asks for a descriptive UA. Allow override via env.
    'user-agent': process.env.SEC_USER_AGENT || 'MyFinancialProject (personal research)',
    accept: 'application/json,text/plain,*/*',
    'accept-language': 'en-US,en;q=0.9',
    'accept-encoding': 'identity',
  };

  const effectiveHeaders = { ...defaultHeaders, ...headers };

  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers: effectiveHeaders, maxHeaderSize: 128 * 1024 }, (res) => {
      const status = res.statusCode ?? 0;
      const location = res.headers.location;
      if (status >= 300 && status < 400 && location) {
        if (maxRedirects <= 0) {
          res.resume();
          return reject(new Error(`Too many redirects for ${url}`));
        }
        const redirected = new URL(location, url).toString();
        res.resume();
        return resolve(request(redirected, { headers, timeoutMs, maxRedirects: maxRedirects - 1 }));
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
    });

    req.on('error', reject);
    req.setTimeout(timeoutMs, () => {
      req.destroy(new Error(`Request timeout after ${timeoutMs}ms for ${url}`));
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

async function resolveCikByTicker(ticker) {
  // This file is stable and doesn’t require an API key.
  const url = 'https://www.sec.gov/files/company_tickers.json';
  const json = await fetchJson(url);
  const wanted = String(ticker).toUpperCase();

  // Format: { "0": { cik_str, ticker, title }, "1": ... }
  const values = Array.isArray(json) ? json : Object.values(json ?? {});
  const hit = values.find((x) => String(x?.ticker ?? '').toUpperCase() === wanted);
  if (!hit?.cik_str) throw new Error(`Ticker not found in SEC mapping: ${ticker}`);

  return { cik: padCik(hit.cik_str), title: hit.title ?? ticker };
}

function pickAnnualFactSeries(companyFacts, tagCandidates) {
  const facts = companyFacts?.facts?.['us-gaap'];
  for (const tag of tagCandidates) {
    const unitMap = facts?.[tag]?.units;
    const usd = unitMap?.USD;
    if (Array.isArray(usd) && usd.length) {
      return { tag, unit: 'USD', series: usd };
    }
  }
  return null;
}

function normalizeAnnual(series) {
  // Prefer 10-K FY values; fallback to any annual-ish items.
  const annual = series
    .filter((x) => x && typeof x.val === 'number')
    .filter((x) => {
      const form = String(x.form ?? '');
      const fp = String(x.fp ?? '');
      return (
        ['10-K', '20-F', '40-F'].includes(form) && (fp === 'FY' || fp === 'CY' || fp === '')
      );
    })
    .map((x) => {
      const end = String(x.end ?? '');
      const fiscalYear = end ? String(new Date(end).getUTCFullYear()) : String(x.fy ?? '');
      return { fiscalYear, end, val: x.val };
    })
    .filter((x) => x.fiscalYear && x.fiscalYear !== 'NaN');

  // Deduplicate by fiscalYear (keep latest end).
  const byYear = new Map();
  for (const row of annual) {
    const prev = byYear.get(row.fiscalYear);
    if (!prev || String(row.end) > String(prev.end)) byYear.set(row.fiscalYear, row);
  }

  return Array.from(byYear.values()).sort((a, b) => Number(b.fiscalYear) - Number(a.fiscalYear));
}

async function fetchSecAnnualPnL(ticker) {
  const { cik, title } = await resolveCikByTicker(ticker);
  const factsUrl = `https://data.sec.gov/api/xbrl/companyfacts/CIK${cik}.json`;
  const companyFacts = await fetchJson(factsUrl);

  const netIncomeFact = pickAnnualFactSeries(companyFacts, ['NetIncomeLoss', 'ProfitLoss']);
  const revenueFact = pickAnnualFactSeries(companyFacts, [
    'Revenues',
    'SalesRevenueNet',
    'RevenueFromContractWithCustomerExcludingAssessedTax',
  ]);

  if (!netIncomeFact && !revenueFact) {
    throw new Error(`No us-gaap NetIncome/Revenue facts found for ${ticker} (CIK${cik})`);
  }

  const netIncomeRows = netIncomeFact ? normalizeAnnual(netIncomeFact.series) : [];
  const revenueRows = revenueFact ? normalizeAnnual(revenueFact.series) : [];

  const years = new Set([...netIncomeRows, ...revenueRows].map((x) => x.fiscalYear));
  const merged = Array.from(years)
    .map((y) => {
      const ni = netIncomeRows.find((r) => r.fiscalYear === y)?.val ?? null;
      const rev = revenueRows.find((r) => r.fiscalYear === y)?.val ?? null;
      return { fiscalYear: y, totalRevenue: rev, netIncome: ni };
    })
    .sort((a, b) => Number(b.fiscalYear) - Number(a.fiscalYear));

  return { title, cik, netIncomeTag: netIncomeFact?.tag, revenueTag: revenueFact?.tag, rows: merged.slice(0, 5) };
}

async function main() {
  const ticker = (getArg('--ticker', 2) ?? 'UNH').toUpperCase();
  console.log('SEC EDGAR XBRL: companyfacts (annual-ish)');
  console.log(`Ticker: ${ticker}`);

  const out = await fetchSecAnnualPnL(ticker);

  console.log(`CIK: ${out.cik}`);
  if (out.revenueTag) console.log(`Revenue tag: us-gaap:${out.revenueTag}`);
  if (out.netIncomeTag) console.log(`Net income tag: us-gaap:${out.netIncomeTag}`);

  console.log('');
  console.log('FiscalYear | TotalRevenue | NetIncome | Currency');
  console.log('---|---:|---:|---');
  for (const r of out.rows) {
    console.log(`${r.fiscalYear} | ${fmtNumber(r.totalRevenue)} | ${fmtNumber(r.netIncome)} | USD`);
  }
}

main().catch((err) => {
  console.error('Failed:', err?.message ?? err);
  process.exitCode = 1;
});
