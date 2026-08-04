import { companyPerformance_us } from './build/tools/companyPerformance_us.js';

async function run() {
    try {
        console.log("Fetching NVDA financial data for 2025 Q1...");
        
        // Income Statement
        console.log("\n--- Income Statement ---");
        const incomeResult = await companyPerformance_us.run({
            ts_code: 'NVDA',
            data_type: 'income',
            start_date: '20250101',
            end_date: '20250331'
        });
        
        if (incomeResult.content && incomeResult.content[0]) {
            console.log(incomeResult.content[0].text);
        } else {
            console.log("No income data found.");
        }

        // Balance Sheet
        console.log("\n--- Balance Sheet ---");
        const balanceResult = await companyPerformance_us.run({
            ts_code: 'NVDA',
            data_type: 'balance',
            start_date: '20250101',
            end_date: '20250331'
        });

        if (balanceResult.content && balanceResult.content[0]) {
            console.log(balanceResult.content[0].text);
        } else {
            console.log("No balance sheet data found.");
        }

        // Cash Flow
        console.log("\n--- Cash Flow ---");
        const cashflowResult = await companyPerformance_us.run({
            ts_code: 'NVDA',
            data_type: 'cashflow',
            start_date: '20250101',
            end_date: '20250331'
        });

        if (cashflowResult.content && cashflowResult.content[0]) {
            console.log(cashflowResult.content[0].text);
        } else {
            console.log("No cash flow data found.");
        }

    } catch (error) {
        console.error("Error:", error);
    }
}

run();
