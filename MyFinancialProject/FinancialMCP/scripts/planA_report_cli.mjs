import { readFile } from 'node:fs/promises';
import process from 'node:process';
import { planAReportPdf } from '../build/tools/planAReportPdf.js';

function parseArgs(argv) {
  const out = {};
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--job') {
      out.job = argv[i + 1];
      i++;
    } else if (a === '--help' || a === '-h') {
      out.help = true;
    }
  }
  return out;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help || !args.job) {
    console.log('Usage: node scripts/planA_report_cli.mjs --job <job.json>');
    process.exit(args.help ? 0 : 2);
  }

  const jobPath = String(args.job);
  const job = JSON.parse(await readFile(jobPath, 'utf-8'));

  const res = await planAReportPdf.run(job);

  // Prefer machine-readable meta for callers (Python).
  if (res && typeof res === 'object' && res.meta) {
    process.stdout.write(JSON.stringify({ ok: true, ...res.meta }, null, 2));
    process.stdout.write('\n');
    return;
  }

  // Fallback: dump whatever the tool returned.
  process.stdout.write(JSON.stringify({ ok: true, result: res }, null, 2));
  process.stdout.write('\n');
}

main().catch((err) => {
  const msg = err instanceof Error ? err.message : String(err);
  process.stderr.write(`ERROR: ${msg}\n`);
  process.exit(1);
});
