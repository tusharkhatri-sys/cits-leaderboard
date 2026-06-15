const API_BASE_URL = 'http://127.0.0.1:8000/api';

const uploadForm = document.getElementById('uploadForm');
const fileInput = document.getElementById('resultFile');
const fileMsg = document.querySelector('.file-msg');
const uploadBtn = document.getElementById('uploadBtn');
const statusMsg = document.getElementById('uploadStatus');
const leaderboardBody = document.getElementById('leaderboardBody');
const loadingLeaderboard = document.getElementById('loadingLeaderboard');
const tradeFilter = document.getElementById('tradeFilter');

let allLeaderboardData = [];

fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        fileMsg.textContent = fileInput.files[0].name;
    } else {
        fileMsg.textContent = 'Drag & Drop or Click to Upload Screenshot';
    }
});

uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (fileInput.files.length === 0) return;

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Extracting Data...';
    statusMsg.textContent = '';
    statusMsg.className = 'status-msg';

    try {
        const response = await fetch(`${API_BASE_URL}/upload-result`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Upload failed');
        }

        statusMsg.textContent = `Success! Added ${data.data.student_name} (${data.data.marks} Marks)`;
        statusMsg.classList.add('success');
        
        // Reset form
        uploadForm.reset();
        fileMsg.textContent = 'Drag & Drop or Click to Upload Screenshot';
        
        // Refresh Leaderboard
        fetchLeaderboard();
        
    } catch (error) {
        statusMsg.textContent = `Error: ${error.message}`;
        statusMsg.classList.add('error');
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = 'Extract & Upload';
    }
});

async function fetchLeaderboard() {
    try {
        const response = await fetch(`${API_BASE_URL}/leaderboard`);
        if (!response.ok) throw new Error('Failed to fetch leaderboard');
        
        const data = await response.json();
        allLeaderboardData = data.data;
        populateTradeFilter(allLeaderboardData);
        applyFilter();
    } catch (error) {
        console.error(error);
        loadingLeaderboard.textContent = 'Failed to load rankings.';
    }
}

function populateTradeFilter(data) {
    const currentSelection = tradeFilter.value;
    const uniqueTrades = [...new Set(data.map(item => item.trade_name))].sort();
    
    tradeFilter.innerHTML = '<option value="all">All Trades</option>';
    uniqueTrades.forEach(trade => {
        const option = document.createElement('option');
        option.value = trade;
        option.textContent = trade;
        tradeFilter.appendChild(option);
    });
    
    if (uniqueTrades.includes(currentSelection)) {
        tradeFilter.value = currentSelection;
    }
}

function applyFilter() {
    const selectedTrade = tradeFilter.value;
    let filteredData = allLeaderboardData;
    
    if (selectedTrade !== 'all') {
        filteredData = allLeaderboardData.filter(item => item.trade_name === selectedTrade);
    }
    
    filteredData.sort((a, b) => b.marks - a.marks);
    renderLeaderboard(filteredData);
}

tradeFilter.addEventListener('change', applyFilter);

function renderLeaderboard(data) {
    leaderboardBody.innerHTML = '';
    loadingLeaderboard.style.display = 'none';

    if (data.length === 0) {
        leaderboardBody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #666;">No results uploaded yet. Be the first!</td></tr>';
        return;
    }

    data.forEach((student, index) => {
        const rank = index + 1;
        let rankClass = 'rank-badge';
        if (rank === 1) rankClass += ' rank-1';
        else if (rank === 2) rankClass += ' rank-2';
        else if (rank === 3) rankClass += ' rank-3';

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><span class="${rankClass}">${rank}</span></td>
            <td style="font-weight: 500;">${student.student_name}</td>
            <td>${student.trade_name}</td>
            <td style="font-weight: bold; color: var(--primary-blue);">${student.marks}</td>
        `;
        leaderboardBody.appendChild(row);
    });
}

// Initial fetch
fetchLeaderboard();
