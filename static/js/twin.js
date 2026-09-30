(() => {
  const canvas = document.getElementById('twin-chart');
  const dataNode = document.getElementById('twin-chart-data');
  if (canvas && dataNode) {
    const data = JSON.parse(dataNode.textContent);
    if (typeof Chart === 'undefined') {
      canvas.parentElement.hidden = true;
      document.getElementById('twin-chart-fallback').hidden = false;
    } else {
      new Chart(canvas, {
        type: 'bar',
        data: {labels: data.labels, datasets: [
          {label: 'Actual marks', data: data.actual, backgroundColor: '#547ce8', borderRadius: 5, maxBarThickness: 22},
          {label: 'Simulated marks', data: data.simulated, backgroundColor: '#9360e8', borderRadius: 5, maxBarThickness: 22}
        ]},
        options: {
          responsive: true, maintainAspectRatio: false,
          animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : {duration: 500},
          plugins: {legend: {display: false}, tooltip: {backgroundColor: '#17243e', padding: 12, cornerRadius: 8}},
          scales: {y: {min: 0, max: 100, ticks: {stepSize: 20, color: '#8b95a7'}, grid: {color: '#f0f3f8'}, border: {display: false}}, x: {ticks: {color: '#8290a6', font: {size: 10}}, grid: {display: false}, border: {display: false}}}
        }
      });
    }
  }
  document.querySelectorAll('.mark-input').forEach(input => input.addEventListener('input', () => {
    document.getElementById('scenario-status').textContent = 'Unsaved scenario changes — run simulation to update the comparison.';
  }));
})();
