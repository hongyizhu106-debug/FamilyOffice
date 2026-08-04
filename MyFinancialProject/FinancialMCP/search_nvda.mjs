import { searchBaiduNews } from './build/tools/crawler/baiduNews.js';

async function run() {
    try {
        console.log("Searching for NVIDIA Q1 2025 financial results...");
        // Search for "NVIDIA FY2026 Q1 earnings" as that is the correct fiscal period for early 2025
        const results = await searchBaiduNews(['NVIDIA', 'FY2026', 'Q1', 'earnings']);
        
        console.log("Found " + results.length + " results.");
        results.forEach((item, index) => {
            console.log(`\n--- Result ${index + 1} ---`);
            console.log(`Title: ${item.title}`);
            console.log(`Source: ${item.source}`);
            console.log(`Date: ${item.publishTime}`);
            console.log(`Summary: ${item.summary}`);
            console.log(`URL: ${item.url}`);
        });

        // Also search for "NVIDIA Q1 2025 revenue net income" to be sure
        console.log("\nSearching for NVIDIA Q1 2025 revenue net income...");
        const results2 = await searchBaiduNews(['NVIDIA', 'Q1', '2025', 'revenue', 'net', 'income']);
        results2.forEach((item, index) => {
            console.log(`\n--- Result ${index + 1} (Set 2) ---`);
            console.log(`Title: ${item.title}`);
            console.log(`Source: ${item.source}`);
            console.log(`Date: ${item.publishTime}`);
            console.log(`Summary: ${item.summary}`);
            console.log(`URL: ${item.url}`);
        });

    } catch (error) {
        console.error("Error running search:", error);
    }
}

run();
