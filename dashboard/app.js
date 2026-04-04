/**
 * BIST 100 Borsa Robotu — Dashboard JavaScript
 */

const API = '';

// ===== CLOCK =====
function updateClock() {
    const now = new Date();
    const el = document.getElementById('clock');
    if (el) {
        el.textContent = now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
}
setInterval(updateClock, 1000);
updateClock();

// ===== API HELPERS =====
async function apiGet(path) {
    try {
        const res = await fetch(API + path);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
    } catch (e) {
        console.error(`API error (${path}):`, e);
        return null;
    }
}

async function apiPost(path, data) {
    try {
        const res = await fetch(API + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        return await res.json();
    } catch (e) {
        console.error(`API POST error (${path}):`, e);
        return null;
    }
}

// ===== PORTFOLIO =====
async function loadPortfolio() {
    const data = await apiGet('/api/portfolio');
    const container = document.getElementById('portfolio-list');
    const valueEl = document.getElementById('portfolio-value');
    const profitEl = document.getElementById('total-profit');
    const profitPctEl = document.getElementById('profit-pct');
    const changeEl = document.getElementById('portfolio-change');

    if (!data || !data.holdings || data.holdings.length === 0) {
        container.innerHTML = '<div class="empty-state">Portföyünüz boş. "Ekle" butonuyla hisse ekleyin.</div>';
        valueEl.textContent = '0 TL';
        profitEl.textContent = '0 TL';
        return;
    }

    // Stats
    valueEl.textContent = `${data.total_value.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL`;
    profitEl.textContent = `${data.total_profit_loss >= 0 ? '+' : ''}${data.total_profit_loss.toLocaleString('tr-TR', { minimumFractionDigits: 2 })} TL`;
    profitEl.style.color = data.total_profit_loss >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
    
    profitPctEl.textContent = `${data.total_profit_pct >= 0 ? '+' : ''}${data.total_profit_pct.toFixed(1)}%`;
    profitPctEl.className = `stat-change ${data.total_profit_pct >= 0 ? 'positive' : 'negative'}`;
    
    changeEl.textContent = `${data.holdings.length} hisse`;

    // Holdings
    container.innerHTML = data.holdings.map(h => `
        <div class="portfolio-item" onclick="analyzeStockDirect('${h.symbol}')">
            <div>
                <div class="stock-name">${h.symbol} ${h.emoji}</div>
                <div class="stock-qty">${h.quantity} adet @ ${h.avg_buy_price.toFixed(2)} TL</div>
            </div>
            <div>
                <div class="stock-profit ${h.profit_loss >= 0 ? 'positive' : 'negative'}">
                    ${h.profit_loss >= 0 ? '+' : ''}${h.profit_loss.toFixed(2)} TL
                </div>
                <div class="stock-pct ${h.profit_pct >= 0 ? 'positive' : 'negative'}">
                    ${h.profit_pct >= 0 ? '+' : ''}${h.profit_pct.toFixed(1)}%
                </div>
            </div>
        </div>
    `).join('');
}

// ===== SIGNALS =====
async function loadSignals() {
    const data = await apiGet('/api/signals');
    const tbody = document.getElementById('signals-body');
    const countEl = document.getElementById('active-signals');

    if (!data || !data.signals || data.signals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Henüz sinyal yok</td></tr>';
        countEl.textContent = '0';
        return;
    }

    // Count today's signals
    const today = new Date().toISOString().slice(0, 10);
    const todaySignals = data.signals.filter(s => s.date && s.date.startsWith(today));
    countEl.textContent = todaySignals.length;

    tbody.innerHTML = data.signals.slice(0, 20).map(s => {
        let signalClass = 'signal-hold';
        if (s.signal_type.includes('AL')) signalClass = 'signal-buy';
        else if (s.signal_type.includes('SAT')) signalClass = 'signal-sell';
        else if (s.signal_type === 'ENGEL') signalClass = 'signal-blocked';

        const badgeClass = signalClass.replace('signal-', '');
        return `
            <tr onclick="analyzeStockDirect('${s.symbol}')" style="cursor:pointer">
                <td>${s.date ? s.date.slice(0, 16).replace('T', ' ') : '—'}</td>
                <td><strong>${s.symbol}</strong></td>
                <td><span class="signal-badge ${signalClass}">${s.signal_type}</span></td>
                <td>${s.score.toFixed(1)}</td>
                <td>${(s.technical_score || 0).toFixed(0)}</td>
                <td>${(s.news_score || 0).toFixed(0)}</td>
                <td>${(s.ml_score || 0).toFixed(0)}</td>
                <td>${s.price_at_signal ? s.price_at_signal.toFixed(2) + ' TL' : '—'}</td>
            </tr>
        `;
    }).join('');
}

// ===== ANALYZE =====
function analyzeStockDirect(symbol) {
    document.getElementById('analyze-input').value = symbol;
    analyzeStock();
}

async function analyzeStock() {
    const input = document.getElementById('analyze-input');
    const btn = document.getElementById('analyze-btn');
    const resultDiv = document.getElementById('analyze-result');
    const symbol = input.value.trim().toUpperCase();

    if (!symbol) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> Analiz ediliyor...';
    resultDiv.className = 'analyze-result active';
    resultDiv.innerHTML = '<div class="empty-state"><span class="loading"></span> 4 katmanlı analiz yapılıyor...</div>';

    const data = await apiGet(`/api/analyze/${symbol}`);

    btn.disabled = false;
    btn.innerHTML = 'Analiz Et';

    if (!data) {
        resultDiv.innerHTML = '<div class="empty-state">❌ Analiz başarısız. API bağlantısını kontrol edin.</div>';
        return;
    }

    const signal = data.signal || {};
    const checklist = signal.checklist || {};
    const action = signal.action || 'TUT';

    let signalClass = 'signal-hold';
    if (action.includes('AL')) signalClass = 'signal-buy';
    else if (action.includes('SAT')) signalClass = 'signal-sell';
    else if (action === 'ENGEL') signalClass = 'signal-blocked';

    const backtest = data.backtest || {};

    resultDiv.innerHTML = `
        <div class="result-card">
            <div class="result-header">
                <div>
                    <div class="result-symbol">${symbol}</div>
                    <div style="color:var(--text-muted);font-size:0.85rem">${data.current_price ? data.current_price.toFixed(2) + ' TL' : ''}</div>
                </div>
                <span class="result-signal ${signalClass}">${signal.emoji || ''} ${action}</span>
            </div>

            <div class="result-scores">
                <div class="score-item">
                    <div class="score-value" style="color:${getScoreColor(data.overall_score)}">${(data.overall_score || 50).toFixed(1)}</div>
                    <div class="score-label">Genel Skor</div>
                </div>
                <div class="score-item">
                    <div class="score-value">${(data.technical_score || 50).toFixed(0)}</div>
                    <div class="score-label">Teknik</div>
                </div>
                <div class="score-item">
                    <div class="score-value">${(data.ml_score || 50).toFixed(0)}</div>
                    <div class="score-label">ML Tahmin</div>
                </div>
                <div class="score-item">
                    <div class="score-value">${(data.news_score || 50).toFixed(0)}</div>
                    <div class="score-label">Haber</div>
                </div>
                <div class="score-item">
                    <div class="score-value">${(data.macro_score || 50).toFixed(0)}</div>
                    <div class="score-label">Makro</div>
                </div>
                <div class="score-item">
                    <div class="score-value">${(data.social_score || 50).toFixed(0)}</div>
                    <div class="score-label">Sosyal</div>
                </div>
            </div>

            ${!backtest.skipped ? `
            <div style="font-size:0.8rem;color:var(--text-muted);margin-bottom:12px;padding:10px;background:rgba(148,163,184,0.05);border-radius:8px">
                📋 Backtest: %${(backtest.accuracy || 0).toFixed(1)} doğruluk | 
                Güven: %${(backtest.confidence_score || 0).toFixed(1)} |
                Sinyal: ${backtest.signal_allowed ? '✅' : '❌'} | 
                Bildirim: ${backtest.notification_allowed ? '✅' : '❌'}
            </div>` : ''}

            <div class="result-checklist">
                <div style="font-size:0.85rem;font-weight:600;margin-bottom:8px">🔍 4'lü Süzgeç</div>
                ${renderChecklist(checklist)}
            </div>

            <div style="margin-top:14px;font-size:0.8rem;color:var(--text-muted)">
                📝 ${signal.reason || '—'}
            </div>

            ${data.errors && data.errors.length ? `
            <div style="margin-top:10px;font-size:0.75rem;color:var(--accent-yellow)">
                ⚠️ ${data.errors.join(', ')}
            </div>` : ''}
        </div>
    `;
}

function renderChecklist(cl) {
    if (!cl || Object.keys(cl).length === 0) {
        return '<div style="font-size:0.8rem;color:var(--text-muted)">Süzgeç verisi yok</div>';
    }

    const labels = {
        'haber_temiz_mi': '📰 Haber Temiz mi?',
        'para_girisi_var_mi': '💰 Para Girişi Var mı?',
        'matematik_onayliyor_mu': '📐 Matematik Onaylıyor mu?',
        'sosyal_medya_modu': '📱 Sosyal Medya Modu',
    };

    return Object.entries(cl).map(([key, val]) => {
        const isPass = val && (val.includes('EVET') || val.includes('POZİTİF'));
        const label = labels[key] || key;
        return `
            <div class="checklist-item">
                <span class="label">${label}</span>
                <span class="value ${isPass ? 'pass' : 'fail'}">${val}</span>
            </div>
        `;
    }).join('');
}

function getScoreColor(score) {
    if (score >= 70) return 'var(--accent-green)';
    if (score >= 55) return 'var(--accent-yellow)';
    if (score <= 30) return 'var(--accent-red)';
    return 'var(--text-primary)';
}

// ===== QUICK SCAN =====
async function quickScan() {
    const btn = document.getElementById('scan-btn');
    const container = document.getElementById('scan-results');

    btn.disabled = true;
    btn.innerHTML = '<span class="loading"></span> Taranıyor...';
    container.innerHTML = '<div class="empty-state"><span class="loading"></span> BIST 100 taranıyor...</div>';

    const data = await apiPost('/api/scan', {
        symbols: ['THYAO', 'GARAN', 'AKBNK', 'ISCTR', 'YKBNK', 'EREGL', 'SISE', 
                  'BIMAS', 'ASELS', 'TCELL', 'TUPRS', 'SAHOL', 'KCHOL', 'FROTO',
                  'TOASO', 'PGSUS', 'KOZAL', 'ARCLK', 'PETKM', 'MGROS']
    });

    btn.disabled = false;
    btn.innerHTML = 'Tara';

    if (!data) {
        container.innerHTML = '<div class="empty-state">❌ Tarama başarısız</div>';
        return;
    }

    let html = '';

    if (data.buy_signals && data.buy_signals.length > 0) {
        html += data.buy_signals.map(s => `
            <div class="scan-item buy" onclick="analyzeStockDirect('${s.symbol}')">
                <div class="scan-symbol">🟢 ${s.symbol}</div>
                <div class="scan-score">Skor: ${s.score.toFixed(0)}/100</div>
                <div class="scan-price">${s.price.toFixed(2)} TL</div>
            </div>
        `).join('');
    }

    if (data.sell_signals && data.sell_signals.length > 0) {
        html += data.sell_signals.map(s => `
            <div class="scan-item sell" onclick="analyzeStockDirect('${s.symbol}')">
                <div class="scan-symbol">🔴 ${s.symbol}</div>
                <div class="scan-score">Skor: ${s.score.toFixed(0)}/100</div>
                <div class="scan-price">${s.price.toFixed(2)} TL</div>
            </div>
        `).join('');
    }

    if (!html) {
        html = `<div class="empty-state">Taranan ${data.total_scanned || 0} hissede güçlü sinyal bulunamadı. Engellenen: ${data.blocked_count || 0}</div>`;
    }

    container.innerHTML = html;
}

// ===== ADD STOCK MODAL =====
function openAddModal() {
    document.getElementById('add-modal').style.display = 'flex';
}

function closeAddModal() {
    document.getElementById('add-modal').style.display = 'none';
}

async function addStock() {
    const symbol = document.getElementById('add-symbol').value.trim().toUpperCase();
    const quantity = parseFloat(document.getElementById('add-quantity').value);
    const price = parseFloat(document.getElementById('add-price').value);

    if (!symbol || isNaN(quantity) || isNaN(price)) {
        alert('Lütfen tüm alanları doldurun');
        return;
    }

    const result = await apiPost('/api/portfolio/add', {
        symbol, quantity, buy_price: price
    });

    if (result && result.success) {
        closeAddModal();
        loadPortfolio();
        document.getElementById('add-symbol').value = '';
        document.getElementById('add-quantity').value = '';
        document.getElementById('add-price').value = '';
    } else {
        alert(result ? result.message : 'Ekleme başarısız');
    }
}

// ===== ENTER KEY =====
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('analyze-input')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') analyzeStock();
    });

    // Initial loads
    loadPortfolio();
    loadSignals();
    loadSystemStatus();
});

// ===== SYSTEM STATUS =====
async function loadSystemStatus() {
    const data = await apiGet('/api/status');
    if (data) {
        document.getElementById('system-status').innerHTML = 
            `<span class="pulse"></span> ${data.status === 'active' ? 'Sistem Aktif' : 'Çevrimdışı'}`;
    }
}

// Auto-refresh every 5 minutes
setInterval(() => {
    loadPortfolio();
    loadSignals();
}, 300000);
