// Global state variables
let allRuns = [];
let mainChart = null;
let splitsChart = null;
let hrChart = null;
let map = null;
let activeTab = 'progress';
let progressCurvesData = null;
let showPaceMetric = true;
let showHrMetric = true;
let showDistanceMetric = true;

// Sorting and global colorbar state
let historySortColumn = 'date';
let historySortAsc = false;
let compareSortColumn = 'date';
let compareSortAsc = false;
let globalPaceBounds = { min: 480, max: 630 };
let listenersInitialized = false;
let compareChart = null;
let compareChartMetric = 'distance_mi';



// Filter helper functions
function initFilterLimits() {
    if (allRuns.length === 0) return;
    
    // Find min and max dates in allRuns
    const dates = allRuns.map(r => r.date).sort();
    const minDate = dates[0];
    const maxDate = dates[dates.length - 1];
    
    const startInput = document.getElementById('filter-start-date');
    const endInput = document.getElementById('filter-end-date');
    
    if (startInput && endInput) {
        startInput.min = minDate;
        startInput.max = maxDate;
        startInput.value = minDate;
        
        endInput.min = minDate;
        endInput.max = maxDate;
        endInput.value = maxDate;
    }

    // Find min and max distances in allRuns
    const distances = allRuns.map(r => r.distance_mi);
    const minDist = Math.min(...distances);
    const maxDist = Math.max(...distances);

    // Floor and ceil to 1 decimal place to give clean limits
    const sliderMinLimit = Math.floor(minDist * 10) / 10;
    const sliderMaxLimit = Math.ceil(maxDist * 10) / 10;

    const minSlider = document.getElementById('filter-min-dist');
    const maxSlider = document.getElementById('filter-max-dist');

    if (minSlider && maxSlider) {
        minSlider.min = sliderMinLimit;
        minSlider.max = sliderMaxLimit;
        minSlider.value = sliderMinLimit;

        maxSlider.min = sliderMinLimit;
        maxSlider.max = sliderMaxLimit;
        maxSlider.value = sliderMaxLimit;

        // Update the slider track highlights and labels
        updateSliderUI();
    }
}

function updateSliderUI() {
    const minSlider = document.getElementById('filter-min-dist');
    const maxSlider = document.getElementById('filter-max-dist');
    const trackFill = document.getElementById('slider-track-fill');
    const sliderValueText = document.getElementById('dist-slider-value');

    if (!minSlider || !maxSlider || !trackFill || !sliderValueText) return;

    let minVal = parseFloat(minSlider.value);
    let maxVal = parseFloat(maxSlider.value);

    // Prevent thumbs from crossing
    if (minVal > maxVal) {
        minSlider.value = maxVal;
        minVal = maxVal;
    }

    // Calculate percentage positions
    const minLimit = parseFloat(minSlider.min);
    const maxLimit = parseFloat(minSlider.max);
    const range = maxLimit - minLimit;

    const pctStart = range > 0 ? ((minVal - minLimit) / range) * 100 : 0;
    const pctEnd = range > 0 ? ((maxVal - minLimit) / range) * 100 : 100;

    trackFill.style.left = `${pctStart}%`;
    trackFill.style.width = `${pctEnd - pctStart}%`;

    // Dynamic hint: Count how many runs are within this custom range!
    const filteredCount = allRuns.filter(r => r.distance_mi >= minVal && r.distance_mi <= maxVal).length;

    sliderValueText.textContent = `${minVal.toFixed(1)} - ${maxVal.toFixed(1)} mi (${filteredCount} runs)`;
}

function getFilteredRuns() {
    const startVal = document.getElementById('filter-start-date')?.value;
    const endVal = document.getElementById('filter-end-date')?.value;
    const minSlider = document.getElementById('filter-min-dist');
    const maxSlider = document.getElementById('filter-max-dist');

    let filtered = [...allRuns];

    if (startVal) {
        filtered = filtered.filter(r => r.date >= startVal);
    }
    if (endVal) {
        filtered = filtered.filter(r => r.date <= endVal);
    }

    if (minSlider && maxSlider) {
        const minVal = parseFloat(minSlider.value);
        const maxVal = parseFloat(maxSlider.value);
        filtered = filtered.filter(r => r.distance_mi >= minVal && r.distance_mi <= maxVal);
    }

    return filtered;
}

function setupFilterListeners() {
    const startInput = document.getElementById('filter-start-date');
    const endInput = document.getElementById('filter-end-date');
    const minSlider = document.getElementById('filter-min-dist');
    const maxSlider = document.getElementById('filter-max-dist');
    const resetBtn = document.getElementById('btn-reset-filters');

    const onChange = () => {
        updateOverviewStats();
        renderHistoryTable();
        renderMainChart();
    };

    if (startInput) startInput.addEventListener('change', onChange);
    if (endInput) endInput.addEventListener('change', onChange);

    const onSliderInput = (e) => {
        const minVal = parseFloat(minSlider.value);
        const maxVal = parseFloat(maxSlider.value);

        if (e.target.id === 'filter-min-dist' && minVal > maxVal) {
            minSlider.value = maxVal;
        } else if (e.target.id === 'filter-max-dist' && maxVal < minVal) {
            maxSlider.value = minVal;
        }

        updateSliderUI();
        onChange();
    };

    if (minSlider) minSlider.addEventListener('input', onSliderInput);
    if (maxSlider) maxSlider.addEventListener('input', onSliderInput);
    
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            initFilterLimits();
            historySortColumn = 'date';
            historySortAsc = false;
            onChange();
        });
    }
}

function setupMetricToggleListeners() {
    const paceBtn = document.getElementById('toggle-pace');
    const hrBtn = document.getElementById('toggle-hr');
    const distBtn = document.getElementById('toggle-dist');

    if (paceBtn) {
        paceBtn.addEventListener('click', () => {
            showPaceMetric = !showPaceMetric;
            paceBtn.classList.toggle('active', showPaceMetric);
            renderMainChart();
        });
    }

    if (hrBtn) {
        hrBtn.addEventListener('click', () => {
            showHrMetric = !showHrMetric;
            hrBtn.classList.toggle('active', showHrMetric);
            renderMainChart();
        });
    }

    if (distBtn) {
        distBtn.addEventListener('click', () => {
            showDistanceMetric = !showDistanceMetric;
            distBtn.classList.toggle('active', showDistanceMetric);
            renderMainChart();
        });
    }
}


