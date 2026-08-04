import { companyPerformance_us } from './build/tools/companyPerformance_us.js';

async function run() {
  try {
    const result = await companyPerformance_us.run({
      ts_code: 'UNH',
      data_type: 'income',
      start_date: '20200101',
      end_date: '20251231',
    });

    if (result?.content?.[0]?.text) {
      console.log(result.content[0].text);
    } else {
      console.log(JSON.stringify(result, null, 2));
    }
  } catch (e) {
    console.error('Error:', e?.message ?? e);
    process.exitCode = 1;
  }
}

run();
