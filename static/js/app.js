(function () {
    'use strict';

    // Shared dialogs keep keyboard focus inside the active form.
    let activeModal = null;
    let previousFocus = null;
    const focusable = 'button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), a[href], [tabindex="0"]';
    function closeModal() {
        if (!activeModal) return;
        activeModal.classList.remove('show');
        activeModal.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = '';
        activeModal = null;
        if (previousFocus) previousFocus.focus();
    }
    function openModal(id) {
        const modal = document.getElementById(id);
        if (!modal) return;
        previousFocus = document.activeElement;
        activeModal = modal;
        modal.classList.add('show');
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        const field = modal.querySelector('input:not([type="hidden"]), select, button');
        if (field) field.focus();
    }
    document.querySelectorAll('[data-open-modal]').forEach(button => {
        button.addEventListener('click', () => openModal(button.dataset.openModal));
    });
    document.querySelectorAll('[data-close-modal]').forEach(button => button.addEventListener('click', closeModal));
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', event => { if (event.target === modal) closeModal(); });
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            closeModal();
            document.body.classList.remove('sidebar-open');
            document.querySelectorAll('[data-toggle-sidebar]').forEach(button => button.setAttribute('aria-expanded', 'false'));
        }
        if (event.key !== 'Tab' || !activeModal) return;
        const controls = Array.from(activeModal.querySelectorAll(focusable)).filter(el => !el.hidden && el.offsetParent !== null);
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    document.querySelectorAll('[data-toggle-sidebar]').forEach(button => {
        button.addEventListener('click', () => {
            const open = document.body.classList.toggle('sidebar-open');
            document.querySelectorAll('[data-toggle-sidebar]').forEach(toggle => toggle.setAttribute('aria-expanded', String(open)));
        });
    });
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', event => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); });
    });

    // Cohort filters refresh both metrics and charts from the database.
    document.querySelectorAll('[data-reset-section]').forEach(select => {
        select.addEventListener('change', () => {
            const section = select.form.querySelector('[name="section_id"]');
            if (section) section.value = '';
            select.form.requestSubmit();
        });
    });
    document.querySelectorAll('[data-auto-submit]').forEach(select => {
        select.addEventListener('change', () => select.form.requestSubmit());
    });
    const courseFilter = document.getElementById('courseFilter');
    if (courseFilter) courseFilter.addEventListener('change', () => {
        ['branch_id', 'section_id'].forEach(name => {
            const field = courseFilter.form.querySelector('[name="' + name + '"]');
            if (field) field.value = '';
        });
        courseFilter.form.requestSubmit();
    });
    const semesterFilter = document.getElementById('semesterFilter');
    if (semesterFilter) semesterFilter.addEventListener('change', () => {
        const section = semesterFilter.form.querySelector('[name="section_id"]');
        if (section) section.value = '';
        semesterFilter.form.requestSubmit();
    });

    const search = document.getElementById('studentSearch');
    if (search) {
        const rows = Array.from(document.querySelectorAll('.student-row'));
        const empty = document.getElementById('searchEmpty');
        const count = document.getElementById('visibleRecordCount');
        function filterRecords() {
            const query = search.value.trim().toLowerCase();
            let visible = 0;
            rows.forEach(row => {
                const matches = (row.dataset.search || '').includes(query);
                row.hidden = !matches;
                if (matches) visible += 1;
            });
            if (empty) empty.hidden = visible !== 0;
            if (count) count.textContent = String(visible);
        }
        search.addEventListener('input', filterRecords);
        filterRecords();
    }

    const newCourse = document.getElementById('newCourse');
    const newBranch = document.getElementById('newBranch');
    const newSemester = document.getElementById('newSemester');
    const newSection = document.getElementById('newSection');
    const registrationData = document.getElementById('registrationData');
    if (newCourse && newBranch && newSemester && newSection && registrationData) {
        const sections = JSON.parse(registrationData.textContent);
        const allSemesters = [...new Set(sections.map(section => String(section.semester)))].sort((a, b) => Number(a) - Number(b));
        const allSectionNames = [...new Set(sections.map(section => section.name))].sort();
        const submit = document.getElementById('registrationSubmit');
        const hint = document.getElementById('registrationHint');

        function updateChoices(select, values, available, prefix, emptyLabel) {
            const previous = select.value;
            select.replaceChildren();
            if (!available.length) {
                const empty = new Option(emptyLabel, '', true, true);
                empty.disabled = true;
                select.add(empty);
                return;
            }
            values.forEach(value => {
                const option = new Option(prefix + value, value);
                option.disabled = !available.includes(value);
                select.add(option);
            });
            select.value = available.includes(previous) ? previous : available[0];
        }

        function matchSections() {
            const branchSections = sections.filter(section => String(section.branch_id) === newBranch.value);
            const semesters = [...new Set(branchSections.map(section => String(section.semester)))].sort((a, b) => Number(a) - Number(b));
            updateChoices(newSemester, allSemesters, semesters, 'Semester ', 'No configured semesters');
            const names = [...new Set(branchSections.filter(section => String(section.semester) === newSemester.value).map(section => section.name))].sort();
            updateChoices(newSection, allSectionNames, names, 'Section ', 'No configured sections');
            const valid = Boolean(newBranch.value && newSemester.value && newSection.value);
            if (submit) submit.disabled = !valid;
            if (hint) {
                hint.hidden = valid;
                hint.textContent = valid ? '' : 'No sections are configured for this selection. Choose another course or branch.';
            }
        }

        function matchBranches() {
            let firstMatch = null;
            Array.from(newBranch.options).forEach(option => {
                const matches = option.dataset.courseId === newCourse.value;
                option.hidden = !matches;
                option.disabled = !matches;
                if (matches && !firstMatch) firstMatch = option;
            });
            if (!newBranch.selectedOptions.length || newBranch.selectedOptions[0].disabled) newBranch.value = firstMatch ? firstMatch.value : '';
            matchSections();
        }
        newCourse.addEventListener('change', matchBranches);
        newBranch.addEventListener('change', matchSections);
        newSemester.addEventListener('change', matchSections);
        matchBranches();
    }

    // Chart payloads are serialized by Flask from the current SQLite selection.
    const dashboardElement = document.getElementById('dashboardChartData');
    const analyticsElement = document.getElementById('analyticsChartData');
    if (!dashboardElement && !analyticsElement) return;
    if (typeof window.Chart === 'undefined') {
        document.querySelectorAll('[data-chart-fallback]').forEach(el => { el.hidden = false; });
        document.querySelectorAll('.chart-wrap, .doughnut-center').forEach(el => { el.hidden = true; });
        return;
    }
    Chart.defaults.font.family = 'Segoe UI, Inter, Arial, sans-serif';
    Chart.defaults.font.size = 10;
    Chart.defaults.color = '#8b97ad';
    Chart.defaults.borderColor = '#edf1f7';
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const tooltip = {backgroundColor: '#1d2a44', padding: 11, cornerRadius: 8, titleFont: {size: 11}, bodyFont: {size: 11}, displayColors: false};
    function barChart(id, labels, values, settings) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        const horizontal = Boolean(settings.horizontal);
        const axes = {
            x: {grid: {display: horizontal, drawTicks: false}, border: {display: false}, ticks: {padding: 10, maxRotation: 0, autoSkip: false}},
            y: {grid: {display: !horizontal, drawTicks: false}, border: {display: false}, ticks: {padding: 10}}
        };
        const valueAxis = horizontal ? axes.x : axes.y;
        valueAxis.beginAtZero = true;
        if (settings.max) valueAxis.max = settings.max;
        valueAxis.ticks.precision = settings.integer ? 0 : 1;
        if (settings.step) valueAxis.ticks.stepSize = settings.step;
        const config = {
            type: 'bar',
            data: {labels: labels, datasets: [{label: settings.label, data: values, backgroundColor: settings.colors || '#7e8ce5', borderRadius: 5, maxBarThickness: horizontal ? 19 : 35, categoryPercentage: 0.65}]},
            options: {responsive: true, maintainAspectRatio: false, animation: reducedMotion ? false : {duration: 450}, indexAxis: horizontal ? 'y' : 'x', plugins: {legend: {display: false}, tooltip: Object.assign({}, tooltip, settings.tooltip || {})}, scales: axes}
        };
        return new Chart(canvas, config);
    }
    function doughnutChart(id, data) {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        return new Chart(canvas, {
            type: 'doughnut',
            data: {labels: data.labels, datasets: [{data: data.values, backgroundColor: ['#23aa89', '#e58391'], borderWidth: 5, borderColor: '#fff', borderRadius: 4, hoverOffset: 4}]},
            options: {responsive: true, maintainAspectRatio: false, cutout: '78%', animation: reducedMotion ? false : {duration: 500}, plugins: {legend: {display: false}, tooltip: Object.assign({}, tooltip, {displayColors: true})}}
        });
    }
    if (dashboardElement) {
        const data = JSON.parse(dashboardElement.textContent);
        function shortBranchName(name) {
            if (/artificial intelligence|AI\s*(?:&|and)\s*ML/i.test(name)) return 'CSE (AI & ML)';
            if (/electronics.*communication|\bECE\b/i.test(name)) return 'ECE';
            if (/computer science|\bCSE\b/i.test(name)) return 'CSE';
            return name.length > 14 ? name.slice(0, 13) + '…' : name;
        }
        barChart('branchChart', data.branch.labels.map(shortBranchName), data.branch.values, {
            label: 'Average SGPA', max: 10, step: 2, colors: ['#6276de', '#8b85df', '#79a6e4', '#9c91de'],
            tooltip: {callbacks: {title: items => data.branch.labels[items[0].dataIndex]}}
        });
        doughnutChart('resultChart', data.result);
        barChart('sgpaChart', ['<5', '5–6', '6–7', '7–8', '8–9', '9–10'], data.sgpa.values, {label: 'Students', integer: true, colors: ['#e5a6af', '#e2bd76', '#aaa5e4', '#8c95e4', '#7184df', '#586cd2'], tooltip: {callbacks: {title: items => data.sgpa.labels[items[0].dataIndex] + ' SGPA'}}});
    }
    if (analyticsElement) {
        const data = JSON.parse(analyticsElement.textContent);
        const subjects = data.subjects || [];
        barChart('subjectChart', subjects.map(subject => subject.subject_name.length > 24 ? subject.subject_name.slice(0, 23) + '…' : subject.subject_name), subjects.map(subject => subject.average_marks), {
            label: 'Average marks', max: 100, step: 20, horizontal: true,
            colors: subjects.map(subject => subject.average_marks < 40 ? '#df9ca9' : '#7d8bdd'),
            tooltip: {callbacks: {
                title: items => subjects[items[0].dataIndex].subject_name,
                label: item => 'Average: ' + Number(item.raw).toFixed(1) + ' / 100',
                afterLabel: item => {
                    const subject = subjects[item.dataIndex];
                    const lines = [];
                    if (subject.highest_marks != null) lines.push('Highest: ' + subject.highest_marks);
                    if (subject.lowest_marks != null) lines.push('Lowest: ' + subject.lowest_marks);
                    return lines;
                }
            }}
        });
        doughnutChart('analyticsResultChart', data.result);
    }
})();
