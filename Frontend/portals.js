/* ArcVault publisher portal connected to the shared SQLite-backed API. */
(() => {
  const $ = id => document.getElementById(id);
  const API = window.ARCVault_PUBLISHER_API_BASE || "http://127.0.0.1:5001";
  const landing = $('landingPage');
  const userPage = $('userPortalPage');
  const publisherPage = $('publisherPortalPage');
  const publisherLogin = $('publisherLogin');
  const publisherDashboard = $('publisherDashboard');
  const tokenKey = 'ArcVaultPublisherToken';
  const publisherKey = 'ArcVaultPublisherIdentity';
  let token = localStorage.getItem(tokenKey) || '';
  let publisher = null;
  let toastTimer;

  function showToast(message) {
    const toast = $('siteToast');
    toast.textContent = message;
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.hidden = true, 3500);
  }
  function showPage(which) {
    landing.hidden = which !== 'landing';
    userPage.hidden = which !== 'user';
    publisherPage.hidden = which !== 'publisher';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  function escapeHTML(value) {
    return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
  function money(value) {
    return new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:0 }).format(Number(value) || 0);
  }
  async function api(path, options = {}, authenticated = false) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (authenticated && token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`${API}${path}`, { ...options, headers });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || payload.message || `API request failed (${response.status})`);
    return payload;
  }
  function showLogin() {
    publisherLogin.hidden = false;
    publisherDashboard.hidden = true;
  }
  function showPublisherDashboard() {
    publisherLogin.hidden = true;
    publisherDashboard.hidden = false;
    $('publisherWelcome').textContent = `Welcome, ${publisher?.name || 'Publisher'}`;
    refreshPublisher();
  }
  async function validateSavedSession() {
    if (!token) return;
    try {
      const result = await api('/api/publishers/me', {}, true);
      publisher = result.publisher;
      localStorage.setItem(publisherKey, JSON.stringify(publisher));
      showPublisherDashboard();
    } catch {
      token = '';
      publisher = null;
      localStorage.removeItem(tokenKey);
      localStorage.removeItem(publisherKey);
      showLogin();
    }
  }

  $('openUserPortal').addEventListener('click', () => showPage('user'));
  $('openPublisherPortal').addEventListener('click', () => {
    showPage('publisher');
    if (token) validateSavedSession(); else showLogin();
  });
  $('userHomeButton').addEventListener('click', () => showPage('landing'));
  $('publisherHomeButton').addEventListener('click', () => showPage('landing'));

  $('publisherLoginForm').addEventListener('submit', async event => {
    event.preventDefault();
    const name = $('publisherName').value.trim();
    const email = $('publisherEmail').value.trim().toLowerCase();
    const password = $('publisherPassword').value;
    if (password.length < 8) { showToast('Password must contain at least 8 characters.'); return; }
    try {
      let result;
      try {
        result = await api('/api/publishers/login', { method:'POST', body:JSON.stringify({ email, password }) });
      } catch (loginError) {
        if (!String(loginError.message).toLowerCase().includes('invalid email or password')) throw loginError;
        try {
          await api('/api/publishers/register', { method:'POST', body:JSON.stringify({ name, email, password }) });
          result = await api('/api/publishers/login', { method:'POST', body:JSON.stringify({ email, password }) });
        } catch (registerError) {
          throw new Error('Sign-in failed. If you already have an account, check your password. Otherwise try a different email.');
        }
      }
      token = result.token;
      publisher = result.publisher;
      localStorage.setItem(tokenKey, token);
      localStorage.setItem(publisherKey, JSON.stringify(publisher));
      showPublisherDashboard();
      showToast('Connected to ArcVault. Your listings are stored in the shared database.');
    } catch (error) {
      showToast(error.message);
    }
  });

  $('publisherLogout').addEventListener('click', async () => {
    try { if (token) await api('/api/publishers/logout', { method:'POST' }, true); } catch {}
    token = '';
    publisher = null;
    localStorage.removeItem(tokenKey);
    localStorage.removeItem(publisherKey);
    $('publisherLoginForm').reset();
    showLogin();
    showToast('Signed out.');
  });

  async function refreshPublisher() {
    if (!token || !publisher) return;
    try {
      const [datasetResult, analyticsResult, transactionResult] = await Promise.all([
        api('/api/publishers/datasets', {}, true),
        api('/api/publishers/analytics', {}, true),
        api('/api/publishers/transactions', {}, true)
      ]);
      renderPublisher(datasetResult.datasets || [], analyticsResult.analytics || {}, transactionResult.transactions || []);
    } catch (error) {
      showToast(`Could not refresh publisher data: ${error.message}`);
    }
  }

  $('publisherDatasetForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (!token) { showToast('Sign in to publish a dataset.'); return; }
    const allowedUses = [];
    if ($('pubResearch').checked) allowedUses.push('research');
    if ($('pubEducation').checked) allowedUses.push('education');
    if ($('pubCommercial').checked) allowedUses.push('commercial_training');
    const payload = {
      name: $('pubDatasetName').value.trim(),
      language: $('pubLanguage').value,
      category: $('pubCategory').value,
      format: $('pubFormat').value,
      size: $('pubSize').value.trim(),
      price: Number($('pubPrice').value),
      licence: $('pubLicence').value,
      expiry_date: $('pubExpiry').value || '2099-12-31',
      allowed_uses: allowedUses,
      allowed_regions: ['India'],
      restricted_regions: [],
      derivative_works_allowed: $('pubDerivatives').checked,
      redistribution_allowed: $('pubRedistribution').checked,
      description: $('pubDescription').value.trim()
    };
    try {
      await api('/api/datasets', { method:'POST', body:JSON.stringify(payload) }, true);
      event.target.reset();
      $('pubResearch').checked = true;
      await refreshPublisher();
      // Refresh the user marketplace from the main backend, which reads the same DB.
      if (typeof window.refreshArcVaultMarketplace === 'function') window.refreshArcVaultMarketplace();
      showToast('Dataset published to the shared ArcVault database. It is now available to the marketplace and optimiser.');
    } catch (error) {
      showToast(`Could not publish dataset: ${error.message}`);
    }
  });

  function renderPublisher(datasets, analytics, transactions) {
    $('pubStatDatasets').textContent = analytics.published_datasets ?? datasets.filter(d => d.status === 'active').length;
    $('pubStatViews').textContent = analytics.views ?? 0;
    $('pubStatPurchases').textContent = analytics.transactions ?? 0;
    $('pubStatRevenue').textContent = money(analytics.revenue ?? 0);
    const mine = datasets.filter(d => d.status === 'active');
    $('publisherPublications').innerHTML = mine.map(d => `<tr>
      <td><strong>${escapeHTML(d.name)}</strong><br><small>${escapeHTML(d.backend_publication_id || `DS_${d.id}`)}</small></td>
      <td>${escapeHTML(d.language)}</td><td>${escapeHTML(d.licence)}</td><td>${money(d.price)}</td>
      <td>${Number(d.views) || 0}</td><td>${Number(d.purchases) || 0}</td><td>
      <button class="button button-secondary" data-action="view" data-id="${Number(d.id)}">+ Demo view</button>
      <button class="button button-secondary" data-action="purchase" data-id="${Number(d.id)}">+ Demo purchase</button>
      <button class="button button-secondary" data-action="delete" data-id="${Number(d.id)}">Withdraw</button></td></tr>`).join('');
    $('publisherEmpty').hidden = mine.length > 0;
    $('publisherTransactions').innerHTML = transactions.map(t => `<tr>
      <td>${escapeHTML(t.transaction_id)}</td><td>${escapeHTML(t.dataset_name || '—')}</td>
      <td>${escapeHTML(t.created_at)}</td><td>${escapeHTML(t.event_type)}</td>
      <td>${money(t.amount)}</td><td>Demo only</td></tr>`).join('');
    $('transactionsEmpty').hidden = transactions.length > 0;
  }

  $('publisherPublications').addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const id = button.dataset.id;
    try {
      if (button.dataset.action === 'delete') {
        if (!confirm('Withdraw this dataset? It will no longer appear in the marketplace or optimiser.')) return;
        await api(`/api/datasets/${id}`, { method:'DELETE' }, true);
      } else if (button.dataset.action === 'view') {
        await api(`/api/datasets/${id}/view`, { method:'POST' });
      } else if (button.dataset.action === 'purchase') {
        await api(`/api/datasets/${id}/transactions`, { method:'POST', body:JSON.stringify({ type:'purchase' }) }, true);
      }
      await refreshPublisher();
      if (typeof window.refreshArcVaultMarketplace === 'function') window.refreshArcVaultMarketplace();
      showToast('Publisher activity updated.');
    } catch (error) {
      showToast(error.message);
    }
  });

  showPage('landing');
  window.refreshArcVaultPublisher = refreshPublisher;
})();
