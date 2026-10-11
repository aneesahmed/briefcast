let pieChartInstance = null;
let barChartInstance = null;

let rawDailyData = [];
let rawRecordsData = [];

async function fetchData() {
    try {
        const [dailyRes, recordsRes] = await Promise.all([
            fetch('/api/audit/daily'),
            fetch('/api/audit/records')
        ]);
        
        rawDailyData = await dailyRes.json();
        rawRecordsData = await recordsRes.json();
        
        applyFilters();
    } catch (error) {
        console.error("Error fetching telemetry data:", error);
    }
}

function applyFilters() {
    const dateFilter = document.getElementById('dateFilter').value;
    const stepFilter = document.getElementById('stepFilter').value;
    
    let filteredDaily = [...rawDailyData];
    let filteredRecords = [...rawRecordsData];
    
    // Apply Date Filter
    if (dateFilter !== 'all') {
        const cutoffDate = new Date();
        if (dateFilter === '7days') cutoffDate.setDate(cutoffDate.getDate() - 7);
        if (dateFilter === '30days') cutoffDate.setDate(cutoffDate.getDate() - 30);
        
        filteredDaily = filteredDaily.filter(d => new Date(d.audit_date) >= cutoffDate);
        filteredRecords = filteredRecords.filter(r => new Date(r.completed_at) >= cutoffDate);
    }
    
    updateKPIs(filteredDaily, filteredRecords, stepFilter);
    updateCharts(filteredDaily, stepFilter);
    updateTable(filteredRecords, stepFilter);
}

function updateKPIs(dailyData, recordsData, stepFilter) {
    let totalDocs = 0;
    let totalSpend = 0;
    let totalTokens = 0;
    let totalAudio = 0;
    
    dailyData.forEach(day => {
        totalDocs += day.total_files;
        if (stepFilter === 'all') {
            totalSpend += day.total_net_cost_usd;
            totalTokens += day.total_net_tokens;
        } else {
            totalSpend += day[`total_${stepFilter}_cost_usd`];
            totalTokens += day[`total_${stepFilter}_tokens`];
        }
    });

    recordsData.forEach(record => {
        if (record.audio_size_mb > 0 || record.audio_tokens > 0) {
            totalAudio++;
        }
    });
    
    const avgCost = totalDocs > 0 ? (totalSpend / totalDocs) : 0;
    
    document.getElementById('kpi-total-docs').innerText = totalDocs.toLocaleString();
    document.getElementById('kpi-total-spend').innerText = `$${totalSpend.toFixed(4)}`;
    document.getElementById('kpi-avg-cost').innerText = `$${avgCost.toFixed(4)}`;
    document.getElementById('kpi-total-tokens').innerText = totalTokens.toLocaleString();
    document.getElementById('kpi-total-audio').innerText = totalAudio.toLocaleString();
}

function updateCharts(dailyData, stepFilter) {
    const chronologicalData = [...dailyData].reverse();
    
    const labels = chronologicalData.map(d => d.audit_date);
    const spendData = chronologicalData.map(d => {
        return stepFilter === 'all' ? d.total_net_cost_usd : d[`total_${stepFilter}_cost_usd`];
    });
    
    // Bar Chart
    const barCtx = document.getElementById('dailySpendChart').getContext('2d');
    if (barChartInstance) barChartInstance.destroy();
    
    barChartInstance = new Chart(barCtx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: `Daily Cost (USD) - ${stepFilter.toUpperCase()}`,
                data: spendData,
                backgroundColor: 'rgba(99, 102, 241, 0.8)',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { y: { beginAtZero: true } }
        }
    });

    // Pie Chart (Ignores step filter, only obeys date filter to show accurate breakdown)
    let ocr = 0, sum = 0, trans = 0, aud = 0;
    dailyData.forEach(d => {
        ocr += d.total_ocr_cost_usd;
        sum += d.total_summary_cost_usd;
        trans += d.total_translation_cost_usd;
        aud += d.total_audio_cost_usd;
    });

    const pieCtx = document.getElementById('costBreakdownChart').getContext('2d');
    if (pieChartInstance) pieChartInstance.destroy();

    pieChartInstance = new Chart(pieCtx, {
        type: 'doughnut',
        data: {
            labels: ['OCR', 'Summary', 'Translation', 'Audio TTS'],
            datasets: [{
                data: [ocr, sum, trans, aud],
                backgroundColor: ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'right' } }
        }
    });
}

function updateTable(records, stepFilter) {
    const tbody = document.getElementById('audit-table-body');
    tbody.innerHTML = '';
    
    records.slice(0, 50).forEach(record => {
        const dateStr = new Date(record.completed_at).toLocaleString();
        const tr = document.createElement('tr');
        
        let tokens = stepFilter === 'all' ? record.net_tokens : record[`${stepFilter}_tokens`];
        let cost = stepFilter === 'all' ? record.net_cost_usd : record[`${stepFilter}_cost_usd`];
        
        tr.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${dateStr}</td>
            <td class="px-6 py-4 text-sm font-medium text-gray-900 truncate max-w-xs" title="${record.filename}">${record.filename}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-gray-100 text-gray-800">
                    ${record.symbol || 'N/A'}
                </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">${(tokens || 0).toLocaleString()}</td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-emerald-600 font-medium">$${(cost || 0).toFixed(4)}</td>
        `;
        tbody.appendChild(tr);
    });
}

document.addEventListener('DOMContentLoaded', fetchData);
