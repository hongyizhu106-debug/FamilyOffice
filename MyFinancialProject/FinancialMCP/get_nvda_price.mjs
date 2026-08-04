
import { stockData } from './build/tools/stockData.js';

async function run() {
    try {
        console.log("Fetching NVDA stock price for 2025-05-02...");
        const result = await stockData.run({
            code: 'NVDA',
            market_type: 'us',
            start_date: '20250502',
            end_date: '20250502'
        });
        
        if (result.content && result.content[0]) {
            console.log(result.content[0].text);
        } else {
            console.log("No data found.");
        }
    } catch (error) {
        console.error("Error:", error);
    }
}

run();
