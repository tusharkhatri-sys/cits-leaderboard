const API_URL = "https://cits-backend-aek9.onrender.com/api";
let currentPassword = "";

document.getElementById('loginBtn').addEventListener('click', () => {
    currentPassword = document.getElementById('passwordInput').value;
    if(currentPassword) {
        fetchAdminData();
    }
});

async function fetchAdminData() {
    try {
        const response = await fetch(`${API_URL}/leaderboard`);
        const data = await response.json();
        
        document.getElementById('loginSection').style.display = 'none';
        document.getElementById('dashboardSection').style.display = 'block';
        
        renderAdminTable(data.data);
    } catch (err) {
        alert("Failed to load data.");
    }
}

function renderAdminTable(entries) {
    const tbody = document.getElementById('adminTableBody');
    tbody.innerHTML = '';
    
    entries.forEach(entry => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${entry.student_name}</td>
            <td>${entry.trade_name}</td>
            <td>${entry.marks}</td>
            <td><button class="delete-btn" onclick="deleteEntry('${entry.id}')">Delete</button></td>
        `;
        tbody.appendChild(tr);
    });
}

window.deleteEntry = async function(id) {
    if(!confirm("Are you sure you want to delete this entry?")) return;
    
    try {
        const response = await fetch(`${API_URL}/admin/leaderboard/${id}`, {
            method: 'DELETE',
            headers: {
                'X-Admin-Key': currentPassword
            }
        });
        
        if(response.status === 401) {
            alert("Incorrect Admin Password!");
            document.getElementById('loginSection').style.display = 'block';
            document.getElementById('dashboardSection').style.display = 'none';
            document.getElementById('loginError').style.display = 'block';
            return;
        }
        
        if(response.ok) {
            alert("Entry deleted successfully!");
            fetchAdminData(); // Refresh
        } else {
            const data = await response.json();
            alert("Error: " + data.detail);
        }
    } catch (err) {
        alert("Network error: " + err);
    }
};
