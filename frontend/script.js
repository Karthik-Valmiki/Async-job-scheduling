const API_METRICS = '/api/metrics';
const API_LOADTEST = '/api/loadtest';

async function fetchMetrics() {
    try {
        const res = await fetch(API_METRICS);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const d = await res.json();

        document.getElementById('valSubmitted').textContent = d.total_jobs_submitted;
        document.getElementById('valCompleted').textContent = d.total_jobs_completed;
        document.getElementById('valFailed').textContent = d.total_jobs_failed;
        document.getElementById('valQueued').textContent = d.total_jobs_queued;
        document.getElementById('valRunning').textContent = d.total_jobs_running;
        document.getElementById('valWorkers').textContent = d.active_workers;
        document.getElementById('valRetries').textContent = d.total_retries;
        
        const rate = d.success_rate_percent.toFixed(1) + '%';
        document.getElementById('valSuccessRate').textContent = rate;
        document.getElementById('valAvgTime').textContent = 
            d.average_execution_time_ms > 0 ? Math.round(d.average_execution_time_ms) + ' ms' : '0 ms';

        document.getElementById('lastUpdated').textContent = 'Updated: ' + new Date().toLocaleTimeString();
    } catch (err) {
        console.error('Metrics fetch error:', err);
        document.getElementById('lastUpdated').textContent = 'Connection error';
    }
}

// Polling
fetchMetrics();
setInterval(fetchMetrics, 2000);

// Load test form handling
const form = document.getElementById('loadTestForm');
const btn = document.getElementById('submitBtn');
const statusDiv = document.getElementById('testStatus');

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const duration = document.getElementById('duration').value;
    
    btn.disabled = true;
    btn.classList.add('loading');
    btn.textContent = 'Starting...';
    statusDiv.style.display = 'none';

    try {
        const res = await fetch(API_LOADTEST, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ duration_minutes: parseInt(duration) })
        });
        
        if (res.ok) {
            statusDiv.textContent = `Load test started for ${duration} minute(s)! Watch metrics.`;
            statusDiv.style.color = '#00a900';
            statusDiv.style.display = 'block';
            setTimeout(() => { statusDiv.style.display = 'none'; }, 5000);
        } else {
            throw new Error('Failed to start');
        }
    } catch (err) {
        console.error(err);
        statusDiv.textContent = 'Error starting test.';
        statusDiv.style.color = '#cc0000';
        statusDiv.style.display = 'block';
    } finally {
        btn.disabled = false;
        btn.classList.remove('loading');
        btn.textContent = 'Start Test';
    }
});