// Helper function to format seconds to MM:SS
function formatDuration(totalSeconds) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Helper to format pace in seconds to M:SS
function formatPace(paceSec) {
    if (!paceSec || isNaN(paceSec)) return 'N/A';
    const mins = Math.floor(paceSec / 60);
    const secs = paceSec % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Helper to parse pace string (M:SS) to seconds
function parsePaceToSec(paceStr) {
    if (!paceStr || paceStr === 'N/A') return null;
    const parts = paceStr.split(':');
    if (parts.length !== 2) return null;
    return parseInt(parts[0]) * 60 + parseInt(parts[1]);
}

// Helper to calculate simple linear regression trendline
function getTrendlinePoints(xValues, yValues) {
    const n = xValues.length;
    if (n < 2) return [];

    let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
    for (let i = 0; i < n; i++) {
        sumX += xValues[i];
        sumY += yValues[i];
        sumXY += xValues[i] * yValues[i];
        sumXX += xValues[i] * xValues[i];
    }

    const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;

    return xValues.map(x => slope * x + intercept);
}

// Calculate global pace bounds for consistent heatmap colorbar (clamped to 5th-95th percentile to remove outliers)
function calculateGlobalPaceBounds() {
    let allPaces = [];
    allRuns.forEach(r => {
        if (r.splits) {
            r.splits.forEach(s => {
                if (s.pace_sec_mi > 0) {
                    allPaces.push(s.pace_sec_mi);
                }
            });
        }
    });
    if (allPaces.length > 0) {
        // Sort to calculate percentiles and eliminate GPS/stopped outliers
        allPaces.sort((a, b) => a - b);
        const p5Idx = Math.floor(allPaces.length * 0.05);
        const p95Idx = Math.floor(allPaces.length * 0.95);
        
        globalPaceBounds.min = allPaces[p5Idx];
        globalPaceBounds.max = allPaces[p95Idx];
        
        // Keep a minimum range of 1 minute to prevent division-by-zero or flat coloring
        if (globalPaceBounds.max - globalPaceBounds.min < 60) {
            globalPaceBounds.max = globalPaceBounds.min + 60;
        }
    }
    
    // Inject dynamic values into the colorbar legend
    const slowVal = document.getElementById('legend-slow-val');
    const fastVal = document.getElementById('legend-fast-val');
    if (slowVal && fastVal) {
        slowVal.textContent = formatPace(globalPaceBounds.max) + ' /mi';
        fastVal.textContent = formatPace(globalPaceBounds.min) + ' /mi';
    }
}

// Update table header sort arrows
function updateSortIcons(tableId, currentColumn, isAsc) {
    const headers = document.querySelectorAll(`#${tableId} th[data-sort]`);
    headers.forEach(th => {
        const icon = th.querySelector('i');
        if (!icon) return;
        
        const col = th.getAttribute('data-sort');
        if (col === currentColumn) {
            icon.className = isAsc ? 'fa-solid fa-sort-up' : 'fa-solid fa-sort-down';
            th.classList.add('sorted-col');
        } else {
            icon.className = 'fa-solid fa-sort';
            th.classList.remove('sorted-col');
        }
    });
}

// Bind table sort clicks
function setupTableSortListeners() {
    const historyHeaders = document.querySelectorAll('#history-table th[data-sort]');
    historyHeaders.forEach(th => {
        th.addEventListener('click', () => {
            const col = th.getAttribute('data-sort');
            if (historySortColumn === col) {
                historySortAsc = !historySortAsc;
            } else {
                historySortColumn = col;
                historySortAsc = (col === 'date') ? false : true;
            }
            renderHistoryTable();
        });
    });

    const compareHeaders = document.querySelectorAll('#compare-table th[data-sort]');
    compareHeaders.forEach(th => {
        th.addEventListener('click', () => {
            const col = th.getAttribute('data-sort');
            if (compareSortColumn === col) {
                compareSortAsc = !compareSortAsc;
            } else {
                compareSortColumn = col;
                compareSortAsc = (col === 'date' || col === 'similarity') ? false : true;
            }
            renderCompareResults();
        });
    });
}

// Bind Fitbit sync button click
function setupSyncBtnListener() {
    const btn = document.getElementById('btn-sync-data');
    if (!btn) return;
    
    btn.addEventListener('click', async () => {
        btn.disabled = true;
        btn.classList.add('loading');
        const spanText = btn.querySelector('span');
        const originalText = spanText.textContent;
        spanText.textContent = 'Syncing...';
        
        try {
            const res = await fetch('/api/sync', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
                alert('Fitbit data sync completed successfully!');
            } else {
                alert('Sync failed: ' + (data.error || 'Unknown error'));
            }
        } catch (e) {
            console.error('Error syncing:', e);
            alert('Error syncing data: ' + e.message);
        } finally {
            btn.disabled = false;
            btn.classList.remove('loading');
            spanText.textContent = originalText;
            // Reload all runs from server
            initDashboard();
        }
    });
}

// Fetch all runs and initialize dashboard
async function initDashboard() {
    try {
        const response = await fetch('/api/runs');
        allRuns = await response.json();
        
        if (!allRuns || allRuns.length === 0) {
            document.getElementById('runs-table-body').innerHTML = `
                <tr><td colspan="8" class="text-center">No running data found. Please run get_data.py to pull your Google Fit history.</td></tr>
            `;
            return;
        }

        // Calculate global bounds across entire history for consistent color mapping
        calculateGlobalPaceBounds();

        // Initialize date bounds, distance sliders limits, and attach filter event listeners
        initFilterLimits();
        
        if (!listenersInitialized) {
            setupFilterListeners();
            setupTabListeners();
            setupMetricToggleListeners();
            setupModalListeners();
            initCompareView();
            setupTableSortListeners();
            setupSyncBtnListener();
            listenersInitialized = true;
        }

        // Calculate and update metrics
        updateOverviewStats();
        
        // Build the training history table
        renderHistoryTable();
        
        // Render default chart
        renderMainChart();
        
    } catch (error) {
        console.error('Error initializing dashboard:', error);
        document.getElementById('runs-table-body').innerHTML = `
            <tr><td colspan="8" class="text-center text-red">Error fetching data from API. Make sure Flask server is running.</td></tr>
        `;
    }
}

// Calculate and show summary cards
function updateOverviewStats() {
    const runs = getFilteredRuns();
    const totalRuns = runs.length;
    document.getElementById('stat-total-runs').textContent = totalRuns;
    document.getElementById('runs-count').textContent = `${totalRuns} Runs`;

    let totalDist = 0;
    let totalSec = 0;
    let hrSum = 0;
    let hrCount = 0;

    runs.forEach(run => {
        totalDist += run.distance_mi;
        totalSec += run.duration_sec;
        if (run.avg_hr) {
            hrSum += run.avg_hr;
            hrCount++;
        }
    });

    document.getElementById('stat-total-distance').textContent = `${totalDist.toFixed(1)} mi`;
    
    // Average pace = total duration / total distance
    if (totalDist > 0) {
        const avgPaceSec = totalSec / totalDist;
        document.getElementById('stat-avg-pace').textContent = `${formatPace(Math.round(avgPaceSec))} /mi`;
    } else {
        document.getElementById('stat-avg-pace').textContent = '-- /mi';
    }

    if (hrCount > 0) {
        document.getElementById('stat-avg-hr').textContent = `${Math.round(hrSum / hrCount)} bpm`;
    } else {
        document.getElementById('stat-avg-hr').textContent = '-- bpm';
    }
}

// Render runs in table
function renderHistoryTable() {
    const tbody = document.getElementById('runs-table-body');
    tbody.innerHTML = '';

    const runs = getFilteredRuns();
    if (runs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center">No runs match the selected filters.</td></tr>`;
        return;
    }

    // Sort runs
    runs.sort((a, b) => {
        let valA = a[historySortColumn];
        let valB = b[historySortColumn];
        
        // Handle null values
        if (valA === null || valA === undefined) return historySortAsc ? 1 : -1;
        if (valB === null || valB === undefined) return historySortAsc ? -1 : 1;
        
        if (historySortColumn === 'date') {
            const valA = a.datetime || '';
            const valB = b.datetime || '';
            return historySortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        
        if (typeof valA === 'string') {
            return historySortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else {
            return historySortAsc ? valA - valB : valB - valA;
        }
    });

    updateSortIcons('history-table', historySortColumn, historySortAsc);

    runs.forEach(run => {
        const tr = document.createElement('tr');
        tr.addEventListener('click', () => openRunModal(run.id));
        
        tr.innerHTML = `
            <td><strong>${run.date}</strong> <span class="modal-run-time">${run.time}</span></td>
            <td>${run.distance_mi.toFixed(2)} mi</td>
            <td>${run.duration_str}</td>
            <td><i class="fa-solid fa-gauge-high" style="color: var(--color-primary); font-size: 12px; margin-right: 4px;"></i> ${run.pace_str}</td>
            <td>${run.avg_hr ? `<i class="fa-solid fa-heartbeat" style="color: var(--color-red); font-size: 12px; margin-right: 4px;"></i> ${run.avg_hr} bpm` : 'N/A'}</td>
            <td>${run.cadence ? `${run.cadence} spm` : 'N/A'}</td>
            <td>${run.stride_cm ? `${run.stride_cm} cm` : 'N/A'}</td>
            <td class="text-right">
                <button class="action-btn">
                    <i class="fa-solid fa-circle-info"></i> View Details
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Set up chart tab buttons
function setupTabListeners() {
    const buttons = document.querySelectorAll('.tab-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            activeTab = btn.getAttribute('data-chart');
            renderMainChart();
        });
    });
}

// Render Main Performance Charts
function renderMainChart() {
    if (mainChart) {
        mainChart.destroy();
    }

    const ctx = document.getElementById('mainChart').getContext('2d');
    
    // Toggle colorbar legend for Pace vs Distance & Pace Comparison
    const legendContainer = document.getElementById('custom-legend-container');
    if (legendContainer) {
        legendContainer.style.display = (activeTab === 'distPace' || activeTab === 'progressCurves') ? 'flex' : 'none';
    }
    
    // Toggle metric toggles and separator visibility
    const progressToggles = document.getElementById('progress-metric-toggles');
    const separator = document.getElementById('metric-toggles-separator');
    const isProgress = (activeTab === 'progress');
    if (progressToggles) {
        progressToggles.style.display = isProgress ? 'flex' : 'none';
    }
    if (separator) {
        separator.style.display = isProgress ? 'block' : 'none';
    }
    
    const runs = getFilteredRuns();
    
    // Check if we have data to plot
    if (runs.length === 0 && activeTab !== 'progressCurves') {
        ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
        ctx.save();
        ctx.fillStyle = '#94a3b8';
        ctx.font = '16px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('No data matches the selected filters.', ctx.canvas.width / 2, ctx.canvas.height / 2);
        ctx.restore();
        return;
    }

    // Labels are dates (for category charts)
    const labels = runs.map(r => r.date);

    if (activeTab === 'progress') {
        // Fitness Progress: Pace, Heart Rate and Distance
        const paces = runs.map(r => ({ x: new Date(r.datetime).getTime(), y: r.pace_sec_mi }));
        const hrs = runs.map(r => ({ x: new Date(r.datetime).getTime(), y: r.avg_hr || null })).filter(h => h.y !== null);
        const dists = runs.map(r => ({ x: new Date(r.datetime).getTime(), y: r.distance_mi }));

        // Filter valid points for trendline
        const validPaces = paces.filter(p => p.y > 0);
        const validHrs = hrs.filter(h => h.y > 0);
        const validDists = dists.filter(d => d.y > 0);

        const paceTrend = getTrendlinePoints(validPaces.map(p => p.x), validPaces.map(p => p.y));
        const hrTrend = getTrendlinePoints(validHrs.map(h => h.x), validHrs.map(h => h.y));
        const distTrend = getTrendlinePoints(validDists.map(d => d.x), validDists.map(d => d.y));

        const paceTrendData = validPaces.map((p, idx) => ({ x: p.x, y: paceTrend[idx] }));
        const hrTrendData = validHrs.map((h, idx) => ({ x: h.x, y: hrTrend[idx] }));
        const distTrendData = validDists.map((d, idx) => ({ x: d.x, y: distTrend[idx] }));

        mainChart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Average Pace (min/mi)',
                        data: paces,
                        borderColor: '#38bdf8',
                        backgroundColor: 'rgba(56, 189, 248, 0.05)',
                        borderWidth: 3,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        yAxisID: 'yPace',
                        tension: 0.15,
                        hidden: !showPaceMetric
                    },
                    {
                        label: 'Pace Trendline',
                        data: paceTrendData,
                        borderColor: 'rgba(56, 189, 248, 0.3)',
                        borderWidth: 1.5,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false,
                        yAxisID: 'yPace',
                        hidden: !showPaceMetric
                    },
                    {
                        label: 'Average Heart Rate (bpm)',
                        data: hrs,
                        borderColor: '#f87171',
                        backgroundColor: 'transparent',
                        borderWidth: 3,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        yAxisID: 'yHr',
                        tension: 0.15,
                        hidden: !showHrMetric
                    },
                    {
                        label: 'Heart Rate Trendline',
                        data: hrTrendData,
                        borderColor: 'rgba(248, 113, 113, 0.3)',
                        borderWidth: 1.5,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false,
                        yAxisID: 'yHr',
                        hidden: !showHrMetric
                    },
                    {
                        label: 'Distance (miles)',
                        data: dists,
                        borderColor: '#34d399',
                        backgroundColor: 'transparent',
                        borderWidth: 3,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        yAxisID: 'yDistance',
                        tension: 0.15,
                        hidden: !showDistanceMetric
                    },
                    {
                        label: 'Distance Trendline',
                        data: distTrendData,
                        borderColor: 'rgba(52, 211, 153, 0.3)',
                        borderWidth: 1.5,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false,
                        yAxisID: 'yDistance',
                        hidden: !showDistanceMetric
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: {
                            color: '#94a3b8',
                            font: { family: 'Inter' },
                            filter: function(item) {
                                // Only show legend items for Pace (0), HR (2), and Distance (4)
                                return item.datasetIndex === 0 || item.datasetIndex === 2 || item.datasetIndex === 4;
                            }
                        },
                        onClick: function(e, legendItem, legend) {
                            const index = legendItem.datasetIndex;
                            if (index === 0) {
                                showPaceMetric = !showPaceMetric;
                                const btn = document.getElementById('toggle-pace');
                                if (btn) btn.classList.toggle('active', showPaceMetric);
                            } else if (index === 2) {
                                showHrMetric = !showHrMetric;
                                const btn = document.getElementById('toggle-hr');
                                if (btn) btn.classList.toggle('active', showHrMetric);
                            } else if (index === 4) {
                                showDistanceMetric = !showDistanceMetric;
                                const btn = document.getElementById('toggle-dist');
                                if (btn) btn.classList.toggle('active', showDistanceMetric);
                            }
                            renderMainChart();
                        }
                    },
                    tooltip: {
                        callbacks: {
                            title: function(context) {
                                return new Date(context[0].parsed.x).toLocaleDateString('en-US', {
                                    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
                                });
                            },
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (context.datasetIndex === 0 || context.datasetIndex === 1) {
                                    return `${label}: ${formatPace(context.parsed.y)}`;
                                } else if (context.datasetIndex === 2 || context.datasetIndex === 3) {
                                    return `${label}: ${Math.round(context.parsed.y)} bpm`;
                                } else {
                                    return `${label}: ${context.parsed.y.toFixed(2)} mi`;
                                }
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'linear',
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: {
                            color: '#94a3b8',
                            callback: function(val) {
                                return new Date(val).toLocaleDateString('en-US', {
                                    month: 'short',
                                    day: 'numeric'
                                });
                            }
                        },
                        title: {
                            display: true,
                            text: 'Date',
                            color: '#94a3b8'
                        }
                    },
                    yPace: {
                        type: 'linear',
                        display: showPaceMetric,
                        position: 'left',
                        reverse: true, // INVERT scale so faster runs are plotted higher
                        grid: {
                            color: 'rgba(255,255,255,0.05)',
                            drawOnChartArea: true // Pace is primary, it always draws grid lines if displayed
                        },
                        ticks: {
                            color: '#38bdf8',
                            callback: function(val) { return formatPace(val); }
                        },
                        title: {
                            display: true,
                            text: 'Pace (min/mi)',
                            color: '#38bdf8'
                        }
                    },
                    yDistance: {
                        type: 'linear',
                        display: showDistanceMetric,
                        position: 'left',
                        grid: {
                            color: 'rgba(255,255,255,0.05)',
                            drawOnChartArea: !showPaceMetric // draw grid if pace is hidden
                        },
                        ticks: {
                            color: '#34d399',
                            callback: function(val) { return val.toFixed(1) + ' mi'; }
                        },
                        title: {
                            display: true,
                            text: 'Distance (miles)',
                            color: '#34d399'
                        },
                        suggestedMin: 0,
                        suggestedMax: 7
                    },
                    yHr: {
                        type: 'linear',
                        display: showHrMetric,
                        position: 'right',
                        grid: {
                            color: 'rgba(255,255,255,0.05)',
                            drawOnChartArea: !showPaceMetric && !showDistanceMetric // draw grid if neither pace nor distance is displayed
                        },
                        ticks: { color: '#f87171' },
                        title: {
                            display: true,
                            text: 'Heart Rate (bpm)',
                            color: '#f87171'
                        },
                        suggestedMin: 130,
                        suggestedMax: 185
                    }
                }
            }
        });

    } else if (activeTab === 'efficiency') {
        // Aerobic Efficiency (Speed in mph / Average HR)
        const effs = runs.map(r => ({ x: new Date(r.datetime).getTime(), y: r.aerobic_efficiency || null })).filter(e => e.y !== null);
        const validEffs = effs.filter(e => e.y > 0);
        
        const effTrend = getTrendlinePoints(validEffs.map(e => e.x), validEffs.map(e => e.y));
        const effTrendData = validEffs.map((e, idx) => ({ x: e.x, y: effTrend[idx] }));

        mainChart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Aerobic Efficiency Index (Speed in mph / Heart Rate)',
                        data: effs,
                        borderColor: '#c084fc',
                        backgroundColor: 'rgba(192, 132, 252, 0.05)',
                        fill: true,
                        borderWidth: 3,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        tension: 0.15
                    },
                    {
                        label: 'Cardiovascular Efficiency Trend',
                        data: effTrendData,
                        borderColor: 'rgba(192, 132, 252, 0.4)',
                        borderWidth: 1.5,
                        borderDash: [5, 5],
                        pointRadius: 0,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: '#94a3b8', font: { family: 'Inter' } }
                    },
                    tooltip: {
                        callbacks: {
                            title: function(context) {
                                return new Date(context[0].parsed.x).toLocaleDateString('en-US', {
                                    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
                                });
                            },
                            afterBody: function() {
                                return "\nHigher index represents physiological adaptation. You run faster at lower heart rates.";
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'linear',
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: {
                            color: '#94a3b8',
                            callback: function(val) {
                                return new Date(val).toLocaleDateString('en-US', {
                                    month: 'short',
                                    day: 'numeric'
                                });
                            }
                        },
                        title: {
                            display: true,
                            text: 'Date',
                            color: '#94a3b8'
                        }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#94a3b8' },
                        title: {
                            display: true,
                            text: 'Efficiency Index (mph/bpm)',
                            color: '#c084fc'
                        }
                    }
                }
            }
        });

    } else if (activeTab === 'volume') {
        // Weekly training volume bar chart
        // Let's aggregate distance by week starting from Monday
        const weeklyData = {};
        
        runs.forEach(run => {
            const date = new Date(run.datetime);
            // Get Monday of the run week
            const day = date.getDay();
            const diff = date.getDate() - day + (day === 0 ? -6 : 1);
            const monday = new Date(date.setDate(diff));
            const mondayStr = monday.toISOString().split('T')[0];
            
            if (!weeklyData[mondayStr]) {
                weeklyData[mondayStr] = 0;
            }
            weeklyData[mondayStr] += run.distance_mi;
        });

        const weekLabels = Object.keys(weeklyData).sort();
        const weekValues = weekLabels.map(l => weeklyData[l]);
        const formattedWeekLabels = weekLabels.map(l => {
            const mon = new Date(l);
            const sun = new Date(mon);
            sun.setDate(mon.getDate() + 6);
            return `${mon.toLocaleDateString('en-US', {month: 'short', day: 'numeric'})} - ${sun.toLocaleDateString('en-US', {month: 'short', day: 'numeric'})}`;
        });

        mainChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: formattedWeekLabels,
                datasets: [{
                    label: 'Weekly Distance (miles)',
                    data: weekValues,
                    backgroundColor: 'rgba(52, 211, 153, 0.35)',
                    borderColor: '#34d399',
                    borderWidth: 2,
                    borderRadius: 8,
                    hoverBackgroundColor: '#34d399'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: '#94a3b8', font: { family: 'Inter' } }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#94a3b8' }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#94a3b8' },
                        title: {
                            display: true,
                            text: 'Distance (miles)',
                            color: '#34d399'
                        }
                    }
                }
            }
        });

    } else if (activeTab === 'form') {
        // Biomechanical Form: Cadence and Stride Length
        const cadences = runs.map(r => ({ x: new Date(r.datetime).getTime(), y: r.cadence || null })).filter(c => c.y !== null);
        const strides = runs.map(r => ({ x: new Date(r.datetime).getTime(), y: r.stride_cm || null })).filter(s => s.y !== null);

        mainChart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: [
                    {
                        label: 'Average Cadence (steps/min)',
                        data: cadences,
                        borderColor: '#fb923c',
                        backgroundColor: 'rgba(251, 146, 60, 0.05)',
                        borderWidth: 3,
                        pointRadius: 4,
                        yAxisID: 'yCadence',
                        tension: 0.15
                    },
                    {
                        label: 'Average Stride Length (cm)',
                        data: strides,
                        borderColor: '#c084fc',
                        backgroundColor: 'transparent',
                        borderWidth: 3,
                        pointRadius: 4,
                        yAxisID: 'yStride',
                        tension: 0.15
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: '#94a3b8', font: { family: 'Inter' } }
                    },
                    tooltip: {
                        callbacks: {
                            title: function(context) {
                                return new Date(context[0].parsed.x).toLocaleDateString('en-US', {
                                    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
                                });
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'linear',
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: {
                            color: '#94a3b8',
                            callback: function(val) {
                                return new Date(val).toLocaleDateString('en-US', {
                                    month: 'short',
                                    day: 'numeric'
                                });
                            }
                        },
                        title: {
                            display: true,
                            text: 'Date',
                            color: '#94a3b8'
                        }
                    },
                    yCadence: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#fb923c' },
                        title: {
                            display: true,
                            text: 'Cadence (spm)',
                            color: '#fb923c'
                        },
                        suggestedMin: 140,
                        suggestedMax: 180
                    },
                    yStride: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: { drawOnChartArea: false },
                        ticks: { color: '#c084fc' },
                        title: {
                            display: true,
                            text: 'Stride Length (cm)',
                            color: '#c084fc'
                        },
                        suggestedMin: 90,
                        suggestedMax: 130
                    }
                }
            }
        });
    } else if (activeTab === 'distPace') {
        const total = runs.length;
        const scatterData = runs.map((r, i) => {
            const pct = total > 1 ? i / (total - 1) : 0;
            const h = 270 - 75 * pct;
            return {
                x: r.distance_mi,
                y: r.pace_sec_mi,
                date: r.date,
                paceStr: r.pace_str,
                color: `hsl(${h}, 85%, 60%)`
            };
        });

        mainChart = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Runs Progression',
                    data: scatterData,
                    pointBackgroundColor: scatterData.map(d => d.color),
                    pointBorderColor: '#ffffff',
                    pointBorderWidth: 1,
                    pointRadius: 6,
                    pointHoverRadius: 8,
                    pointHoverBackgroundColor: scatterData.map(d => d.color),
                    pointHoverBorderColor: '#ffffff',
                    pointHoverBorderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const pt = context.raw;
                                return `Date: ${pt.date} | Distance: ${pt.x.toFixed(2)} mi | Pace: ${pt.paceStr} /mi`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'linear',
                        grid: { color: 'rgba(255,255,255,0.03)' },
                        ticks: { color: '#94a3b8' },
                        title: {
                            display: true,
                            text: 'Distance (miles)',
                            color: '#94a3b8'
                        }
                    },
                    y: {
                        type: 'linear',
                        reverse: true,
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: {
                            color: '#94a3b8',
                            callback: function(val) { return formatPace(val); }
                        },
                        title: {
                            display: true,
                            text: 'Pace (min/mi)',
                            color: '#94a3b8'
                        }
                    }
                }
            }
        });
    } else if (activeTab === 'progressCurves') {
        if (!progressCurvesData) {
            fetchProgressCurvesAndRender(ctx);
        } else {
            const filteredIds = new Set(runs.map(r => r.id));
            const filteredCurves = progressCurvesData.filter(c => filteredIds.has(c.id));
            renderProgressCurves(ctx, filteredCurves);
        }
    }
}

async function fetchProgressCurvesAndRender(ctx) {
    ctx.save();
    ctx.fillStyle = '#94a3b8';
    ctx.font = '16px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Loading speed comparison curves...', ctx.canvas.width / 2, ctx.canvas.height / 2);
    ctx.restore();

    try {
        const response = await fetch('/api/runs/progress-curves');
        progressCurvesData = await response.json();
        if (activeTab === 'progressCurves') {
            const runs = getFilteredRuns();
            const filteredIds = new Set(runs.map(r => r.id));
            const filteredCurves = progressCurvesData.filter(c => filteredIds.has(c.id));
            renderProgressCurves(ctx, filteredCurves);
        }
    } catch (error) {
        console.error('Error fetching progress curves:', error);
        ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
        ctx.save();
        ctx.fillStyle = '#ef4444';
        ctx.font = '16px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Error loading speed comparison curves', ctx.canvas.width / 2, ctx.canvas.height / 2);
        ctx.restore();
    }
}

function renderProgressCurves(ctx, curves) {
    if (mainChart) {
        mainChart.destroy();
    }

    if (!curves || curves.length === 0) {
        ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
        ctx.save();
        ctx.fillStyle = '#94a3b8';
        ctx.font = '16px Inter, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('No speed curves match the selected filters.', ctx.canvas.width / 2, ctx.canvas.height / 2);
        ctx.restore();
        return;
    }

    const total = curves.length;
    const datasets = curves.map((run, i) => {
        const pct = total > 1 ? i / (total - 1) : 0;
        const h = 270 - 75 * pct;
        const op = 0.15 + 0.85 * pct;
        const color = `hsla(${h}, 85%, 60%, ${op})`;

        const chartData = run.points.map(pt => ({
            x: pt.sec,
            y: pt.pace_sec,
            dist_mi: pt.dist_mi
        }));

        return {
            label: run.date,
            data: chartData,
            borderColor: color,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            fill: false,
            tension: 0.15
        };
    });

    mainChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            return context[0].dataset.label;
                        },
                        label: function(context) {
                            const pt = context.raw;
                            const timeStr = formatDuration(pt.x);
                            const paceStr = formatPace(pt.y);
                            const distStr = pt.dist_mi !== undefined ? `${pt.dist_mi.toFixed(2)} mi` : "N/A";
                            return `Time: ${timeStr} | Distance: ${distStr} | Pace: ${paceStr} /mi`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    ticks: {
                        color: '#94a3b8',
                        callback: function(val) { return formatDuration(val); }
                    },
                    title: {
                        display: true,
                        text: 'Time within Run (MM:SS)',
                        color: '#94a3b8'
                    }
                },
                y: {
                    type: 'linear',
                    reverse: true, // Invert scale so faster paces are plotted higher
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        color: '#94a3b8',
                        callback: function(val) { return formatPace(val); }
                    },
                    title: {
                        display: true,
                        text: 'Rolling Pace (min/mi)',
                        color: '#94a3b8'
                    },
                    suggestedMin: 480, // 8:00 min/mi
                    suggestedMax: 660  // 11:00 min/mi
                }
            }
        }
    });
}

// Open Run Details Overlay
async function openRunModal(runId) {
    const run = allRuns.find(r => r.id === runId);
    if (!run) return;

    // Reset overlay scroll
    const overlay = document.getElementById('run-modal');
    overlay.classList.add('active');

    // Populate metadata
    document.getElementById('modal-run-date').textContent = new Date(run.datetime).toLocaleDateString('en-US', {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
    });
    document.getElementById('modal-run-time').textContent = run.time;
    
    document.getElementById('modal-dist').textContent = `${run.distance_mi.toFixed(2)} mi`;
    document.getElementById('modal-dur').textContent = run.duration_str;
    document.getElementById('modal-pace').textContent = `${run.pace_str} /mi`;
    document.getElementById('modal-hr').textContent = run.avg_hr ? `${run.avg_hr} bpm` : 'N/A';
    document.getElementById('modal-cadence').textContent = run.cadence ? `${run.cadence} spm` : 'N/A';
    document.getElementById('modal-stride').textContent = run.stride_cm ? `${run.stride_cm} cm` : 'N/A';

    // Populate HR zones
    updateZoneStats(run.zones, run.duration_sec);

    // Initialize Map and Splits Charts concurrently
    renderSplitsChart(run.splits);
    renderHrProfileChart(run.id);
    loadGpsRoute(run.id, run.has_gps);
}

// Render zone stats progress bars in modal
function updateZoneStats(zones, totalDuration) {
    const formatZoneTime = (sec) => {
        const mins = Math.floor(sec / 60);
        const secs = sec % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const updateZoneRow = (id, sec) => {
        const durEl = document.getElementById(`dur-${id}`);
        const barEl = document.getElementById(`bar-${id}`);
        
        durEl.textContent = formatZoneTime(sec);
        if (totalDuration > 0) {
            const pct = (sec / totalDuration) * 100;
            barEl.style.width = `${pct}%`;
        } else {
            barEl.style.width = '0%';
        }
    };

    updateZoneRow('peak', zones.peak_sec || 0);
    updateZoneRow('vigorous', zones.vigorous_sec || 0);
    updateZoneRow('moderate', zones.moderate_sec || 0);
    updateZoneRow('light', zones.light_sec || 0);
}

// Render splits bar chart inside modal
function renderSplitsChart(splits) {
    if (splitsChart) {
        splitsChart.destroy();
    }

    const ctx = document.getElementById('splitsChart').getContext('2d');
    
    if (!splits || splits.length === 0) {
        ctx.clearRect(0, 0, 400, 200);
        return;
    }

    const labels = splits.map(s => `Mile ${s.split_num}`);
    const dataValues = splits.map(s => s.pace_sec_mi);

    splitsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Mile Pace (min/mi)',
                data: dataValues,
                backgroundColor: 'rgba(56, 189, 248, 0.45)',
                borderColor: '#38bdf8',
                borderWidth: 2,
                borderRadius: 6,
                hoverBackgroundColor: '#38bdf8'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `Pace: ${formatPace(context.parsed.y)} /mi`;
                        }
                    }
                }
            },
            scales: {
                x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 11 } } },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        color: '#94a3b8',
                        callback: function(val) { return formatPace(val); }
                    }
                }
            }
        }
    });
}

// Fetch and render detailed heart rate time-series profile chart inside modal
async function renderHrProfileChart(runId) {
    if (hrChart) {
        hrChart.destroy();
    }

    const ctx = document.getElementById('hrChart').getContext('2d');

    try {
        const response = await fetch(`/api/runs/${runId}/hr`);
        const hrData = await response.json();

        if (!hrData || hrData.length === 0) {
            // Write N/A inside chart canvas
            ctx.clearRect(0, 0, 400, 200);
            return;
        }

        const labels = hrData.map(h => formatDuration(h.sec));
        const bpms = hrData.map(h => h.bpm);

        hrChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Heart Rate (bpm)',
                    data: bpms,
                    borderColor: '#f87171',
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    fill: true,
                    backgroundColor: 'rgba(248, 113, 113, 0.05)',
                    tension: 0.2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#94a3b8', font: { size: 10 }, maxTicksLimit: 10 }
                    },
                    y: {
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: '#94a3b8' }
                    }
                }
            }
        });

    } catch (e) {
        console.error('Error rendering HR profile chart:', e);
    }
}

// Load GPS route and map inside modal
async function loadGpsRoute(runId, hasGps) {
    const mapDiv = document.getElementById('map');
    const placeholder = document.getElementById('map-placeholder');
    const statusBadge = document.getElementById('gps-status');

    if (!hasGps) {
        mapDiv.style.display = 'none';
        placeholder.style.display = 'flex';
        statusBadge.className = 'gps-badge disabled';
        statusBadge.innerHTML = '<i class="fa-solid fa-circle-xmark"></i> No GPS';
        return;
    }

    try {
        const response = await fetch(`/api/runs/${runId}/route`);
        const points = await response.json();

        if (!points || points.length === 0) {
            mapDiv.style.display = 'none';
            placeholder.style.display = 'flex';
            statusBadge.className = 'gps-badge disabled';
            statusBadge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> GPS Missing';
            return;
        }

        // Show map
        mapDiv.style.display = 'block';
        placeholder.style.display = 'none';
        statusBadge.className = 'gps-badge';
        statusBadge.innerHTML = '<i class="fa-solid fa-location-dot"></i> GPS Active';

        // Recreate Leaflet Map instance
        if (map) {
            map.remove();
        }

        // Center on the first coordinate
        const startPoint = [points[0].lat, points[0].lon];
        map = L.map('map', {
            zoomControl: true,
            attributionControl: false
        }).setView(startPoint, 14);

        // Load stunning CartoDB Dark Matter map tile layers
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
            maxZoom: 19
        }).addTo(map);

        // Map path polyline coordinates
        const latLons = points.map(p => [p.lat, p.lon]);
        
        // Draw the neon route line
        const polyline = L.polyline(latLons, {
            color: '#38bdf8',
            weight: 5,
            opacity: 0.9,
            lineJoin: 'round'
        }).addTo(map);

        // Fit map bounds to the polyline
        map.fitBounds(polyline.getBounds(), { padding: [20, 20] });

        // Add custom modern Start and End markers (circle markers)
        const endPoint = [points[points.length - 1].lat, points[points.length - 1].lon];
        
        L.circleMarker(startPoint, {
            radius: 6,
            fillColor: '#34d399',
            color: '#ffffff',
            weight: 2,
            opacity: 1,
            fillOpacity: 1
        }).addTo(map).bindPopup('Start Position');

        L.circleMarker(endPoint, {
            radius: 6,
            fillColor: '#f87171',
            color: '#ffffff',
            weight: 2,
            opacity: 1,
            fillOpacity: 1
        }).addTo(map).bindPopup('Finish Position');

    } catch (e) {
        console.error('Error drawing GPS Leaflet map:', e);
        mapDiv.style.display = 'none';
        placeholder.style.display = 'flex';
        statusBadge.className = 'gps-badge disabled';
        statusBadge.innerHTML = '<i class="fa-solid fa-bug"></i> Map Error';
    }
}

// Modal Listeners setup
function setupModalListeners() {
    const overlay = document.getElementById('run-modal');
    const closeBtn = document.getElementById('modal-close-btn');

    const closeModal = () => {
        overlay.classList.remove('active');
        // clean map and charts
        if (map) {
            map.remove();
            map = null;
        }
    };

    closeBtn.addEventListener('click', closeModal);
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeModal();
        }
    });
    
    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && overlay.classList.contains('active')) {
            closeModal();
        }
    });
}

// Compare View State Variables
let currentSimilarityType = 'general'; // 'general' or 'exact'
let currentSimilarityThreshold = 75; // 75%
let selectedCompareRunId = null;
let similarRunsData = [];
let comparePaceBounds = { min: 480, max: 600 };

function initCompareView() {
    const selectEl = document.getElementById('compare-run-select');
    const typeGeneral = document.getElementById('match-type-general');
    const typeExact = document.getElementById('match-type-exact');
    const thresholdSlider = document.getElementById('compare-threshold');
    const thresholdVal = document.getElementById('compare-threshold-val');
    
    if (selectEl) {
        selectEl.addEventListener('change', () => {
            selectedCompareRunId = selectEl.value;
            if (selectedCompareRunId) {
                fetchSimilarityAndRender();
            } else {
                resetCompareViewUI();
            }
        });
    }
    
    const toggleActiveType = (activeType) => {
        currentSimilarityType = activeType;
        if (activeType === 'general') {
            typeGeneral.classList.add('active');
            typeExact.classList.remove('active');
        } else {
            typeExact.classList.add('active');
            typeGeneral.classList.remove('active');
        }
        renderCompareResults();
    };
    
    if (typeGeneral) {
        typeGeneral.addEventListener('click', () => toggleActiveType('general'));
    }
    if (typeExact) {
        typeExact.addEventListener('click', () => toggleActiveType('exact'));
    }
    
    if (thresholdSlider && thresholdVal) {
        thresholdSlider.value = currentSimilarityThreshold;
        thresholdVal.textContent = `${currentSimilarityThreshold}%`;
        thresholdSlider.addEventListener('input', (e) => {
            currentSimilarityThreshold = parseInt(e.target.value);
            thresholdVal.textContent = `${currentSimilarityThreshold}%`;
            renderCompareResults();
        });
    }
    
    const compareChartTabs = document.querySelectorAll('#compare-chart-tabs .tab-btn');
    compareChartTabs.forEach(btn => {
        btn.addEventListener('click', () => {
            compareChartTabs.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            compareChartMetric = btn.getAttribute('data-compare-metric');
            renderCompareChart();
        });
    });
    
    setupViewSwitching();
}

function setupViewSwitching() {
    const menuDashboard = document.getElementById('menu-dashboard');
    const menuCompare = document.getElementById('menu-compare');
    
    const dashboardView = document.getElementById('dashboard-view');
    const compareView = document.getElementById('compare-view');
    
    if (menuDashboard && menuCompare && dashboardView && compareView) {
        menuDashboard.addEventListener('click', (e) => {
            e.preventDefault();
            menuDashboard.classList.add('active');
            menuCompare.classList.remove('active');
            dashboardView.style.display = 'block';
            compareView.style.display = 'none';
            renderMainChart();
        });
        
        menuCompare.addEventListener('click', (e) => {
            e.preventDefault();
            menuCompare.classList.add('active');
            menuDashboard.classList.remove('active');
            dashboardView.style.display = 'none';
            compareView.style.display = 'block';
            onCompareViewActive();
        });
    }
}

function onCompareViewActive() {
    const selectEl = document.getElementById('compare-run-select');
    if (!selectEl) return;
    
    const previousValue = selectEl.value;
    
    selectEl.innerHTML = '<option value="">-- Choose a Run of Interest --</option>';
    
    // Sort runs descending by date (most recent first)
    const sortedRuns = [...allRuns].sort((a, b) => new Date(b.datetime) - new Date(a.datetime));
    
    sortedRuns.forEach(run => {
        const opt = document.createElement('option');
        opt.value = run.id;
        opt.textContent = `${run.date} (${run.time}) — ${run.distance_mi.toFixed(2)} mi — ${run.pace_str}/mi`;
        selectEl.appendChild(opt);
    });
    
    if (previousValue && allRuns.some(r => r.id === previousValue)) {
        selectEl.value = previousValue;
    } else if (sortedRuns.length > 0) {
        selectEl.value = sortedRuns[0].id;
        selectedCompareRunId = sortedRuns[0].id;
        fetchSimilarityAndRender();
    }
}

async function fetchSimilarityAndRender() {
    if (!selectedCompareRunId) return;
    
    const tbody = document.getElementById('compare-runs-table-body');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center">Calculating route similarity... This may take a moment.</td></tr>`;
    }
    
    try {
        const res = await fetch(`/api/runs/${selectedCompareRunId}/compare-similarity`);
        similarRunsData = await res.json();
        renderCompareResults();
    } catch (e) {
        console.error('Error fetching similarity details:', e);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="8" class="text-center text-red">Error calculating route similarity. Make sure server is running.</td></tr>`;
        }
    }
}

function renderCompareResults() {
    if (!selectedCompareRunId || !similarRunsData || similarRunsData.length === 0) {
        resetCompareViewUI();
        return;
    }
    
    const targetRun = similarRunsData.find(r => r.id === selectedCompareRunId);
    if (!targetRun) return;
    
    // 1. Update Selected Run Stats Card
    document.getElementById('comp-sel-dist').textContent = targetRun.distance_mi.toFixed(2);
    document.getElementById('comp-sel-pace').textContent = targetRun.pace_str;
    document.getElementById('comp-sel-hr').textContent = targetRun.avg_hr ? targetRun.avg_hr : 'N/A';
    
    // 2. Filter runs according to threshold
    const thresholdDec = currentSimilarityThreshold / 100.0;
    const scoreKey = currentSimilarityType === 'general' ? 'overlap_score' : 'exact_score';
    
    let includedRuns = similarRunsData.filter(r => r[scoreKey] >= thresholdDec);
    
    // Sort includedRuns
    includedRuns.sort((a, b) => {
        let valA, valB;
        if (compareSortColumn === 'similarity') {
            valA = a[scoreKey];
            valB = b[scoreKey];
        } else {
            valA = a[compareSortColumn];
            valB = b[compareSortColumn];
        }
        
        // Handle null values
        if (valA === null || valA === undefined) return compareSortAsc ? 1 : -1;
        if (valB === null || valB === undefined) return compareSortAsc ? -1 : 1;
        
        if (compareSortColumn === 'date') {
            const valA = a.datetime || '';
            const valB = b.datetime || '';
            return compareSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        }
        
        if (typeof valA === 'string') {
            return compareSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else {
            return compareSortAsc ? valA - valB : valB - valA;
        }
    });

    updateSortIcons('compare-table', compareSortColumn, compareSortAsc);
    
    // Update badge count
    document.getElementById('compare-included-count').textContent = `${includedRuns.length} Runs Included`;
    
    // Similar runs for averaging (excluding target run to get a true comparison against the base)
    const otherSimilarRuns = includedRuns.filter(r => r.id !== selectedCompareRunId);
    const avgSourceList = otherSimilarRuns.length > 0 ? otherSimilarRuns : [targetRun];
    
    let avgStats = { dist: 0, duration: 0, paceSec: 0, hr: 0, hrCount: 0 };
    avgSourceList.forEach(r => {
        avgStats.dist += r.distance_mi;
        avgStats.duration += r.duration_sec;
        if (r.avg_hr) {
            avgStats.hr += r.avg_hr;
            avgStats.hrCount++;
        }
    });
    
    const avgDist = avgStats.dist / avgSourceList.length;
    const avgDurationSec = avgStats.duration / avgSourceList.length;
    const avgPaceSec = avgDist > 0 ? (avgDurationSec / avgDist) : 0;
    const avgHr = avgStats.hrCount > 0 ? Math.round(avgStats.hr / avgStats.hrCount) : null;
    
    const avgPaceStr = formatPace(Math.round(avgPaceSec));
    document.getElementById('comp-avg-dist').textContent = avgDist.toFixed(2);
    document.getElementById('comp-avg-pace').textContent = avgPaceStr;
    document.getElementById('comp-avg-hr').textContent = avgHr ? avgHr : 'N/A';
    
    // Calculate average splits mapped exactly to the target run's distance intervals
    const avgSplits = calculateAverageSplits(avgSourceList, targetRun);
    
    // Find the maximum distance across all runs we are comparing on the page to align splits visually
    const allCompareDistances = [targetRun.distance_mi, ...includedRuns.map(r => r.distance_mi)];
    if (avgSplits.length > 0) {
        allCompareDistances.push(avgSplits.reduce((sum, s) => sum + s.distance_mi, 0));
    }
    const maxDistance = Math.max(...allCompareDistances, 1.0);
    
    // 3. Render Heatmaps
    renderSplitsHeatmaps(targetRun, avgSplits, avgDist, avgPaceStr, maxDistance);
    
    // 4. Render Table
    renderCompareTable(includedRuns, scoreKey, maxDistance);

    // 5. Render Comparison Chart
    renderCompareChart();
}

function resetCompareViewUI() {
    if (compareChart) {
        compareChart.destroy();
        compareChart = null;
    }
    const emptyOverlay = document.getElementById('compare-chart-empty');
    if (emptyOverlay) {
        emptyOverlay.style.display = 'flex';
        emptyOverlay.textContent = 'Select a run of interest above to plot similarity trends.';
    }
    document.getElementById('comp-sel-dist').textContent = '--';
    document.getElementById('comp-sel-pace').textContent = '--';
    document.getElementById('comp-sel-hr').textContent = '--';
    document.getElementById('comp-avg-dist').textContent = '--';
    document.getElementById('comp-avg-pace').textContent = '--';
    document.getElementById('comp-avg-hr').textContent = '--';
    document.getElementById('compare-included-count').textContent = '-- Similar Runs';
    document.getElementById('vector-title-selected-desc').textContent = '--';
    document.getElementById('vector-title-average-desc').textContent = '--';
    
    document.getElementById('vector-bar-selected').innerHTML = '<div class="vector-empty-message">Select a run above to view splits heatmap.</div>';
    document.getElementById('vector-bar-average').innerHTML = '<div class="vector-empty-message">Select a run above to view splits heatmap.</div>';
    
    const tbody = document.getElementById('compare-runs-table-body');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center">Select a run of interest to find similar runs.</td></tr>`;
    }
}

function calculateAverageSplits(runs, targetRun) {
    if (!targetRun || !targetRun.splits) return [];
    
    const avgSplits = [];
    targetRun.splits.forEach(tSplit => {
        const num = tSplit.split_num;
        let sumPace = 0;
        let count = 0;
        
        runs.forEach(run => {
            if (run.splits) {
                const rSplit = run.splits.find(s => s.split_num === num);
                if (rSplit) {
                    sumPace += rSplit.pace_sec_mi;
                    count++;
                }
            }
        });
        
        // Fallback to target run's own pace if no compared run reached this split
        const avgPaceSec = count > 0 ? Math.round(sumPace / count) : tSplit.pace_sec_mi;
        
        avgSplits.push({
            split_num: num,
            distance_mi: tSplit.distance_mi, // Match target run distance exactly for perfect visual alignment
            pace_sec_mi: avgPaceSec,
            pace_str: formatPace(avgPaceSec)
        });
    });
    return avgSplits;
}

function getPaceColor(paceSec, minPace, maxPace) {
    if (!paceSec || isNaN(paceSec)) return 'rgba(255,255,255,0.05)';
    if (minPace === maxPace) return 'hsl(30, 85%, 50%)';
    
    const p = Math.max(minPace, Math.min(maxPace, paceSec));
    // ratio = 0 (fastest/minPace) to 1 (slowest/maxPace)
    const ratio = (p - minPace) / (maxPace - minPace);
    
    // Warm colors (orange-red) = fast, Cool colors (cyan-blue) = slow.
    // Interpolating HSL hue from 15 (warm fast) to 205 (cool slow)
    const hue = 15 + ratio * 190;
    return `hsl(${hue}, 85%, 50%)`;
}

function createVectorBarHtml(splits, minPace, maxPace, maxDistance) {
    if (!splits || splits.length === 0) {
        return '<div class="vector-empty-message">No split data.</div>';
    }
    
    let html = '';
    
    splits.forEach(split => {
        const pctWidth = (split.distance_mi / maxDistance) * 100;
        const color = getPaceColor(split.pace_sec_mi, minPace, maxPace);
        
        let label = `M${split.split_num}`;
        if (pctWidth > 12) {
            label = `Mile ${split.split_num}: ${split.pace_str}`;
        } else if (pctWidth > 6) {
            label = `M${split.split_num}: ${split.pace_str}`;
        }
        
        html += `
            <div class="vector-segment" style="width: ${pctWidth}%; flex-shrink: 0; background-color: ${color};">
                <span>${label}</span>
                <div class="vector-segment-tooltip">
                    <strong>Mile ${split.split_num}</strong><br>
                    Distance: ${split.distance_mi.toFixed(2)} mi<br>
                    Pace: ${split.pace_str} /mi
                </div>
            </div>
        `;
    });
    
    return html;
}

function createMiniVectorBarHtml(splits, minPace, maxPace, maxDistance) {
    if (!splits || splits.length === 0) {
        return '<div style="color: var(--text-muted); font-size: 11px;">No split data</div>';
    }
    
    let html = '<div class="mini-vector-bar">';
    
    splits.forEach(split => {
        const pctWidth = (split.distance_mi / maxDistance) * 100;
        const color = getPaceColor(split.pace_sec_mi, minPace, maxPace);
        
        html += `
            <div class="mini-segment" style="width: ${pctWidth}%; flex-shrink: 0; background-color: ${color};">
                <div class="vector-segment-tooltip">
                    <strong>Mile ${split.split_num}</strong><br>
                    Distance: ${split.distance_mi.toFixed(2)} mi<br>
                    Pace: ${split.pace_str} /mi
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    return html;
}

function renderSplitsHeatmaps(targetRun, avgSplits, avgDist, avgPaceStr, maxDistance) {
    document.getElementById('vector-title-selected-desc').textContent = `${targetRun.distance_mi.toFixed(2)} mi | Avg Pace: ${targetRun.pace_str}/mi`;
    
    document.getElementById('vector-title-average-desc').textContent = `${avgDist.toFixed(2)} mi | Avg Pace: ${avgPaceStr}/mi`;
    
    document.getElementById('vector-bar-selected').innerHTML = createVectorBarHtml(targetRun.splits, globalPaceBounds.min, globalPaceBounds.max, maxDistance);
    document.getElementById('vector-bar-average').innerHTML = createVectorBarHtml(avgSplits, globalPaceBounds.min, globalPaceBounds.max, maxDistance);
}

function renderCompareTable(includedRuns, scoreKey, maxDistance) {
    const tbody = document.getElementById('compare-runs-table-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (includedRuns.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center">No runs match the selected similarity criteria.</td></tr>`;
        return;
    }
    
    includedRuns.forEach(run => {
        const tr = document.createElement('tr');
        if (run.id === selectedCompareRunId) {
            tr.classList.add('selected-run-row');
        }
        
        const pct = run[scoreKey] * 100;
        let badgeClass = '';
        if (pct >= 90) {
            badgeClass = 'high';
        } else if (pct >= 75) {
            badgeClass = 'medium';
        }
        
        const simText = run.id === selectedCompareRunId ? 'Selected' : `${pct.toFixed(0)}%`;
        const similarityHtml = run.id === selectedCompareRunId 
            ? `<span class="similarity-badge high"><i class="fa-solid fa-star"></i> Selected</span>`
            : `<span class="similarity-badge ${badgeClass}">${simText}</span>`;
        
        const miniVectorHtml = createMiniVectorBarHtml(run.splits, globalPaceBounds.min, globalPaceBounds.max, maxDistance);
        
        tr.innerHTML = `
            <td><strong>${run.date}</strong> <span class="modal-run-time">${run.time}</span></td>
            <td>${run.distance_mi.toFixed(2)} mi</td>
            <td>${run.duration_str}</td>
            <td><i class="fa-solid fa-gauge-high" style="color: var(--color-primary); font-size: 12px; margin-right: 4px;"></i> ${run.pace_str}</td>
            <td>${run.avg_hr ? `<i class="fa-solid fa-heartbeat" style="color: var(--color-red); font-size: 12px; margin-right: 4px;"></i> ${run.avg_hr} bpm` : 'N/A'}</td>
            <td>${similarityHtml}</td>
            <td>${miniVectorHtml}</td>
            <td class="text-right">
                <button class="action-btn">
                    <i class="fa-solid fa-circle-info"></i> View Details
                </button>
            </td>
        `;
        
        tr.addEventListener('click', (e) => {
            if (e.target.closest('.mini-vector-bar') || e.target.closest('.action-btn')) {
                return;
            }
            openRunModal(run.id);
        });
        
        const btn = tr.querySelector('.action-btn');
        if (btn) {
            btn.addEventListener('click', () => openRunModal(run.id));
        }
        
        tbody.appendChild(tr);
    });
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', initDashboard);


function getIncludedCompareRuns() {
    if (!selectedCompareRunId || !similarRunsData || similarRunsData.length === 0) return [];
    const thresholdDec = currentSimilarityThreshold / 100.0;
    const scoreKey = currentSimilarityType === 'general' ? 'overlap_score' : 'exact_score';
    return similarRunsData.filter(r => r[scoreKey] >= thresholdDec);
}

function renderCompareChart() {
    if (compareChart) {
        compareChart.destroy();
        compareChart = null;
    }

    const canvas = document.getElementById('compareChartCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const emptyOverlay = document.getElementById('compare-chart-empty');
    
    const includedRuns = getIncludedCompareRuns();
    
    if (includedRuns.length === 0) {
        if (emptyOverlay) emptyOverlay.style.display = 'flex';
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
    }
    
    if (emptyOverlay) emptyOverlay.style.display = 'none';
    
    // Sort included runs chronologically ascending so time flows left-to-right
    const chartRuns = [...includedRuns].sort((a, b) => (a.datetime || '').localeCompare(b.datetime || ''));
    
    // Prepare data points based on metric
    const dataPoints = [];
    chartRuns.forEach(run => {
        let val = null;
        if (compareChartMetric === 'distance_mi') {
            val = run.distance_mi;
        } else if (compareChartMetric === 'duration_sec') {
            val = run.duration_sec;
        } else if (compareChartMetric === 'pace_sec_mi') {
            val = run.pace_sec_mi;
        } else if (compareChartMetric === 'avg_hr') {
            val = run.avg_hr;
        }
        
        if (val !== null && val !== undefined && !isNaN(val)) {
            dataPoints.push({
                x: new Date(run.datetime).getTime(),
                y: val,
                runId: run.id,
                dateStr: run.date,
                timeStr: run.time
            });
        }
    });

    if (dataPoints.length === 0) {
        if (emptyOverlay) {
            emptyOverlay.style.display = 'flex';
            emptyOverlay.textContent = 'No matching data points for this metric.';
        }
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
    }
    
    // Define point properties to highlight target run
    const pointBackgroundColor = dataPoints.map(dp => dp.runId === selectedCompareRunId ? '#ef4444' : '#38bdf8');
    const pointBorderColor = dataPoints.map(dp => dp.runId === selectedCompareRunId ? '#ffffff' : '#38bdf8');
    const pointRadius = dataPoints.map(dp => dp.runId === selectedCompareRunId ? 8 : 4);
    const pointHoverRadius = dataPoints.map(dp => dp.runId === selectedCompareRunId ? 10 : 6);
    const pointBorderWidth = dataPoints.map(dp => dp.runId === selectedCompareRunId ? 2 : 1);
    
    let yLabel = '';
    let yReverse = false;
    let yCallback = val => val;
    
    if (compareChartMetric === 'distance_mi') {
        yLabel = 'Distance (miles)';
        yCallback = val => val.toFixed(2) + ' mi';
    } else if (compareChartMetric === 'duration_sec') {
        yLabel = 'Duration (min)';
        yCallback = val => formatDuration(val);
    } else if (compareChartMetric === 'pace_sec_mi') {
        yLabel = 'Average Pace (min/mi)';
        yCallback = val => formatPace(val);
        yReverse = true;
    } else if (compareChartMetric === 'avg_hr') {
        yLabel = 'Average Heart Rate (bpm)';
        yCallback = val => val + ' bpm';
    }
    
    compareChart = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: [{
                label: yLabel,
                data: dataPoints,
                borderColor: 'rgba(56, 189, 248, 0.4)',
                backgroundColor: 'rgba(56, 189, 248, 0.05)',
                borderWidth: 2,
                tension: 0.15,
                fill: true,
                pointBackgroundColor: pointBackgroundColor,
                pointBorderColor: pointBorderColor,
                pointRadius: pointRadius,
                pointHoverRadius: pointHoverRadius,
                pointBorderWidth: pointBorderWidth
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: function(context) {
                            const dp = context[0].raw;
                            return `${dp.dateStr} at ${dp.timeStr}` + (dp.runId === selectedCompareRunId ? ' (Selected Run)' : '');
                        },
                        label: function(context) {
                            const dp = context.raw;
                            return `${yLabel}: ${yCallback(dp.y)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    ticks: {
                        color: '#94a3b8',
                        callback: function(val) {
                            return new Date(val).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                                year: '2-digit'
                            });
                        }
                    },
                    title: {
                        display: true,
                        text: 'Date',
                        color: '#94a3b8'
                    }
                },
                y: {
                    type: 'linear',
                    reverse: yReverse,
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: {
                        color: '#94a3b8',
                        callback: yCallback
                    },
                    title: {
                        display: true,
                        text: yLabel,
                        color: '#94a3b8'
                    }
                }
            }
        }
    });
}

