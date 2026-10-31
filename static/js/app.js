// ==========================================
// Xodim-Reyting & Paynet CRM: Frontend Logic
// ==========================================

let currentUser = null;
let authToken = localStorage.getItem("crm_token");
let otpCountdownTimer = null;
let pendingTelegramId = null;
let currentActiveTab = { name: "reports", isAdmin: false };
let currentAnalyticsPeriod = "7d";
let currentChartMetric = "all";
let analyticsDataCache = null;
let mainChartInstance = null;
let growthChartInstance = null;
let operatorChartInstance = null;

// ==========================================
// Mavzu (Dark / Day rejim) Boshqaruvi
// ==========================================
function getAppTheme() {
  return localStorage.getItem("app_theme") || "dark";
}

function applyTheme(theme) {
  const isLight = theme === "light";
  if (isLight) {
    document.documentElement.classList.remove("dark");
    document.documentElement.classList.add("theme-light");
    document.documentElement.setAttribute("data-theme", "light");
    document.body.classList.remove("dark");
    document.body.classList.add("theme-light");
  } else {
    document.documentElement.classList.add("dark");
    document.documentElement.classList.remove("theme-light");
    document.documentElement.setAttribute("data-theme", "dark");
    document.body.classList.add("dark");
    document.body.classList.remove("theme-light");
  }
  try {
    localStorage.setItem("app_theme", theme);
  } catch(e) {}

  const icon = isLight ? "☀️" : "🌙";
  const text = isLight ? "Kunduzgi" : "Tungi";
  const fullText = isLight ? "Kunduzgi rejim" : "Tungi rejim";

  // Desktop navbar tugmasi
  const themeIconEl = document.getElementById("theme-icon");
  const themeTextEl = document.getElementById("theme-text");
  if (themeIconEl) themeIconEl.innerText = icon;
  if (themeTextEl) themeTextEl.innerText = text;

  // Mobil yon menyu (drawer) elementi
  const sideIconEl = document.getElementById("sidebar-theme-icon");
  const sideTextEl = document.getElementById("sidebar-theme-text");
  if (sideIconEl) sideIconEl.innerText = icon;
  if (sideTextEl) sideTextEl.innerText = fullText;

  // Agar hozir monitoring ochilgan bo'lsa, diagrammalarni yangi mavzu ranglarida qayta chizish
  if (typeof currentActiveTab !== "undefined" && currentActiveTab && currentActiveTab.name === "analytics" && analyticsDataCache) {
    renderAllAnalyticsCharts();
  }
}

function toggleAppTheme() {
  const current = getAppTheme();
  const next = current === "light" ? "dark" : "light";
  applyTheme(next);
  showToast(`${next === "light" ? "☀️ Kunduzgi" : "🌙 Tungi"} rejim yoqildi`, "info");
}

function initTheme() {
  applyTheme(getAppTheme());
}

// Skript yuklanishi bilan zudlik bilan mavzuni qo'llash
initTheme();

// API Base URL (Vercel va tashqi bulutli xostinglar uchun)
const API_BASE_URL = (
  window.API_BASE_URL ||
  localStorage.getItem("api_base_url") ||
  ""
).replace(/\/+$/, "");

// API Helper
async function api(endpoint, method = "GET", data = null) {
  const headers = { "Content-Type": "application/json" };
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }

  const options = { method, headers };
  if (data && method !== "GET") {
    options.body = JSON.stringify(data);
  }

  const targetUrl = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;

  try {
    const res = await fetch(targetUrl, options);
    const json = await res.json();
    if (!res.ok) {
      if (res.status === 401 && !endpoint.includes("/api/auth/")) {
        logout();
      }
      throw new Error(json.detail || json.message || "Xatolik yuz berdi");
    }
    return json;
  } catch (err) {
    showToast(err.message, "danger");
    throw err;
  }
}

// Toast Notification
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container") || createToastContainer();
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const icon = type === "success" ? "✅" : type === "danger" ? "❌" : "ℹ️";
  toast.innerHTML = `<span style="font-size: 1.25rem;">${icon}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function createToastContainer() {
  const c = document.createElement("div");
  c.id = "toast-container";
  document.body.appendChild(c);
  return c;
}

// O'zbekcha sonlarni so'z bilan ifodalash
function numberToUzbekWords(num) {
  if (!num || isNaN(num) || num <= 0) return "";
  num = Math.floor(num);

  const ones = ["", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"];
  const tens = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"];

  function convertHundreds(n) {
    let str = "";
    if (n >= 100) {
      const h = Math.floor(n / 100);
      str += (h === 1 ? "bir yuz " : ones[h] + " yuz ");
      n %= 100;
    }
    if (n >= 10) {
      str += tens[Math.floor(n / 10)] + " ";
      n %= 10;
    }
    if (n > 0) {
      str += ones[n] + " ";
    }
    return str.trim();
  }

  let result = "";
  if (num >= 1000000000) {
    const b = Math.floor(num / 1000000000);
    result += convertHundreds(b) + " milliard ";
    num %= 1000000000;
  }
  if (num >= 1000000) {
    const m = Math.floor(num / 1000000);
    result += convertHundreds(m) + " million ";
    num %= 1000000;
  }
  if (num >= 1000) {
    const th = Math.floor(num / 1000);
    result += convertHundreds(th) + " ming ";
    num %= 1000;
  }
  if (num > 0) {
    result += convertHundreds(num);
  }

  result = result.trim();
  return result ? result.charAt(0).toUpperCase() + result.slice(1) + " so'm" : "";
}

// Summa hajmiga qarab reaktiv hayratlanish emojisi (Rekord 100 000 000 so'm)
function getAmountEmoji(amount) {
  if (!amount || amount <= 0) return { emoji: "🙂", label: "Kiritilmoqda..." };
  if (amount < 30000) return { emoji: "⚠️", label: "Minimal: 30 000 so'm" };
  if (amount < 100000) return { emoji: "🙂", label: "Standart to'lov" };
  if (amount < 500000) return { emoji: "👍", label: "Yaxshi summa" };
  if (amount < 2000000) return { emoji: "😃", label: "Katta to'lov" };
  if (amount < 10000000) return { emoji: "🔥", label: "Yuqori summa!" };
  if (amount < 50000000) return { emoji: "😲", label: "Juda yirik summa!" };
  if (amount < 100000000) return { emoji: "🤯", label: "Ulkan to'lov!" };
  return { emoji: "🤑 💥", label: "Rekord darajadagi summa!" };
}

// Formatters
function formatNumberSpaces(val) {
  if (val === 0 || val === "0") return "0";
  if (!val) return "";
  const clean = val.toString().replace(/\D/g, "");
  return clean ? clean.replace(/\B(?=(\d{3})+(?!\d))/g, " ") : "";
}

function parseFormattedNumber(val) {
  if (!val) return 0;
  return parseFloat(val.toString().replace(/\s/g, "")) || 0;
}

// Copy to Clipboard
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast(`Nusxalandi: ${text}`, "success");
  });
}

function formatRoleName(role) {
  if (role === "ADMIN") return "Bosh Rahbar";
  if (role === "CASHIER") return "Kassir";
  if (role === "EMPLOYEE") return "Xodim";
  return role || "Xodim";
}

function formatStatusName(status) {
  if (!status) return "-";
  const s = String(status).toUpperCase();
  if (s === "APPROVED") return "Tasdiqlandi ✅";
  if (s === "REJECTED") return "Rad etildi ❌";
  if (s === "PENDING") return "Kutilmoqda ⏳";
  if (s === "TOPSHIRILMAGAN") return "Topshirilmagan ⚠️";
  return status;
}

function formatStatusBadge(status, extraText = "") {
  const extra = extraText ? ` (${extraText})` : "";
  if (!status) return `<span class="status-badge status-pending">-</span>`;
  const s = String(status).toUpperCase();
  if (s === "APPROVED") return `<span class="status-badge status-approved">Tasdiqlandi ✅${extra}</span>`;
  if (s === "REJECTED") return `<span class="status-badge status-rejected">Rad etildi ❌${extra}</span>`;
  if (s === "PENDING") return `<span class="status-badge status-pending">Kutilmoqda ⏳</span>`;
  if (s === "TOPSHIRILMAGAN") return `<span class="status-badge status-pending" style="background: rgba(239, 68, 68, 0.15); color: #f87171; border-color: rgba(239, 68, 68, 0.3);">Topshirilmagan ⚠️</span>`;
  return `<span class="status-badge status-pending">${status}</span>`;
}

// ==========================================
// Sana va Vaqt Formatteri (Toshkent vaqti UTC+5)
// ==========================================

function parseUtcDate(dateStr) {
  if (!dateStr) return null;
  const str = String(dateStr).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) {
    const parts = str.split('-');
    return `${parts[2]}.${parts[1]}.${parts[0]}`;
  }
  let d;
  if (str.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(str)) {
    d = new Date(str);
  } else {
    // SQLite standart CURRENT_TIMESTAMP ("YYYY-MM-DD HH:MM:SS") UTC da saqlanadi
    d = new Date(str.replace(' ', 'T') + 'Z');
  }
  if (isNaN(d.getTime())) return null;
  return d;
}

function formatTashkentDateTime(dateStr, includeSeconds = false) {
  if (!dateStr) return '-';
  const parsed = parseUtcDate(dateStr);
  if (typeof parsed === 'string') return parsed;
  if (!parsed) return dateStr;

  // UTC vaqtiga +5 soat qo'shib Toshkent vaqtini olamiz
  const tashkentMs = parsed.getTime() + (5 * 60 * 60 * 1000);
  const t = new Date(tashkentMs);

  const year = t.getUTCFullYear();
  const month = String(t.getUTCMonth() + 1).padStart(2, '0');
  const day = String(t.getUTCDate()).padStart(2, '0');
  const hours = String(t.getUTCHours()).padStart(2, '0');
  const minutes = String(t.getUTCMinutes()).padStart(2, '0');
  const seconds = String(t.getUTCSeconds()).padStart(2, '0');

  if (includeSeconds) {
    return `${day}.${month}.${year} ${hours}:${minutes}:${seconds}`;
  }
  return `${day}.${month}.${year} ${hours}:${minutes}`;
}

function formatDateOnly(dateStr) {
  if (!dateStr) return '-';
  const str = String(dateStr).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) {
    const parts = str.split('-');
    return `${parts[2]}.${parts[1]}.${parts[0]}`;
  }
  const formatted = formatTashkentDateTime(dateStr);
  return formatted.split(' ')[0] || dateStr;
}

// ==========================================
// Auth & App Init
// ==========================================

// ==========================================
// 3 SOAT HARAKATSIZLIK (INACTIVITY TIMEOUT) STANDARTI
// ==========================================
const INACTIVITY_TIMEOUT_MS = 3 * 60 * 60 * 1000; // 3 soat = 10 800 000 ms
let lastActivitySaved = 0;

function recordUserActivity() {
  const now = Date.now();
  if (now - lastActivitySaved > 10000) {
    lastActivitySaved = now;
    if (authToken) {
      localStorage.setItem("crm_last_activity", now.toString());
    }
  }
}

function checkInactivityTimeout() {
  if (!authToken) return false;
  const last = parseInt(localStorage.getItem("crm_last_activity") || "0", 10);
  if (last > 0 && (Date.now() - last > INACTIVITY_TIMEOUT_MS)) {
    handleInactivityLogout();
    return true;
  }
  return false;
}

function handleInactivityLogout() {
  authToken = null;
  currentUser = null;
  localStorage.removeItem("crm_token");
  localStorage.removeItem("crm_last_activity");

  // Hech qanday ogohlantirish oynasi (alert) ko'rsatilmasdan, avtomatik ravishda Login oynasi ochiladi
  const appContent = document.getElementById("app-content");
  if (appContent) appContent.style.display = "none";
  const navTabsAdmin = document.getElementById("nav-tabs-admin");
  if (navTabsAdmin) navTabsAdmin.style.display = "none";
  const navTabsEmployee = document.getElementById("nav-tabs-employee");
  if (navTabsEmployee) navTabsEmployee.style.display = "none";

  showLoginModal();
}

// Barcha harakatlarni tinglash
['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart', 'click'].forEach(evt => {
  window.addEventListener(evt, recordUserActivity, { passive: true });
});

// Har 30 soniyada fonda tekshirib borish
setInterval(checkInactivityTimeout, 30000);

async function initApp() {
  if (authToken) {
    if (checkInactivityTimeout()) {
      return;
    }
    try {
      const res = await api("/api/auth/me");
      currentUser = res.user;
      localStorage.setItem("crm_last_activity", Date.now().toString());
      renderApp();
      return;
    } catch (e) {
      authToken = null;
      localStorage.removeItem("crm_token");
      localStorage.removeItem("crm_last_activity");
    }
  }
  showLoginModal();
}

function logout() {
  authToken = null;
  currentUser = null;
  localStorage.removeItem("crm_token");
  localStorage.removeItem("crm_last_activity");
  window.location.reload();
}

function showLoginModal() {
  document.getElementById("login-modal").style.display = "flex";
  document.getElementById("login-step-1").style.display = "block";
  document.getElementById("login-step-2").style.display = "none";
}

// Login Step 1: Submit ID & Password
let otpSecondsLeft = 0;

function getCooldownSecondsLeft() {
  const cd = localStorage.getItem("otp_cooldown_until");
  if (!cd) return otpSecondsLeft;
  const diff = Math.ceil((parseInt(cd, 10) - Date.now()) / 1000);
  return Math.max(diff > 0 ? diff : 0, otpSecondsLeft);
}

function updateRetryButtonUI() {
  const retryBtn = document.getElementById("btn-retry-login");
  if (!retryBtn) return;
  const left = getCooldownSecondsLeft();
  if (left > 0) {
    retryBtn.disabled = true;
    retryBtn.style.opacity = "0.5";
    retryBtn.style.cursor = "not-allowed";
    retryBtn.innerText = `⏳ Qaytadan urinish (${left}s)`;
  } else {
    retryBtn.disabled = false;
    retryBtn.style.opacity = "1";
    retryBtn.style.cursor = "pointer";
    retryBtn.innerText = `🔄 Qaytadan urinish`;
  }
}

// Serverni oldindan uyg'otib qo'yish (Cold-start va uyqudan uyg'onish kechikishining oldini olish)
function prewarmBackend() {
  try {
    fetch("/api/health").catch(() => {});
  } catch(e) {}
}
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", prewarmBackend);
} else {
  prewarmBackend();
}

let isLoginStep1InProgress = false;

async function handleLoginStep1(e) {
  if (e) e.preventDefault();
  if (isLoginStep1InProgress) return;
  isLoginStep1InProgress = true;
  const alertEl = document.getElementById("login-error-alert");
  const submitBtn = document.getElementById("btn-login-submit");
  if (alertEl) {
    alertEl.style.display = "none";
    alertEl.style.background = "rgba(239, 68, 68, 0.15)";
    alertEl.style.borderColor = "rgba(239, 68, 68, 0.4)";
    alertEl.style.color = "#fca5a5";
  }

  const tgIdRaw = document.getElementById("login-telegram-id")?.value || "";
  const password = document.getElementById("login-password")?.value || "";
  const tgIdClean = tgIdRaw.replace(/\D/g, "");

  if (!tgIdClean || !password.trim()) {
    isLoginStep1InProgress = false;
    const msg = "Login va parolni kiriting!";
    if (alertEl) { alertEl.innerText = msg; alertEl.style.display = "block"; }
    showToast(msg, "danger");
    return;
  }

  const left = getCooldownSecondsLeft();
  if (left > 0) {
    isLoginStep1InProgress = false;
    const msg = `1 minutda faqat 1 marta urinish mumkin! Qayta urinish ${left} soniyadan keyin.`;
    if (alertEl) { alertEl.innerText = msg; alertEl.style.display = "block"; }
    showToast(msg, "warning");
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = "⏳ Tekshirilmoqda...";
  }

  try {
    const res = await api("/api/auth/login", "POST", {
      telegram_id: parseInt(tgIdClean, 10),
      password: password.trim()
    });
    pendingTelegramId = parseInt(tgIdClean, 10);

    // Step 2 ga o'tish (OTP Kod kiritish oynasi)
    document.getElementById("login-step-1").style.display = "none";
    document.getElementById("login-step-2").style.display = "block";

    // Telegram ID ko'rsatish
    const tgDisplay = document.getElementById("otp-tg-id-display");
    if (tgDisplay) tgDisplay.innerText = tgIdClean;

    showToast(res.message || "Tasdiqlash kodi Telegram lichkangizga yuborildi!", "success");

    startOtpCountdown(res.expires_in || 60);

    const otpInput = document.getElementById("otp-code-input");
    if (otpInput) {
      otpInput.value = "";
      otpInput.focus();
    }
  } catch (err) {
    const errText = err.message || "Kirishda xatolik yuz berdi!";
    if (alertEl) {
      alertEl.style.background = "rgba(239, 68, 68, 0.15)";
      alertEl.style.borderColor = "rgba(239, 68, 68, 0.4)";
      alertEl.style.color = "#fca5a5";
      alertEl.innerText = errText;
      alertEl.style.display = "block";
    }
    if (errText.includes("1 minutda faqat 1 marta")) {
      pendingTelegramId = parseInt(tgIdClean, 10);
      document.getElementById("login-step-1").style.display = "none";
      document.getElementById("login-step-2").style.display = "block";
      const tgDisplay = document.getElementById("otp-tg-id-display");
      if (tgDisplay) tgDisplay.innerText = tgIdClean;
      startOtpCountdown(getCooldownSecondsLeft() || 60);
    }
  } finally {
    isLoginStep1InProgress = false;
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = "Kirish ➡️";
    }
  }
}

function startOtpCountdown(seconds) {
  clearInterval(otpCountdownTimer);
  otpSecondsLeft = seconds;
  localStorage.setItem("otp_cooldown_until", (Date.now() + seconds * 1000).toString());
  const timerEl = document.getElementById("otp-timer");
  if (timerEl) timerEl.innerText = `${otpSecondsLeft}s`;
  updateRetryButtonUI();

  otpCountdownTimer = setInterval(() => {
    otpSecondsLeft--;
    const left = getCooldownSecondsLeft();
    if (left <= 0) {
      clearInterval(otpCountdownTimer);
      otpSecondsLeft = 0;
      localStorage.removeItem("otp_cooldown_until");
      if (timerEl) timerEl.innerText = "Muddati tugadi!";
      updateRetryButtonUI();
    } else {
      if (timerEl) timerEl.innerText = `${left}s`;
      updateRetryButtonUI();
    }
  }, 1000);
}

function handleRetryLogin() {
  const left = getCooldownSecondsLeft();
  if (left > 0) {
    showToast(`1 minutda faqat 1 marta urinish mumkin! Qayta urinish ${left} soniyadan keyin.`, "warning");
    return;
  }
  showLoginModal();
}

let isVerifyOtpInProgress = false;

// Login Step 2: Verify OTP
async function handleVerifyOtp(e) {
  if (e) e.preventDefault();
  if (isVerifyOtpInProgress) return;
  isVerifyOtpInProgress = true;

  const alertEl = document.getElementById("otp-error-alert");
  const submitBtn = document.getElementById("btn-verify-submit");
  if (alertEl) alertEl.style.display = "none";

  const otp = document.getElementById("otp-code-input")?.value.trim() || "";
  if (!otp || otp.length !== 6) {
    isVerifyOtpInProgress = false;
    const msg = "6 xonali tasdiqlash kodini to'liq kiriting!";
    if (alertEl) { alertEl.innerText = msg; alertEl.style.display = "block"; }
    showToast(msg, "danger");
    return;
  }

  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = "⏳ Tekshirilmoqda...";
  }

  try {
    const res = await api("/api/auth/verify-otp", "POST", {
      telegram_id: pendingTelegramId,
      otp: otp
    });

    authToken = res.access_token;
    localStorage.setItem("crm_token", authToken);
    localStorage.setItem("crm_last_activity", Date.now().toString());
    currentUser = res.user;
    localStorage.removeItem("otp_cooldown_until");
    otpSecondsLeft = 0;

    clearInterval(otpCountdownTimer);
    document.getElementById("login-modal").style.display = "none";
    showToast("Tizimga muvaffaqiyatli kirdingiz!", "success");
    renderApp();
  } catch (err) {
    if (alertEl) {
      alertEl.innerText = err.message || "Kodni tekshirishda xatolik!";
      alertEl.style.display = "block";
    }
  } finally {
    isVerifyOtpInProgress = false;
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerText = "Tasdiqlash va Kirish 🔓";
    }
  }
}

// ==========================================
// ==========================================
// RESPONSIV CHAP YON MENYU (SIDEBAR DRAWER)
// ==========================================

function toggleSidebarMenu() {
  const drawer = document.getElementById("sidebar-drawer");
  const overlay = document.getElementById("sidebar-overlay");
  if (!drawer || !overlay) return;
  if (drawer.classList.contains("open")) {
    closeSidebarMenu();
  } else {
    openSidebarMenu();
  }
}

function openSidebarMenu() {
  const drawer = document.getElementById("sidebar-drawer");
  const overlay = document.getElementById("sidebar-overlay");
  if (drawer && overlay) {
    updateSidebarContent();
    drawer.classList.add("open");
    overlay.classList.add("open");
    document.body.style.overflow = "hidden";
  }
}

function closeSidebarMenu() {
  const drawer = document.getElementById("sidebar-drawer");
  const overlay = document.getElementById("sidebar-overlay");
  if (drawer && overlay) {
    drawer.classList.remove("open");
    overlay.classList.remove("open");
    document.body.style.overflow = "";
  }
}

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeSidebarMenu();
});

function updateSidebarContent() {
  if (!currentUser) return;

  const nameEl = document.getElementById("sidebar-user-name");
  const roleEl = document.getElementById("sidebar-user-role");
  const debtEl = document.getElementById("sidebar-user-debt");
  const usdRateEl = document.getElementById("sidebar-usd-rate-text");

  if (usdRateEl && currentUsdRate) {
    usdRateEl.innerText = `1$ = ${formatNumberSpaces(currentUsdRate)} so'm`;
  }

  if (nameEl) {
    if (currentUser.role === "ADMIN" && (currentUser.full_name === "Bosh Rahbar" || !currentUser.full_name)) {
      nameEl.innerText = isRahbarCashierMode ? "💼 Kassir (Rejim)" : "👑 Bosh Rahbar";
      if (roleEl) roleEl.style.display = "none";
    } else {
      nameEl.innerText = currentUser.full_name;
      if (roleEl) roleEl.style.display = "inline-flex";
    }
  }

  if (roleEl && currentUser.role !== "ADMIN") {
    if (currentUser.role === "CASHIER") {
      roleEl.className = "badge badge-cashier";
      roleEl.innerText = "💼 Kassir";
    } else {
      roleEl.className = "badge badge-employee";
      roleEl.innerText = "👤 Xodim";
    }
  }

  if (debtEl) {
    if (currentUser.role !== "ADMIN" && currentUser.debt_amount !== undefined) {
      debtEl.style.display = "inline-flex";
      debtEl.innerText = `Qarz: ${formatNumberSpaces(currentUser.debt_amount)} so'm`;
    } else {
      debtEl.style.display = "none";
    }
  }

  const navContainer = document.getElementById("sidebar-nav-list");
  if (!navContainer) return;

  let menuItems = [];

  if (currentUser.role === "ADMIN") {
    if (isRahbarCashierMode) {
      menuItems = [
        { id: "cashier-intake", icon: "📥", title: "Kassa qabul qilish", isAdmin: false },
        { id: "cashier-sims", icon: "📲", title: "Sim-karta tarqatish", isAdmin: false },
        { id: "rahbar-back", icon: "⬅️", title: "Rahbar paneliga qaytish", isAction: true, action: "toggleRahbarCashierMode" }
      ];
    } else {
      menuItems = [
        { id: "reports", icon: "📋", title: "Hisobotlarni qabul qilish", isAdmin: true },
        { id: "analytics", icon: "📈", title: "Savdo monitoringi", isAdmin: true },
        { id: "givens", icon: "💵", title: "Berilgan summalar", isAdmin: true },
        { id: "topups", icon: "💳", title: "Karta so'rovlari", isAdmin: true },
        { id: "comparison", icon: "⚖️", title: "Kassa taqqoslash (Audit)", isAdmin: true },
        { id: "users", icon: "👥", title: "Xodimlar & Qarz boshqaruvi", isAdmin: true },
        { id: "cashier", icon: "💼", title: "Kassir tayinlash & Tarix", isAdmin: true },
        { id: "sims", icon: "📲", title: "Sim-karta boshqaruvi", isAdmin: true },
        { id: "rating", icon: "🏆", title: "Reyting & KPI", isAdmin: true },
        { id: "audit", icon: "🛡️", title: "Audit loglar", isAdmin: true },
        { id: "rahbar-cashier-toggle", icon: "💼", title: "Kassir rejimiga o'tish", isAction: true, action: "toggleRahbarCashierMode" }
      ];
    }
  } else if (currentUser.role === "CASHIER") {
    menuItems = [
      { id: "card-topup", icon: "💳", title: "Karta to'ldirish", isAdmin: false },
      { id: "given-amount", icon: "💵", title: "Berilgan summa", isAdmin: false },
      { id: "daily-report", icon: "📊", title: "Hisobot topshirish", isAdmin: false },
      { id: "cashier-intake", icon: "📥", title: "Kassa qabul qilish", isAdmin: false },
      { id: "cashier-sims", icon: "📲", title: "Sim-karta tarqatish", isAdmin: false },
      { id: "emp-rating", icon: "🏆", title: "Reyting oynasi", isAdmin: false }
    ];
  } else {
    menuItems = [
      { id: "card-topup", icon: "💳", title: "Karta to'ldirish", isAdmin: false },
      { id: "given-amount", icon: "💵", title: "Berilgan summa", isAdmin: false },
      { id: "daily-report", icon: "📊", title: "Hisobot topshirish", isAdmin: false },
      { id: "emp-rating", icon: "🏆", title: "Reyting oynasi", isAdmin: false }
    ];
  }

  navContainer.innerHTML = menuItems.map(item => {
    if (item.isAction) {
      return `
        <button type="button" class="sidebar-nav-item" style="border: 1px dashed rgba(245, 158, 11, 0.4); color: #fbbf24; margin-top: 0.5rem;" onclick="${item.action}(); closeSidebarMenu();">
          <span class="nav-icon">${item.icon}</span>
          <span>${item.title}</span>
        </button>
      `;
    }

    const isActive = (currentActiveTab.isAdmin === item.isAdmin && currentActiveTab.name === item.id);
    const clickHandler = item.isAdmin 
      ? `switchAdminTab('${item.id}'); closeSidebarMenu();` 
      : `switchEmployeeTab('${item.id}'); closeSidebarMenu();`;

    return `
      <button type="button" class="sidebar-nav-item ${isActive ? 'active' : ''}" id="sidebar-item-${item.id}" onclick="${clickHandler}">
        <span class="nav-icon">${item.icon}</span>
        <span>${item.title}</span>
      </button>
    `;
  }).join("");
}

// UI Rendering & Role Management
// ==========================================

function renderApp() {
  document.getElementById("login-modal").style.display = "none";
  document.getElementById("app-content").style.display = "block";

  // Navbar user details
  const userNameEl = document.getElementById("nav-user-name");
  const roleBadge = document.getElementById("nav-user-role");
  const debtBadge = document.getElementById("nav-user-debt");

  const isAdminDuplicateName = (currentUser.role === "ADMIN" && (currentUser.full_name === "Bosh Rahbar" || !currentUser.full_name));
  userNameEl.innerText = isAdminDuplicateName ? "" : currentUser.full_name;
  userNameEl.style.display = isAdminDuplicateName ? "none" : "";

  const adminNav = document.getElementById("nav-tabs-admin");
  const employeeNav = document.getElementById("nav-tabs-employee");
  const cashierTabBtn = document.getElementById("tab-btn-cashier-intake");

  // Barcha panellarni tozalash
  document.querySelectorAll(".admin-pane").forEach(p => p.style.display = "none");
  document.querySelectorAll(".employee-pane").forEach(p => p.style.display = "none");

  // Dollar kursini barcha foydalanuvchilar uchun yangilash
  loadUsdRate();
  const usdRateBadge = document.getElementById("usd-rate-badge");
  const rahbarCashierToggle = document.getElementById("btn-rahbar-cashier-toggle");

  if (currentUser.role === "ADMIN") {
    roleBadge.className = "badge badge-admin";
    roleBadge.innerText = "👑 Bosh Rahbar";
    debtBadge.style.display = "none";
    if (usdRateBadge) {
      usdRateBadge.style.cursor = "pointer";
      usdRateBadge.title = "Dollar kursini belgilash uchun bosing";
    }
    if (rahbarCashierToggle) {
      rahbarCashierToggle.style.display = "inline-flex";
      rahbarCashierToggle.innerHTML = "<span>💼</span> Kassir rejimi";
      rahbarCashierToggle.className = "badge badge-cashier";
      rahbarCashierToggle.style.background = "";
      rahbarCashierToggle.style.borderColor = "";
      rahbarCashierToggle.style.color = "";
    }

    isRahbarCashierMode = false;

    // Faqat Rahbar menyusini ko'rsatish, Xodim menyusini butunlay yashirish!
    adminNav.style.display = "flex";
    adminNav.style.flexWrap = "nowrap";
    employeeNav.style.display = "none";

    // Rahbar uchun boshlang'ich oyna: Kunlik hisobotlarni qabul qilish
    switchAdminTab("reports");
  } else if (currentUser.role === "CASHIER") {
    roleBadge.className = "badge badge-cashier";
    roleBadge.innerText = "💼 Kassir";
    debtBadge.style.display = "inline-flex";
    debtBadge.innerText = `Qarz: ${formatNumberSpaces(currentUser.debt_amount)} so'm`;
    if (usdRateBadge) {
      usdRateBadge.style.cursor = "default";
      usdRateBadge.title = "Joriy dollar kursi";
    }
    if (rahbarCashierToggle) rahbarCashierToggle.style.display = "none";

    // Xodim & Kassir menyusini ko'rsatish, Rahbar menyusini yashirish
    adminNav.style.display = "none";
    employeeNav.style.display = "flex";
    employeeNav.style.flexWrap = "nowrap";

    // Barcha xodim tablarini ko'rsatish
    document.getElementById("tab-btn-card-topup").style.display = "inline-flex";
    document.getElementById("tab-btn-given-amount").style.display = "inline-flex";
    document.getElementById("tab-btn-daily-report").style.display = "inline-flex";
    document.getElementById("tab-btn-emp-rating").style.display = "inline-flex";
    cashierTabBtn.style.display = "inline-flex";
    const cashierSimsBtn = document.getElementById("tab-btn-cashier-sims");
    if (cashierSimsBtn) cashierSimsBtn.style.display = "inline-flex";
    const rahbarBackBtn = document.getElementById("tab-btn-rahbar-back");
    if (rahbarBackBtn) rahbarBackBtn.style.display = "none";

    // Kassir uchun boshlang'ich oyna: Karta to'ldirish
    switchEmployeeTab("card-topup");
  } else {
    // EMPLOYEE (Oddiy xodim)
    roleBadge.className = "badge badge-employee";
    roleBadge.innerText = "👤 Xodim";
    debtBadge.style.display = "inline-flex";
    debtBadge.innerText = `Qarz: ${formatNumberSpaces(currentUser.debt_amount)} so'm`;
    if (usdRateBadge) {
      usdRateBadge.style.cursor = "default";
      usdRateBadge.title = "Joriy dollar kursi";
    }
    if (rahbarCashierToggle) rahbarCashierToggle.style.display = "none";

    // Faqat Xodim menyusini ko'rsatish (4 ta oyna), Kassir va Rahbar menyusini yashirish
    adminNav.style.display = "none";
    employeeNav.style.display = "flex";

    document.getElementById("tab-btn-card-topup").style.display = "inline-flex";
    document.getElementById("tab-btn-given-amount").style.display = "inline-flex";
    document.getElementById("tab-btn-daily-report").style.display = "inline-flex";
    document.getElementById("tab-btn-emp-rating").style.display = "inline-flex";
    cashierTabBtn.style.display = "none";
    const cashierSimsBtn = document.getElementById("tab-btn-cashier-sims");
    if (cashierSimsBtn) cashierSimsBtn.style.display = "none";
    const rahbarBackBtn = document.getElementById("tab-btn-rahbar-back");
    if (rahbarBackBtn) rahbarBackBtn.style.display = "none";

    // Xodim uchun boshlang'ich oyna: Karta to'ldirish
    switchEmployeeTab("card-topup");
  }

  // Yon menyuni ham foydalanuvchi ma'lumotlari bilan to'liq sinxronlash
  updateSidebarContent();
}

// Rahbar Kassir rejimiga o'tishi / qaytishi
let isRahbarCashierMode = false;

function toggleRahbarCashierMode() {
  if (!currentUser || currentUser.role !== "ADMIN") return;
  isRahbarCashierMode = !isRahbarCashierMode;

  const adminNav = document.getElementById("nav-tabs-admin");
  const employeeNav = document.getElementById("nav-tabs-employee");
  const roleBadge = document.getElementById("nav-user-role");
  const toggleBtn = document.getElementById("btn-rahbar-cashier-toggle");
  const rahbarBackBtn = document.getElementById("tab-btn-rahbar-back");

  document.querySelectorAll(".admin-pane").forEach(p => p.style.display = "none");
  document.querySelectorAll(".employee-pane").forEach(p => p.style.display = "none");

  if (isRahbarCashierMode) {
    // Kassir rejimiga o'tish (Lekin xodim bo'la olmaydi!)
    adminNav.style.display = "none";
    employeeNav.style.display = "flex";
    employeeNav.style.flexWrap = "wrap";

    // Oddiy xodim tablarini mutlaqo yashirish (Rahbar xodim bo'la olmaydi!)
    document.getElementById("tab-btn-card-topup").style.display = "none";
    document.getElementById("tab-btn-given-amount").style.display = "none";
    document.getElementById("tab-btn-daily-report").style.display = "none";
    document.getElementById("tab-btn-emp-rating").style.display = "none";

    // Faqat Kassir tablarini ko'rsatish
    document.getElementById("tab-btn-cashier-intake").style.display = "inline-flex";
    document.getElementById("tab-btn-cashier-sims").style.display = "inline-flex";
    if (rahbarBackBtn) rahbarBackBtn.style.display = "inline-flex";

    roleBadge.className = "badge badge-cashier";
    roleBadge.innerText = "👑 Bosh Rahbar (Kassir)";
    if (toggleBtn) {
      toggleBtn.innerHTML = "<span>⬅️</span> Rahbar paneli";
      toggleBtn.style.background = "rgba(99, 102, 241, 0.25)";
      toggleBtn.style.borderColor = "rgba(99, 102, 241, 0.5)";
      toggleBtn.style.color = "#c7d2fe";
    }

    switchEmployeeTab("cashier-intake");
    updateSidebarContent();
    showToast("Kassir rejimiga o'tdingiz (Kassa qabul qilish & Sim-karta tarqatish)", "info");
  } else {
    // Rahbar paneliga qaytish
    adminNav.style.display = "flex";
    employeeNav.style.display = "none";
    if (rahbarBackBtn) rahbarBackBtn.style.display = "none";

    roleBadge.className = "badge badge-admin";
    roleBadge.innerText = "👑 Bosh Rahbar";
    if (toggleBtn) {
      toggleBtn.innerHTML = "<span>💼</span> Kassir rejimi";
      toggleBtn.style.background = "rgba(245, 158, 11, 0.2)";
      toggleBtn.style.borderColor = "rgba(245, 158, 11, 0.5)";
      toggleBtn.style.color = "#fbbf24";
    }

    switchAdminTab("reports");
    updateSidebarContent();
    showToast("Bosh Rahbar paneliga qaytdingiz", "info");
  }
}

// Rahbar (Admin) tablarini almashtirish
function switchAdminTab(tabName) {
  currentActiveTab = { name: tabName, isAdmin: true };
  document.querySelectorAll("#nav-tabs-admin .tab-btn").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.getElementById(`tab-btn-admin-${tabName}`);
  if (activeBtn) activeBtn.classList.add("active");

  document.querySelectorAll(".sidebar-nav-item").forEach(item => item.classList.remove("active"));
  const sideItem = document.getElementById(`sidebar-item-${tabName}`);
  if (sideItem) sideItem.classList.add("active");

  document.querySelectorAll(".admin-pane").forEach(p => p.style.display = "none");
  document.querySelectorAll(".employee-pane").forEach(p => p.style.display = "none");

  const activePane = document.getElementById(`pane-admin-${tabName}`);
  if (activePane) activePane.style.display = "block";

  if (tabName === "reports") loadAdminReports();
  else if (tabName === "analytics") loadAdminAnalytics();
  else if (tabName === "givens") loadAdminGivens();
  else if (tabName === "topups") loadAdminTopups();
  else if (tabName === "comparison") loadAdminComparison();
  else if (tabName === "users") loadAdminUsers();
  else if (tabName === "cashier") loadAdminCashierTab();
  else if (tabName === "sims") loadAdminSimsTab();
  else if (tabName === "rating") loadLeaderboard("monthly", "admin");
  else if (tabName === "audit") loadAdminAudit();
}

// Xodim va Kassir tablarini almashtirish
function switchEmployeeTab(tabName) {
  currentActiveTab = { name: tabName, isAdmin: false };
  document.querySelectorAll("#nav-tabs-employee .tab-btn").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.getElementById(`tab-btn-${tabName}`);
  if (activeBtn) activeBtn.classList.add("active");

  document.querySelectorAll(".sidebar-nav-item").forEach(item => item.classList.remove("active"));
  const sideItem = document.getElementById(`sidebar-item-${tabName}`);
  if (sideItem) sideItem.classList.add("active");

  document.querySelectorAll(".admin-pane").forEach(p => p.style.display = "none");
  document.querySelectorAll(".employee-pane").forEach(p => p.style.display = "none");

  const activePane = document.getElementById(`pane-${tabName}`);
  if (activePane) activePane.style.display = "block";

  if (tabName === "card-topup") loadCardHistory();
  else if (tabName === "given-amount") loadGivenHistory();
  else if (tabName === "daily-report") loadDailyReportPrefill();
  else if (tabName === "cashier-intake") loadCashierPanel();
  else if (tabName === "cashier-sims") loadCashierSimsTab();
  else if (tabName === "emp-rating") loadLeaderboard("monthly", "emp");
}

// ==========================================
// 1. KARTA TO'LDIRISH OYNASI
// ==========================================

function setupCardTopupInputs() {
  const cardInput = document.getElementById("topup-card-number");
  const holderInput = document.getElementById("topup-card-holder");
  const amountInput = document.getElementById("topup-amount");

  // Karta raqamini har 4 ta raqamdan keyin probel bilan formatlash (16 xonali)
  cardInput.addEventListener("input", (e) => {
    let val = e.target.value.replace(/\D/g, "").slice(0, 16);
    let formatted = val.match(/.{1,4}/g)?.join(" ") || val;
    e.target.value = formatted;
  });

  // Karta egasi: Faqat harflar
  holderInput.addEventListener("input", (e) => {
    e.target.value = e.target.value.replace(/[^a-zA-Zа-яА-ЯёЁ\s']/g, "");
  });

  // Summa: 3 xonadan probel, so'z bilan o'qilishi, +3% va hayratlanish emojisi
  amountInput.addEventListener("input", (e) => {
    let raw = e.target.value.replace(/\D/g, "");
    e.target.value = formatNumberSpaces(raw);
    const amount = parseFormattedNumber(raw);

    const wordsEl = document.getElementById("topup-words-readout");
    const surchargeEl = document.getElementById("topup-surcharge-readout");
    const emojiEl = document.getElementById("topup-emoji-readout");
    const emojiLabel = document.getElementById("topup-emoji-label");

    if (amount > 0) {
      wordsEl.innerText = numberToUzbekWords(amount);
      // 3% ustamani 1000 so'mda yaxlitlash (masalan, 50 000 -> 52 000)
      const surcharge = Math.ceil((amount * 1.03) / 1000) * 1000;
      surchargeEl.innerText = `+3% Ustama bilan: ${formatNumberSpaces(surcharge)} so'm`;

      const emojiData = getAmountEmoji(amount);
      emojiEl.innerText = emojiData.emoji;
      emojiLabel.innerText = emojiData.label;
    } else {
      wordsEl.innerText = "";
      surchargeEl.innerText = "+3% Ustama bilan: 0 so'm";
      emojiEl.innerText = "🙂";
      emojiLabel.innerText = "";
    }
  });
}

async function handleCardTopupSubmit(e) {
  e.preventDefault();
  const cardNumber = document.getElementById("topup-card-number").value.trim();
  const cardHolder = document.getElementById("topup-card-holder").value.trim();
  const amount = parseFormattedNumber(document.getElementById("topup-amount").value);

  if (!cardNumber || cardNumber.replace(/\s/g, "").length !== 16) {
    showToast("Karta raqami to'liq 16 ta raqam bo'lishi kerak!", "danger");
    return;
  }
  if (!cardHolder) {
    showToast("Karta egasini kiriting!", "danger");
    return;
  }
  if (amount < 30000) {
    showToast("Karta to'ldirish uchun eng kam summa: 30 000 so'm!", "danger");
    return;
  }

  try {
    const res = await api("/api/cards/topup", "POST", {
      card_number: cardNumber,
      card_holder: cardHolder,
      amount: amount
    });

    const toastType = (res.data && res.data.is_repeat_today) ? "warning" : "success";
    showToast(res.message, toastType);
    document.getElementById("card-topup-form").reset();
    document.getElementById("topup-words-readout").innerText = "";
    document.getElementById("topup-surcharge-readout").innerText = "+3% Ustama bilan: 0 so'm";
    document.getElementById("topup-emoji-readout").innerText = "🙂";
    loadCardHistory();
  } catch (err) {}
}

async function loadCardHistory() {
  try {
    const res = await api("/api/cards/my-history");
    const tbody = document.getElementById("card-history-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-sub);">Hozircha so'rovlar mavjud emas</td></tr>`;
      return;
    }

    res.data.forEach(item => {
      const statusBadge = formatStatusBadge(item.status);
      const actionBtn = item.status === "PENDING"
        ? `<button type="button" class="btn-reject-topup" onclick="handleRejectMyCardTopup(${item.id}, ${item.transaction_number})" title="So'rovni rad etish (bekor qilish)">❌ Rad etish</button>`
        : `<span style="color: var(--text-sub); font-size: 0.8rem;">—</span>`;

      tbody.innerHTML += `
        <tr>
          <td><b>#${item.transaction_number}</b></td>
          <td>${item.status === 'REJECTED' 
            ? `<span style="color: var(--text-sub);">${item.card_number}</span>` 
            : `<span class="copyable-card" onclick="copyToClipboard('${item.card_number}')">${item.card_number} 📋</span>`}</td>
          <td>${item.card_holder}</td>
          <td><b>${formatNumberSpaces(item.amount)} so'm</b></td>
          <td style="color: var(--accent-success);">${formatNumberSpaces(item.surcharge_amount)} so'm</td>
          <td>${statusBadge}</td>
          <td style="font-size: 0.8rem; color: var(--text-sub);">${formatTashkentDateTime(item.created_at)}</td>
          <td>${actionBtn}</td>
        </tr>
      `;
    });
  } catch (e) {}
}

async function handleRejectMyCardTopup(topupId, txNum) {
  try {
    const res = await api(`/api/cards/${topupId}/reject`, "POST");
    showToast(res.message || "So'rov rad etildi!", "success");
    loadCardHistory();
  } catch (err) {
    showToast(err.message || "Xatolik yuz berdi", "danger");
  }
}

// ==========================================
// 2. BERILGAN SUMMA OYNASI
// ==========================================

function setupGivenAmountInputs() {
  const amountInput = document.getElementById("given-amount-input");

  amountInput.addEventListener("input", (e) => {
    e.target.value = formatNumberSpaces(e.target.value.replace(/\D/g, ""));
  });
}

async function handleGivenAmountSubmit(e) {
  e.preventDefault();
  const amount = parseFormattedNumber(document.getElementById("given-amount-input").value);
  const comment = document.getElementById("given-comment-input").value.trim();

  if (amount <= 0) {
    showToast("Summani to'g'ri kiriting!", "danger");
    return;
  }
  if (!comment) {
    showToast("Izohni kiritish majburiy!", "danger");
    return;
  }

  try {
    const res = await api("/api/given/submit", "POST", { amount, comment });
    showToast(res.message, "success");
    document.getElementById("given-amount-form").reset();
    loadGivenHistory();
  } catch (err) {}
}

async function loadGivenHistory() {
  try {
    const res = await api("/api/given/my-history");
    const tbody = document.getElementById("given-history-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-sub);">Hozircha yozuvlar yo'q</td></tr>`;
      return;
    }

    res.data.forEach(item => {
      const statusBadge = formatStatusBadge(item.status);

      tbody.innerHTML += `
        <tr>
          <td><b>#${item.id}</b></td>
          <td><b>${formatNumberSpaces(item.amount)} so'm</b></td>
          <td>${item.comment}</td>
          <td>${statusBadge}</td>
          <td style="font-size: 0.8rem; color: var(--text-sub);">${formatTashkentDateTime(item.created_at)}</td>
        </tr>
      `;
    });
  } catch (e) {}
}

// ==========================================
// 3. HISOBOT TOPSHIRISH OYNASI
// ==========================================

let prefillData = {
  card_amount: 0,
  given_amount: 0,
  debt_snapshot: 0
};

async function loadDailyReportPrefill() {
  try {
    const res = await api("/api/reports/today-prefill");
    prefillData = res;

    document.getElementById("rep-date-display").innerText = formatDateOnly(res.today);
    document.getElementById("rep-card-amount").value = formatNumberSpaces(res.card_amount);
    
    const initialDebt = res.debt_snapshot || 0;
    const existingDebtPaid = (res.existing_report && res.existing_report.debt_paid) ? res.existing_report.debt_paid : 0;
    const remainingDebt = Math.max(0, initialDebt - existingDebtPaid);
    document.getElementById("rep-debt-snapshot").value = formatNumberSpaces(remainingDebt);
    document.getElementById("rep-given-amount").value = formatNumberSpaces(res.given_amount);

    const debtPaidInput = document.getElementById("rep-debt-paid");
    if (initialDebt <= 0) {
      debtPaidInput.value = "0";
      debtPaidInput.disabled = true;
      debtPaidInput.placeholder = "Qarzdorlik yo'q";
    } else {
      debtPaidInput.disabled = false;
      debtPaidInput.placeholder = "0";
    }

    const banner = document.getElementById("rep-pending-alert");
    if (res.existing_report) {
      banner.style.display = "block";
      if (res.existing_report.status === "APPROVED") {
        banner.className = "alert-card-danger";
        banner.style.borderColor = "var(--accent-success)";
        banner.innerHTML = `✅ <b>Bugungi hisobotingiz tasdiqlangan (Tasdiqlandi).</b>`;
        document.getElementById("btn-submit-report").disabled = true;
      } else if (res.existing_report.status === "REJECTED") {
        banner.className = "alert-card-danger";
        banner.style.borderColor = "var(--accent-danger)";
        banner.innerHTML = `❌ <b>Bugungi hisobotingiz rad etilgan (Rad etildi). Iltimos, ma'lumotlarni tekshirib qayta yuboring.</b>`;
        document.getElementById("btn-submit-report").disabled = false;
      } else {
        banner.className = "alert-card-danger";
        banner.style.borderColor = "var(--accent-warning)";
        banner.innerHTML = `⏳ <b>Bugungi hisobotingiz ko'rib chiqilmoqda (Kutilmoqda).</b>`;
        document.getElementById("btn-submit-report").disabled = false;
      }

      // Mavjud qiymatlarni forma maydonlariga joylash
      document.getElementById("rep-paynet").value = formatNumberSpaces(res.existing_report.paynet);
      document.getElementById("rep-leviy").value = formatNumberSpaces(res.existing_report.leviy);
      document.getElementById("rep-debt-paid").value = formatNumberSpaces(res.existing_report.debt_paid);
      document.getElementById("rep-sim-cards").value = res.existing_report.sim_cards_count;
      document.getElementById("rep-kunlik").value = formatNumberSpaces(res.existing_report.kunlik);
      document.getElementById("rep-terminal").value = formatNumberSpaces(res.existing_report.terminal);
      document.getElementById("rep-skidka").value = formatNumberSpaces(res.existing_report.skidka);
      document.getElementById("rep-xarajat").value = formatNumberSpaces(res.existing_report.xarajat);
      document.getElementById("rep-comment").value = res.existing_report.comment || "";
    } else {
      banner.style.display = "none";
      document.getElementById("btn-submit-report").disabled = false;
    }

    calculateLiveReportFormula();
    loadReportHistory();
  } catch (e) {}
}

function setupReportCalculationListeners() {
  const inputs = [
    "rep-paynet", "rep-leviy", "rep-debt-paid", 
    "rep-kunlik", "rep-terminal", "rep-skidka", "rep-xarajat"
  ];

  inputs.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("input", (e) => {
        e.target.value = formatNumberSpaces(e.target.value.replace(/\D/g, ""));
        calculateLiveReportFormula();
      });
    }
  });
}

function calculateLiveReportFormula() {
  const paynet = parseFormattedNumber(document.getElementById("rep-paynet").value);
  const card = prefillData.card_amount || 0;
  const leviy = parseFormattedNumber(document.getElementById("rep-leviy").value);
  const initialDebt = prefillData.debt_snapshot || 0;
  let debtPaid = parseFormattedNumber(document.getElementById("rep-debt-paid").value);

  // Agar qarz uchun to'lov mavjud qarzdorlikdan oshib ketsa, uni chegara qilish
  if (initialDebt > 0 && debtPaid > initialDebt) {
    debtPaid = initialDebt;
    document.getElementById("rep-debt-paid").value = formatNumberSpaces(debtPaid);
  }

  // Qarzdorlikdan qarz uchun to'lov ayrilib boriladi
  const remainingDebt = Math.max(0, initialDebt - debtPaid);
  document.getElementById("rep-debt-snapshot").value = formatNumberSpaces(remainingDebt);

  const kunlik = parseFormattedNumber(document.getElementById("rep-kunlik").value);
  const terminal = parseFormattedNumber(document.getElementById("rep-terminal").value);
  const given = prefillData.given_amount || 0;
  const skidka = parseFormattedNumber(document.getElementById("rep-skidka").value);
  const xarajat = parseFormattedNumber(document.getElementById("rep-xarajat").value);

  // Qarzdorlik kirimga qo'shilmaydi! Faqat qarz uchun to'lov kiritilsa kirimga qo'shiladi.
  const totalInflow = paynet + card + leviy + debtPaid;
  // Chiqimlar = Kunlik + Terminal + Berildi + Skidka + Xarajat
  const totalOutflow = kunlik + terminal + given + skidka + xarajat;
  // Umumiy Summa = Kirimlar - Chiqimlar
  const netAmount = totalInflow - totalOutflow;

  document.getElementById("rep-total-inflow-display").innerText = `${formatNumberSpaces(totalInflow)} so'm`;
  document.getElementById("rep-total-outflow-display").innerText = `${formatNumberSpaces(totalOutflow)} so'm`;
  document.getElementById("rep-net-amount-display").innerText = `${formatNumberSpaces(netAmount)} so'm`;
}

async function handleReportSubmit(e) {
  e.preventDefault();

  const paynet = parseFormattedNumber(document.getElementById("rep-paynet").value);
  const leviy = parseFormattedNumber(document.getElementById("rep-leviy").value);
  const debtPaid = parseFormattedNumber(document.getElementById("rep-debt-paid").value);
  const simCards = parseInt(document.getElementById("rep-sim-cards").value) || 0;
  const kunlik = parseFormattedNumber(document.getElementById("rep-kunlik").value);
  const terminal = parseFormattedNumber(document.getElementById("rep-terminal").value);
  const skidka = parseFormattedNumber(document.getElementById("rep-skidka").value);
  const xarajat = parseFormattedNumber(document.getElementById("rep-xarajat").value);
  const comment = document.getElementById("rep-comment").value.trim();

  try {
    const res = await api("/api/reports/submit", "POST", {
      paynet,
      leviy,
      debt_paid: debtPaid,
      sim_cards_count: simCards,
      kunlik,
      terminal,
      skidka,
      xarajat,
      comment
    });

    showToast(res.message, "success");
    loadDailyReportPrefill();
  } catch (err) {}
}

async function loadReportHistory() {
  try {
    const res = await api("/api/reports/my-history");
    const tbody = document.getElementById("report-history-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-sub);">Hozircha topshirilgan hisobotlar yo'q</td></tr>`;
      return;
    }

    res.data.forEach(item => {
      const statusBadge = formatStatusBadge(item.status);

      tbody.innerHTML += `
        <tr>
          <td><b>${formatDateOnly(item.report_date)}</b></td>
          <td>${formatNumberSpaces(item.total_inflow)} so'm</td>
          <td>${formatNumberSpaces(item.total_outflow)} so'm</td>
          <td style="font-weight: 800; color: var(--accent-success);">${formatNumberSpaces(item.net_amount)} so'm</td>
          <td><b>${item.sim_cards_count} dona</b></td>
          <td>${statusBadge}</td>
          <td style="font-size: 0.85rem; color: var(--text-sub);">${item.comment || '-'}</td>
        </tr>
      `;
    });
  } catch (e) {}
}

// ==========================================
// 4. REYTING & LIDERLAR JADVALI
// ==========================================

async function loadLeaderboard(period = "monthly") {
  document.getElementById("btn-rating-monthly").className = period === "monthly" ? "btn-primary" : "btn-logout";
  document.getElementById("btn-rating-overall").className = period === "overall" ? "btn-primary" : "btn-logout";

  try {
    const res = await api(`/api/rating/leaderboard?period=${period}`);
    const tbody = document.getElementById("rating-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-sub);">Hozircha tasdiqlangan hisobotlar mavjud emas</td></tr>`;
      return;
    }

    res.data.forEach(item => {
      tbody.innerHTML += `
        <tr>
          <td><b style="font-size: 1.1rem;">${item.badge}</b></td>
          <td><b>${item.employee_name}</b></td>
          <td>${formatNumberSpaces(item.total_sum)} so'm</td>
          <td>${item.money_points} ball</td>
          <td>${item.total_sim_cards} dona (${item.sim_points} ball)</td>
          <td><b style="font-size: 1.15rem; color: #a5b4fc;">${item.total_score} ball</b></td>
          <td>${item.reports_count} ta kun</td>
        </tr>
      `;
    });
  } catch (e) {}
}

// ==========================================
// 5. KASSIR PANELI
// ==========================================

async function loadCashierPanel() {
  try {
    await loadCashierEmployees();
    setupCashierInputs();
    calculateCashierLiveTotal();
    await loadCashierMyHandovers();
  } catch (e) {}
}

async function loadCashierEmployees() {
  try {
    const res = await api("/api/cashier/employees");
    const select = document.getElementById("cashier-employee-select");
    if (!select) return;
    select.innerHTML = `<option value="">-- Xodimni tanlang --</option>`;
    const employees = (res.data || []).filter(emp => emp.role !== "ADMIN");
    if (employees.length === 0) {
      select.innerHTML += `<option value="" disabled>Barcha xodimlar bugungi kassani topshirib bo'lgan</option>`;
      return;
    }
    employees.forEach(emp => {
      const roleText = emp.role === "CASHIER" ? "Kassir" : "Xodim";
      select.innerHTML += `<option value="${emp.id}">${emp.full_name} (${roleText})</option>`;
    });
  } catch (e) {}
}

function setupCashierInputs() {
  const uzsInput = document.getElementById("cashier-amount-uzs");
  const usdInput = document.getElementById("cashier-amount-usd");

  [uzsInput, usdInput].forEach(inp => {
    if (inp && !inp.dataset.listenerAttached) {
      inp.dataset.listenerAttached = "true";
      inp.addEventListener("input", (e) => {
        e.target.value = formatNumberSpaces(e.target.value.replace(/\D/g, ""));
        calculateCashierLiveTotal();
      });
    }
  });
}

function calculateCashierLiveTotal() {
  const uzs = parseFormattedNumber(document.getElementById("cashier-amount-uzs")?.value) || 0;
  const usd = parseFormattedNumber(document.getElementById("cashier-amount-usd")?.value) || 0;
  const rate = currentUsdRate || 12000;

  const total = uzs + (usd * rate);
  const totalDisplay = document.getElementById("cashier-total-equivalent-display");
  const formulaDisplay = document.getElementById("cashier-formula-breakdown");

  if (totalDisplay) {
    totalDisplay.innerText = `${formatNumberSpaces(total)} so'm`;
  }
  if (formulaDisplay) {
    if (usd > 0) {
      formulaDisplay.innerText = `(${formatNumberSpaces(uzs)} so'm + ${formatNumberSpaces(usd)} $ * ${formatNumberSpaces(rate)} so'm)`;
    } else {
      formulaDisplay.innerText = `${formatNumberSpaces(uzs)} so'm`;
    }
  }
}

async function handleCashierHandoverSubmit(e) {
  e.preventDefault();
  const empId = document.getElementById("cashier-employee-select").value;
  const uzs = parseFormattedNumber(document.getElementById("cashier-amount-uzs").value) || 0;
  const usd = parseFormattedNumber(document.getElementById("cashier-amount-usd").value) || 0;
  const rate = currentUsdRate || 12000;

  if (!empId) {
    showToast("Iltimos, xodimni tanlang!", "danger");
    return;
  }
  if (uzs <= 0 && usd <= 0) {
    showToast("Iltimos, so'm yoki dollar summasini kiriting!", "danger");
    return;
  }

  try {
    const res = await api("/api/cashier/handover", "POST", {
      employee_id: parseInt(empId),
      amount_uzs: uzs,
      amount_usd: usd,
      usd_rate: rate
    });

    showToast(res.message, "success");
    document.getElementById("cashier-amount-uzs").value = "";
    document.getElementById("cashier-amount-usd").value = "";
    calculateCashierLiveTotal();
    await loadCashierEmployees();
    await loadCashierMyHandovers();
  } catch (err) {}
}

async function loadCashierMyHandovers() {
  try {
    const res = await api("/api/cashier/my-handovers");
    const tbody = document.getElementById("cashier-my-handovers-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-sub); padding: 1rem;">Bugun hali qabul qilingan summalar yo'q</td></tr>`;
      return;
    }

    res.data.forEach(item => {
      const cashierBadge = item.cashier_name ? `<span class="badge badge-primary">${item.cashier_name}</span>` : `<span class="badge badge-primary">Kassir</span>`;
      tbody.innerHTML += `
        <tr>
          <td><b>${item.employee_name}</b></td>
          <td>${cashierBadge}</td>
          <td style="color: #60a5fa; font-weight: 600;">${formatNumberSpaces(item.amount_uzs)} so'm</td>
          <td style="color: #34d399; font-weight: 700;">${formatNumberSpaces(item.amount_usd)} $</td>
          <td><b style="color: var(--accent-success); font-size: 1.05rem;">${formatNumberSpaces(item.amount)} so'm</b></td>
          <td>${formatDateOnly(item.handover_date)}</td>
          <td style="font-size: 0.8rem; color: var(--text-sub);">${formatTashkentDateTime(item.created_at)}</td>
        </tr>
      `;
    });
  } catch (e) {}
}

// ==========================================
// 6. RAHBAR (ADMIN) BOSHQARUV PANELI
// ==========================================

// Admin 1: Hisobotlarni tasdiqlash & Saralash
let adminReportsCache = [];

// Sana oralig'i filtri holati
let adminReportDateFilter = {
  startDate: null, // "YYYY-MM-DD"
  endDate: null,   // "YYYY-MM-DD"
  label: "Barcha sanalar"
};

// Kalendar modali ichki holati
let calModalState = {
  viewYear: new Date(Date.now() + 5 * 3600 * 1000).getFullYear(),
  viewMonth: new Date(Date.now() + 5 * 3600 * 1000).getMonth(),
  startDate: null,
  endDate: null,
  pickingStep: "start",
  activePreset: "all"
};

const uzbekMonths = [
  "Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun",
  "Iyul", "Avgust", "Sentabr", "Oktyabr", "Noyabr", "Dekabr"
];

function getTashkentTodayIso(offsetDays = 0) {
  const d = new Date(Date.now() + 5 * 3600 * 1000 + offsetDays * 86400 * 1000);
  return d.toISOString().slice(0, 10);
}

function updateAdminReportsDateDisplay() {
  const displayEl = document.getElementById("admin-reports-date-display");
  if (displayEl) {
    displayEl.textContent = adminReportDateFilter.label || "Barcha sanalar";
  }
}

function setAdminReportsTodayFilter() {
  const today = getTashkentTodayIso();
  adminReportDateFilter = {
    startDate: today,
    endDate: today,
    label: `Bugun (${formatDateOnly(today)})`
  };
  updateAdminReportsDateDisplay();
  loadAdminReports();
}

function resetAdminReportsFilter() {
  adminReportDateFilter = {
    startDate: null,
    endDate: null,
    label: "Barcha sanalar"
  };
  updateAdminReportsDateDisplay();
  loadAdminReports();
}

// Alohida Kalendar Modalini ochish
function openDateRangeModal() {
  const modal = document.getElementById("date-range-modal");
  if (!modal) return;

  // Hozirgi filtr holatini yuklash
  calModalState.startDate = adminReportDateFilter.startDate;
  calModalState.endDate = adminReportDateFilter.endDate;
  calModalState.pickingStep = "start";

  // Kalendarni boshlanish sanasi yoki bugungi oyga moslash
  const baseDateStr = calModalState.startDate || getTashkentTodayIso();
  const parts = baseDateStr.split("-");
  if (parts.length === 3) {
    calModalState.viewYear = parseInt(parts[0], 10);
    calModalState.viewMonth = parseInt(parts[1], 10) - 1;
  }

  // Inputlarni to'ldirish
  const startInp = document.getElementById("cal-modal-start-date");
  const endInp = document.getElementById("cal-modal-end-date");
  if (startInp) startInp.value = calModalState.startDate || "";
  if (endInp) endInp.value = calModalState.endDate || "";

  renderCustomCalendarWidget();
  updateCalModalSummaryText();
  modal.style.display = "flex";
}

function closeDateRangeModal() {
  const modal = document.getElementById("date-range-modal");
  if (modal) modal.style.display = "none";
}

function handleDateModalOverlayClick(e) {
  if (e.target && e.target.id === "date-range-modal") {
    closeDateRangeModal();
  }
}

// Oylarni oldinga/orqaga almashtirish
function navigateCalendarMonth(direction) {
  calModalState.viewMonth += direction;
  if (calModalState.viewMonth < 0) {
    calModalState.viewMonth = 11;
    calModalState.viewYear -= 1;
  } else if (calModalState.viewMonth > 11) {
    calModalState.viewMonth = 0;
    calModalState.viewYear += 1;
  }
  renderCustomCalendarWidget();
}

// Tezkor davr tugmalari (Bugun, Kecha, 7 kun, 30 kun, Shu oy, Barchasi)
function applyDatePreset(preset) {
  calModalState.activePreset = preset;
  document.querySelectorAll(".date-preset-btn").forEach(btn => {
    btn.classList.toggle("active", btn.id === `preset-${preset}`);
  });

  const todayStr = getTashkentTodayIso();

  if (preset === "today") {
    calModalState.startDate = todayStr;
    calModalState.endDate = todayStr;
  } else if (preset === "yesterday") {
    const yestStr = getTashkentTodayIso(-1);
    calModalState.startDate = yestStr;
    calModalState.endDate = yestStr;
  } else if (preset === "7d") {
    calModalState.startDate = getTashkentTodayIso(-6);
    calModalState.endDate = todayStr;
  } else if (preset === "30d") {
    calModalState.startDate = getTashkentTodayIso(-29);
    calModalState.endDate = todayStr;
  } else if (preset === "this_month") {
    const parts = todayStr.split("-");
    calModalState.startDate = `${parts[0]}-${parts[1]}-01`;
    calModalState.endDate = todayStr;
  } else if (preset === "all") {
    calModalState.startDate = null;
    calModalState.endDate = null;
  }

  // Agar sana tanlangan bo'lsa, kalendar ko'rinishini o'sha oyga o'tkazish
  if (calModalState.startDate) {
    const p = calModalState.startDate.split("-");
    calModalState.viewYear = parseInt(p[0], 10);
    calModalState.viewMonth = parseInt(p[1], 10) - 1;
  }

  // Inputlarni sinxronlash
  const startInp = document.getElementById("cal-modal-start-date");
  const endInp = document.getElementById("cal-modal-end-date");
  if (startInp) startInp.value = calModalState.startDate || "";
  if (endInp) endInp.value = calModalState.endDate || "";

  calModalState.pickingStep = "start";
  renderCustomCalendarWidget();
  updateCalModalSummaryText();
}

// Qo'lda sana kiritilganda sinxronlash
function onModalDateInputChange() {
  const startInp = document.getElementById("cal-modal-start-date");
  const endInp = document.getElementById("cal-modal-end-date");

  let s = startInp ? startInp.value : "";
  let e = endInp ? endInp.value : "";

  if (s && e && s > e) {
    const tmp = s; s = e; e = tmp;
    if (startInp) startInp.value = s;
    if (endInp) endInp.value = e;
  }

  calModalState.startDate = s || null;
  calModalState.endDate = e || null;
  calModalState.activePreset = null;
  document.querySelectorAll(".date-preset-btn").forEach(btn => btn.classList.remove("active"));

  if (calModalState.startDate) {
    const p = calModalState.startDate.split("-");
    calModalState.viewYear = parseInt(p[0], 10);
    calModalState.viewMonth = parseInt(p[1], 10) - 1;
  }

  renderCustomCalendarWidget();
  updateCalModalSummaryText();
}

// Kalendar katakchasi bosilganda
function handleCalendarDayClick(dateStr) {
  calModalState.activePreset = null;
  document.querySelectorAll(".date-preset-btn").forEach(btn => btn.classList.remove("active"));

  if (calModalState.pickingStep === "start" || (calModalState.startDate && calModalState.endDate)) {
    calModalState.startDate = dateStr;
    calModalState.endDate = null;
    calModalState.pickingStep = "end";
  } else {
    // 2-chi marta bosildi: tugash sanasi
    if (dateStr < calModalState.startDate) {
      calModalState.endDate = calModalState.startDate;
      calModalState.startDate = dateStr;
    } else {
      calModalState.endDate = dateStr;
    }
    calModalState.pickingStep = "start";
  }

  const startInp = document.getElementById("cal-modal-start-date");
  const endInp = document.getElementById("cal-modal-end-date");
  if (startInp) startInp.value = calModalState.startDate || "";
  if (endInp) endInp.value = calModalState.endDate || "";

  renderCustomCalendarWidget();
  updateCalModalSummaryText();
}

// Kalendar katakchalarini chizish
function renderCustomCalendarWidget() {
  const container = document.getElementById("cal-days-container");
  const labelEl = document.getElementById("cal-month-year-text");
  if (!container || !labelEl) return;

  const y = calModalState.viewYear;
  const m = calModalState.viewMonth;
  labelEl.textContent = `${uzbekMonths[m]} ${y}`;

  const firstDayObj = new Date(y, m, 1);
  let firstDayIndex = firstDayObj.getDay(); // 0 is Sun, 1 is Mon...
  if (firstDayIndex === 0) firstDayIndex = 7; // Mon=1, Sun=7

  const daysInMonth = new Date(y, m + 1, 0).getDate();
  const prevMonthDays = new Date(y, m, 0).getDate();
  const todayIso = getTashkentTodayIso();

  let s = calModalState.startDate;
  let e = calModalState.endDate;
  if (s && e && s > e) {
    const tmp = s; s = e; e = tmp;
  }

  let html = "";

  // Oldingi oydan to'ldiruvchi kunlar
  for (let i = firstDayIndex - 1; i >= 1; i--) {
    const dNum = prevMonthDays - i + 1;
    html += `<div class="cal-day-cell empty-day">${dNum}</div>`;
  }

  // Joriy oy kunlari
  for (let day = 1; day <= daysInMonth; day++) {
    const mm = String(m + 1).padStart(2, "0");
    const dd = String(day).padStart(2, "0");
    const dateStr = `${y}-${mm}-${dd}`;

    let classes = ["cal-day-cell"];
    if (dateStr === todayIso) classes.push("is-today");

    if (s && dateStr === s) classes.push("is-start");
    if (e && dateStr === e) classes.push("is-end");
    if (s && e && dateStr > s && dateStr < e) classes.push("in-range");

    html += `<div class="${classes.join(' ')}" onclick="handleCalendarDayClick('${dateStr}')">${day}</div>`;
  }

  // Keyingi oydan to'ldiruvchi kunlar
  const totalCells = (firstDayIndex - 1) + daysInMonth;
  const trailingCount = (7 - (totalCells % 7)) % 7;
  for (let t = 1; t <= trailingCount; t++) {
    html += `<div class="cal-day-cell empty-day">${t}</div>`;
  }

  container.innerHTML = html;
}

// Xulosa matnini yangilash
function updateCalModalSummaryText() {
  const summaryEl = document.getElementById("cal-modal-summary-text");
  if (!summaryEl) return;

  const s = calModalState.startDate;
  const e = calModalState.endDate;

  if (s && e) {
    if (s === e) {
      summaryEl.innerHTML = `<span>📅</span> Tanlandi: <b>${formatDateOnly(s)}</b> (1 kun)`;
    } else {
      const msDiff = new Date(e) - new Date(s);
      const daysCount = Math.round(msDiff / (1000 * 3600 * 24)) + 1;
      summaryEl.innerHTML = `<span>📅</span> Tanlandi: <b>${formatDateOnly(s)}</b> dan <b>${formatDateOnly(e)}</b> gacha (${daysCount} kun)`;
    }
  } else if (s) {
    summaryEl.innerHTML = `<span>📅</span> Boshlanish sanasi: <b>${formatDateOnly(s)}</b> (Tugash sanasini tanlang)`;
  } else if (e) {
    summaryEl.innerHTML = `<span>📅</span> Tugash sanasi: <b>${formatDateOnly(e)}</b>`;
  } else {
    summaryEl.innerHTML = `<span>📅</span> Oraliq tanlanmagan (Barcha sanalar ko'rsatiladi)`;
  }
}

// Tozalash
function clearDateRangeModalFilter() {
  calModalState.startDate = null;
  calModalState.endDate = null;
  calModalState.activePreset = "all";
  calModalState.pickingStep = "start";

  const startInp = document.getElementById("cal-modal-start-date");
  const endInp = document.getElementById("cal-modal-end-date");
  if (startInp) startInp.value = "";
  if (endInp) endInp.value = "";

  document.querySelectorAll(".date-preset-btn").forEach(btn => {
    btn.classList.toggle("active", btn.id === "preset-all");
  });

  renderCustomCalendarWidget();
  updateCalModalSummaryText();
}

// Modaldan filtrni qabul qilish
function applyDateRangeFilterFromModal() {
  let s = calModalState.startDate;
  let e = calModalState.endDate;

  if (s && e && s > e) {
    const tmp = s; s = e; e = tmp;
  }

  adminReportDateFilter.startDate = s;
  adminReportDateFilter.endDate = e;

  if (s && e) {
    if (s === e) {
      adminReportDateFilter.label = formatDateOnly(s);
    } else {
      adminReportDateFilter.label = `${formatDateOnly(s)} — ${formatDateOnly(e)}`;
    }
  } else if (s) {
    adminReportDateFilter.label = `${formatDateOnly(s)} dan boshlab`;
  } else if (e) {
    adminReportDateFilter.label = `${formatDateOnly(e)} gacha`;
  } else {
    adminReportDateFilter.label = "Barcha sanalar";
  }

  updateAdminReportsDateDisplay();
  closeDateRangeModal();
  loadAdminReports();
}

// ==========================================
// Savdo Monitoringi & Diagrammalar (Analytics)
// ==========================================

function changeAnalyticsPeriod(period) {
  currentAnalyticsPeriod = period;
  document.querySelectorAll("#analytics-period-buttons .analytics-period-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-period") === period);
  });
  loadAdminAnalytics(period);
}

function setChartMetric(metric) {
  currentChartMetric = metric;
  document.querySelectorAll("#chart-metric-buttons .chart-metric-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-metric") === metric);
  });
  if (analyticsDataCache) {
    renderMainAnalyticsChart(analyticsDataCache.timeline);
  }
}

async function loadAdminAnalytics(period = currentAnalyticsPeriod) {
  currentAnalyticsPeriod = period;
  try {
    const res = await api(`/api/admin/analytics/monitoring?period=${period}`);
    if (!res || !res.data) return;

    analyticsDataCache = res.data;
    const { summary, timeline, operators } = res.data;

    // 1. KPI kartochkalarini yangilash
    updateAnalyticsKpis(summary);

    // 2. Diagrammalarni chizish
    renderAllAnalyticsCharts();

    // 3. Kunlik jadvalni to'ldirish
    renderAnalyticsTable(timeline);

  } catch (err) {
    console.error("Savdo monitoringini yuklashda xatolik:", err);
  }
}

function updateAnalyticsKpis(s) {
  // 1. Topshirilgan summa
  const revEl = document.getElementById("kpi-revenue-val");
  if (revEl) revEl.innerText = `${formatNumberSpaces(s.total_submitted_amount)} so'm`;
  setTrendBadge("kpi-revenue-trend", s.submitted_growth_pct);

  // 2. Sim-kartalar
  const simEl = document.getElementById("kpi-sims-val");
  if (simEl) simEl.innerText = `${s.total_sim_cards} dona`;
  setTrendBadge("kpi-sims-trend", s.sim_growth_pct);

  // 3. Karta to'ldirish
  const cardEl = document.getElementById("kpi-cards-val");
  if (cardEl) cardEl.innerText = `${formatNumberSpaces(s.total_card_topup_amount)} so'm`;
  setTrendBadge("kpi-cards-trend", s.card_growth_pct);
  const cardSub = document.getElementById("kpi-cards-sub");
  if (cardSub) cardSub.innerText = `${s.total_card_topup_count} ta tasdiqlangan to'ldirish`;

  // 4. Sof kassa (Net) & Kunlik o'rtacha
  const netEl = document.getElementById("kpi-net-val");
  if (netEl) netEl.innerText = `${formatNumberSpaces(s.total_net_amount)} so'm`;
  setTrendBadge("kpi-net-trend", s.net_growth_pct);
  const netSub = document.getElementById("kpi-net-sub");
  if (netSub) netSub.innerText = `O'rtacha kunlik: ~${formatNumberSpaces(s.avg_daily_submitted)} so'm`;
}

function setTrendBadge(badgeId, pct) {
  const el = document.getElementById(badgeId);
  if (!el) return;
  const num = parseFloat(pct) || 0;
  if (num > 0) {
    el.className = "kpi-badge trend-up";
    el.innerHTML = `↗️ +${num}%`;
  } else if (num < 0) {
    el.className = "kpi-badge trend-down";
    el.innerHTML = `↘️ ${num}%`;
  } else {
    el.className = "kpi-badge trend-flat";
    el.innerHTML = `➡️ 0%`;
  }
}

function renderAllAnalyticsCharts() {
  if (!analyticsDataCache) return;
  renderMainAnalyticsChart(analyticsDataCache.timeline);
  renderGrowthChart(analyticsDataCache.timeline);
  renderOperatorChart(analyticsDataCache.operators);
}

function getChartThemeColors() {
  const isLight = document.body.classList.contains("theme-light");
  return {
    isLight,
    textColor: isLight ? "#475569" : "#9ca3af",
    gridColor: isLight ? "rgba(0, 0, 0, 0.06)" : "rgba(255, 255, 255, 0.06)",
    tooltipBg: isLight ? "rgba(255, 255, 255, 0.95)" : "rgba(17, 24, 39, 0.95)",
    tooltipText: isLight ? "#0f172a" : "#f9fafb",
    tooltipBorder: isLight ? "#cbd5e1" : "rgba(255, 255, 255, 0.12)"
  };
}

function renderMainAnalyticsChart(timeline) {
  const canvas = document.getElementById("monitoring-main-chart");
  if (!canvas) return;

  const labels = timeline.map(t => `${t.short_date} (${t.weekday})`);
  const subData = timeline.map(t => t.submitted_amount);
  const netData = timeline.map(t => t.net_amount);
  const simData = timeline.map(t => t.sim_cards_sold);
  const cardData = timeline.map(t => t.card_topup_amount);

  const tc = getChartThemeColors();

  if (typeof Chart !== "undefined") {
    if (mainChartInstance) mainChartInstance.destroy();

    const datasets = [];

    if (currentChartMetric === "all" || currentChartMetric === "submitted") {
      datasets.push({
        label: "💰 Topshirilgan summa (so'm)",
        data: subData,
        borderColor: "#6366f1",
        backgroundColor: "rgba(99, 102, 241, 0.18)",
        fill: true,
        tension: 0.35,
        yAxisID: "yLeft",
        pointRadius: 4,
        pointHoverRadius: 6
      });
      if (currentChartMetric === "submitted") {
        datasets.push({
          label: "⚖️ Sof kassa (Net)",
          data: netData,
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.1)",
          fill: true,
          tension: 0.35,
          yAxisID: "yLeft",
          pointRadius: 4,
          pointHoverRadius: 6
        });
      }
    }

    if (currentChartMetric === "all" || currentChartMetric === "cards") {
      datasets.push({
        label: "💳 Karta to'ldirish (+3%)",
        data: cardData,
        borderColor: "#06b6d4",
        backgroundColor: "rgba(6, 182, 212, 0.14)",
        fill: currentChartMetric === "cards",
        borderDash: currentChartMetric === "all" ? [5, 5] : [],
        tension: 0.35,
        yAxisID: "yLeft",
        pointRadius: 4,
        pointHoverRadius: 6
      });
    }

    if (currentChartMetric === "all" || currentChartMetric === "sims") {
      datasets.push({
        label: "📱 Sotilgan sim-karta (dona)",
        data: simData,
        borderColor: "#f59e0b",
        backgroundColor: currentChartMetric === "sims" ? "rgba(245, 158, 11, 0.45)" : "rgba(245, 158, 11, 0.8)",
        type: currentChartMetric === "sims" ? "bar" : "line",
        borderRadius: 4,
        tension: 0.3,
        yAxisID: currentChartMetric === "all" ? "yRight" : "yLeft",
        pointRadius: 4,
        pointHoverRadius: 6
      });
    }

    const scales = {
      x: {
        grid: { color: tc.gridColor, display: false },
        ticks: { 
          color: tc.textColor, 
          font: { size: 11, weight: 500 },
          maxRotation: 0,
          minRotation: 0,
          autoSkip: true,
          maxTicksLimit: 7
        }
      },
      yLeft: {
        type: "linear",
        position: "left",
        grid: { color: tc.gridColor },
        ticks: {
          color: tc.textColor,
          font: { size: 11 },
          callback: (v) => formatNumberShort(v)
        }
      }
    };

    if (currentChartMetric === "all") {
      scales.yRight = {
        type: "linear",
        position: "right",
        grid: { drawOnChartArea: false },
        ticks: {
          color: "#f59e0b",
          font: { size: 11 },
          callback: (v) => `${v} ta`
        }
      };
    }

    mainChartInstance = new Chart(canvas, {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "top",
            labels: { color: tc.textColor, font: { size: 12, weight: 600 } }
          },
          tooltip: {
            backgroundColor: tc.tooltipBg,
            titleColor: tc.tooltipText,
            bodyColor: tc.tooltipText,
            borderColor: tc.tooltipBorder,
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label: (ctx) => {
                const val = ctx.parsed.y;
                if (ctx.dataset.label.includes("dona") || ctx.dataset.label.includes("sim-karta")) {
                  return ` ${ctx.dataset.label}: ${val} dona`;
                }
                return ` ${ctx.dataset.label}: ${formatNumberSpaces(val)} so'm`;
              }
            }
          }
        },
        scales
      }
    });
  } else {
    renderCanvasFallback(canvas, timeline);
  }
}

function renderGrowthChart(timeline) {
  const canvas = document.getElementById("monitoring-growth-chart");
  if (!canvas) return;

  const labels = timeline.map(t => t.short_date);
  const changes = timeline.map(t => t.day_change_pct);
  const tc = getChartThemeColors();

  if (typeof Chart !== "undefined") {
    if (growthChartInstance) growthChartInstance.destroy();

    const bgColors = changes.map(c => c >= 0 ? "rgba(16, 185, 129, 0.75)" : "rgba(239, 68, 68, 0.75)");
    const borderColors = changes.map(c => c >= 0 ? "#10b981" : "#ef4444");

    growthChartInstance = new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Kunlik o'sish / pasayish (%)",
          data: changes,
          backgroundColor: bgColors,
          borderColor: borderColors,
          borderWidth: 1,
          borderRadius: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: tc.tooltipBg,
            titleColor: tc.tooltipText,
            bodyColor: tc.tooltipText,
            borderColor: tc.tooltipBorder,
            borderWidth: 1,
            callbacks: {
              label: (ctx) => ` O'zgarish: ${ctx.parsed.y > 0 ? '+' : ''}${ctx.parsed.y}%`
            }
          }
        },
        scales: {
          x: {
            grid: { color: tc.gridColor, display: false },
            ticks: { 
              color: tc.textColor, 
              font: { size: 10 },
              maxRotation: 0,
              minRotation: 0,
              autoSkip: true,
              maxTicksLimit: 8
            }
          },
          y: {
            grid: { color: tc.gridColor },
            ticks: {
              color: tc.textColor,
              font: { size: 10 },
              callback: (v) => `${v}%`
            }
          }
        }
      }
    });
  }
}

function renderOperatorChart(operators) {
  const canvas = document.getElementById("monitoring-operator-chart");
  if (!canvas) return;

  const labels = (operators && operators.length > 0) ? operators.map(o => o.operator_type) : [];
  const data = (operators && operators.length > 0) ? operators.map(o => o.count) : [];
  const tc = getChartThemeColors();

  const opColors = {
    "Uzmobile": "#06b6d4",
    "Beeline": "#fbbf24",
    "Ucell": "#c084fc",
    "Mobiuz": "#f87171",
    "Perfectum": "#60a5fa"
  };
  const bgColors = labels.map(l => opColors[l] || "#818cf8");

  if (typeof Chart !== "undefined") {
    if (operatorChartInstance) operatorChartInstance.destroy();

    operatorChartInstance = new Chart(canvas, {
      type: "doughnut",
      data: {
        labels: labels.length > 0 ? labels : ["Ma'lumot yo'q"],
        datasets: [{
          data: data.length > 0 ? data : [1],
          backgroundColor: data.length > 0 ? bgColors : ["#475569"],
          borderWidth: 2,
          borderColor: tc.isLight ? "#ffffff" : "#111827"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "right",
            labels: { color: tc.textColor, font: { size: 11, weight: 600 } }
          },
          tooltip: {
            backgroundColor: tc.tooltipBg,
            titleColor: tc.tooltipText,
            bodyColor: tc.tooltipText,
            borderColor: tc.tooltipBorder,
            borderWidth: 1,
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.raw} dona`
            }
          }
        }
      }
    });
  }
}

function renderAnalyticsTable(timeline) {
  const tbody = document.getElementById("analytics-table-tbody");
  if (!tbody) return;

  if (!timeline || timeline.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-sub); padding: 1.5rem;">Ma'lumotlar mavjud emas</td></tr>`;
    return;
  }

  // Sanalarni eng yangidan eskiga qarab ko'rsatamiz
  const reversed = [...timeline].reverse();

  tbody.innerHTML = reversed.map(t => {
    const changeBadge = t.day_change_pct > 0 
      ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #34d399; font-weight: 700;">↗️ +${t.day_change_pct}%</span>`
      : t.day_change_pct < 0
      ? `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; font-weight: 700;">↘️ ${t.day_change_pct}%</span>`
      : `<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: #94a3b8;">➡️ 0%</span>`;

    return `
      <tr>
        <td><b>${formatDateOnly(t.date)}</b> <span style="font-size: 0.75rem; color: var(--text-sub);">(${t.weekday})</span></td>
        <td style="font-weight: 700; color: #a5b4fc;">${formatNumberSpaces(t.submitted_amount)} so'm</td>
        <td style="font-weight: 700; color: #34d399;">${formatNumberSpaces(t.net_amount)} so'm</td>
        <td><span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; font-weight: 700;">📱 ${t.sim_cards_sold} dona</span></td>
        <td style="font-weight: 600; color: #22d3ee;">${formatNumberSpaces(t.card_topup_amount)} so'm</td>
        <td>${t.card_topup_count} ta</td>
        <td>${changeBadge}</td>
      </tr>
    `;
  }).join("");
}

function formatNumberShort(num) {
  if (num >= 1000000000) return (num / 1000000000).toFixed(1) + " mlrd";
  if (num >= 1000000) return (num / 1000000).toFixed(1) + " mln";
  if (num >= 1000) return (num / 1000).toFixed(0) + " ming";
  return num;
}

function renderCanvasFallback(canvas, timeline) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const w = canvas.width = canvas.parentElement.clientWidth || 600;
  const h = canvas.height = canvas.parentElement.clientHeight || 300;
  ctx.clearRect(0, 0, w, h);

  const tc = getChartThemeColors();
  ctx.fillStyle = tc.textColor;
  ctx.font = "12px sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("📊 Savdo monitoringi diagrammasi (Faol)", w / 2, 25);

  const maxVal = Math.max(...timeline.map(t => t.submitted_amount), 1);
  const stepX = (w - 80) / Math.max(1, timeline.length - 1);

  ctx.beginPath();
  ctx.strokeStyle = "#6366f1";
  ctx.lineWidth = 2.5;

  timeline.forEach((t, i) => {
    const x = 50 + i * stepX;
    const y = h - 40 - ((t.submitted_amount / maxVal) * (h - 90));
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  timeline.forEach((t, i) => {
    const x = 50 + i * stepX;
    const y = h - 40 - ((t.submitted_amount / maxVal) * (h - 90));
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#6366f1";
    ctx.fill();
    ctx.fillStyle = tc.textColor;
    ctx.fillText(t.short_date, x, h - 15);
  });
}

async function loadAdminReports() {
  try {
    const { startDate, endDate, label } = adminReportDateFilter;
    let query = "";
    if (startDate && endDate) {
      if (startDate === endDate) {
        query = `?date=${encodeURIComponent(startDate)}`;
      } else {
        query = `?start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}`;
      }
    } else if (startDate) {
      query = `?start_date=${encodeURIComponent(startDate)}`;
    } else if (endDate) {
      query = `?end_date=${encodeURIComponent(endDate)}`;
    }

    const res = await api(`/api/reports/all${query}`);
    const tbody = document.getElementById("admin-reports-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      const emptyMsg = (startDate || endDate)
        ? `📅 <b>${label || 'Tanlangan sana'}</b> oralig'ida topshirilgan hisobotlar topilmadi`
        : "Hozircha hisobotlar mavjud emas";
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-sub); padding: 1.5rem;">${emptyMsg}</td></tr>`;
      adminReportsCache = [];
      return;
    }

    adminReportsCache = res.data;

    res.data.forEach(r => {
      const actions = r.status === "PENDING" ? `
        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
          <button class="btn-success" style="padding: 0.35rem 0.65rem; font-size: 0.8rem;" onclick="updateReportStatus(${r.id}, 'APPROVED')">✅ Tasdiqlash</button>
          <button class="btn-danger" style="padding: 0.35rem 0.65rem; font-size: 0.8rem;" onclick="updateReportStatus(${r.id}, 'REJECTED')">❌ Rad etish</button>
        </div>
      ` : formatStatusBadge(r.status);

      const effectiveDebt = Math.max(0, (r.debt_snapshot || 0) - (r.debt_paid || 0));

      tbody.innerHTML += `
        <tr>
          <td><b>${formatDateOnly(r.report_date)}</b></td>
          <td><b>${r.employee_name}</b></td>
          <td>
            <div class="val-inflow">${formatNumberSpaces(r.total_inflow)} so'm</div>
            <div class="val-sub">
              Paynet: ${formatNumberSpaces(r.paynet)} | Karta: ${formatNumberSpaces(r.card_amount)} | Lev: ${formatNumberSpaces(r.leviy)}${r.debt_paid > 0 ? ` | Qarz to'lov: ${formatNumberSpaces(r.debt_paid)}` : ''}
            </div>
          </td>
          <td>
            <div class="val-outflow">${formatNumberSpaces(r.total_outflow)} so'm</div>
            <div class="val-sub">
              Kunlik: ${formatNumberSpaces(r.kunlik)} | Term: ${formatNumberSpaces(r.terminal)} | Berildi: ${formatNumberSpaces(r.given_amount)}
            </div>
          </td>
          <td>
            <b class="val-net">${formatNumberSpaces(r.net_amount)} so'm</b>
          </td>
          <td>
            <span class="val-debt-paid">${formatNumberSpaces(r.debt_paid)} so'm</span>
            ${effectiveDebt > 0 ? `<div class="val-debt-remaining">(Qoldiq: ${formatNumberSpaces(effectiveDebt)})</div>` : ''}
          </td>
          <td><span class="badge badge-sim">${r.sim_cards_count} dona</span></td>
          <td>
            <button class="btn-details" onclick="openReportDetailsModal(${r.id})">
              👁️ Batafsil
            </button>
          </td>
          <td>${actions}</td>
        </tr>
      `;
    });
  } catch (e) {}
}

async function updateReportStatus(id, status) {
  try {
    const res = await api(`/api/reports/${id}/status`, "POST", { status });
    showToast(res.message, "success");
    loadAdminReports();
  } catch (e) {}
}

function openReportDetailsModal(reportId) {
  const r = adminReportsCache.find(x => x.id === reportId);
  if (!r) {
    showToast("Hisobot ma'lumotlari topilmadi!", "danger");
    return;
  }

  const modal = document.getElementById("report-details-modal");
  const titleEl = document.getElementById("rep-detail-modal-title");
  const subEl = document.getElementById("rep-detail-subtitle");
  const bodyEl = document.getElementById("rep-detail-body");
  const actionsEl = document.getElementById("rep-detail-actions");

  titleEl.innerHTML = `📋 Hisobot: <b>${r.employee_name}</b>`;
  subEl.innerHTML = `Sana: <b>${formatDateOnly(r.report_date)}</b> | Topshirilgan vaqti: <b>${formatTashkentDateTime(r.created_at)}</b> | Holati: ${formatStatusBadge(r.status)}`;

  const effectiveDebt = Math.max(0, (r.debt_snapshot || 0) - (r.debt_paid || 0));

  bodyEl.innerHTML = `
    <div class="grid-2" style="gap: 1.25rem;">
      <!-- Kirimlar ustuni -->
      <div class="rep-modal-income-col">
        <h4 class="rep-modal-income-head">
          <span>📥 KIRIMLAR</span>
          <b class="rep-modal-inflow-total">${formatNumberSpaces(r.total_inflow)} so'm</b>
        </h4>
        <table class="rep-modal-table">
          <tr><td class="rep-modal-label">Paynet tushumi:</td><td class="rep-modal-val">${formatNumberSpaces(r.paynet)} so'm</td></tr>
          <tr><td class="rep-modal-label">Karta to'ldirish (+3% ustama):</td><td class="rep-modal-val">${formatNumberSpaces(r.card_amount)} so'm</td></tr>
          <tr><td class="rep-modal-label">Leviy tushum:</td><td class="rep-modal-val">${formatNumberSpaces(r.leviy)} so'm</td></tr>
          ${r.debt_paid > 0 ? `<tr><td class="rep-modal-debt-paid-lbl">Qarz uchun to'lov (Kirim):</td><td class="rep-modal-debt-paid-val">+${formatNumberSpaces(r.debt_paid)} so'm</td></tr>` : ''}
          <tr class="rep-modal-divider"><td class="rep-modal-label">Boshlang'ich qarzdorlik:</td><td class="rep-modal-debt-snapshot">${formatNumberSpaces(r.debt_snapshot || 0)} so'm</td></tr>
          <tr><td class="rep-modal-debt-rem-lbl">Qolgan qarzdorlik:</td><td class="rep-modal-debt-rem-val">${formatNumberSpaces(effectiveDebt)} so'm</td></tr>
        </table>
      </div>

      <!-- Chiqimlar ustuni -->
      <div class="rep-modal-expense-col">
        <h4 class="rep-modal-expense-head">
          <span>📤 CHIQIMLAR</span>
          <b class="rep-modal-outflow-total">${formatNumberSpaces(r.total_outflow)} so'm</b>
        </h4>
        <table class="rep-modal-table">
          <tr><td class="rep-modal-label">Kunlik (Oylik / Avans):</td><td class="rep-modal-val">${formatNumberSpaces(r.kunlik)} so'm</td></tr>
          <tr><td class="rep-modal-label">Terminal chiqimi:</td><td class="rep-modal-val">${formatNumberSpaces(r.terminal)} so'm</td></tr>
          <tr><td class="rep-modal-label">Berilgan summa:</td><td class="rep-modal-val">${formatNumberSpaces(r.given_amount)} so'm</td></tr>
          <tr><td class="rep-modal-label">Skidka (Chegirma):</td><td class="rep-modal-val">${formatNumberSpaces(r.skidka)} so'm</td></tr>
          <tr><td class="rep-modal-label">Boshqa xarajatlar:</td><td class="rep-modal-val">${formatNumberSpaces(r.xarajat)} so'm</td></tr>
        </table>
      </div>
    </div>

    <!-- Yakuniy Sof Kassa va Sim-karta kartasi -->
    <div class="rep-modal-net-card">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
        <div>
          <div style="font-size: 0.85rem; color: var(--text-sub);">Kassaga topshirilishi kerak bo'lgan summa (Net):</div>
          <div style="font-size: 1.75rem; font-weight: 800; color: var(--accent-success); margin-top: 0.25rem;">
            ${formatNumberSpaces(r.net_amount)} so'm
          </div>
          <div class="rep-modal-net-subtitle">
            (Kirimlar: ${formatNumberSpaces(r.total_inflow)} so'm - Chiqimlar: ${formatNumberSpaces(r.total_outflow)} so'm)
          </div>
        </div>
        <div style="text-align: right;">
          <div style="font-size: 0.85rem; color: var(--text-sub);">Sotilgan sim-kartalar:</div>
          <div class="rep-modal-sim-total">
            📱 ${r.sim_cards_count} dona
          </div>
        </div>
      </div>

      <div style="margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
        <span style="font-size: 0.85rem; color: var(--text-sub);">Xodim izohi:</span>
        <div style="font-size: 0.95rem; color: var(--text-main); margin-top: 0.25rem; font-style: italic;">
          "${r.comment || 'Izoh qoldirilmagan'}"
        </div>
      </div>
    </div>
  `;

  let actionBtns = `
    <button type="button" class="btn-logout" onclick="closeReportDetailsModal()">Yopish</button>
  `;

  if (r.status === "PENDING") {
    actionBtns = `
      <button type="button" class="btn-success" onclick="updateReportStatusFromModal(${r.id}, 'APPROVED')">✅ Tasdiqlash</button>
      <button type="button" class="btn-danger" onclick="updateReportStatusFromModal(${r.id}, 'REJECTED')">❌ Rad etish</button>
      <button type="button" class="btn-logout" onclick="closeReportDetailsModal()">Yopish</button>
    `;
  }

  actionsEl.innerHTML = actionBtns;
  modal.style.display = "flex";
}

function closeReportDetailsModal() {
  const modal = document.getElementById("report-details-modal");
  if (modal) modal.style.display = "none";
}

async function updateReportStatusFromModal(id, status) {
  await updateReportStatus(id, status);
  closeReportDetailsModal();
}

// Admin 2: Berilgan summalarni tasdiqlash
async function loadAdminGivens() {
  try {
    const res = await api("/api/given/all");
    const tbody = document.getElementById("admin-givens-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-sub);">Hozircha yozuvlar yo'q</td></tr>`;
      return;
    }

    res.data.forEach(g => {
      const actions = g.status === "PENDING" ? `
        <button class="btn-success" onclick="updateGivenStatus(${g.id}, 'APPROVED')">✅ Tasdiqlash</button>
        <button class="btn-danger" onclick="updateGivenStatus(${g.id}, 'REJECTED')">❌ Rad etish</button>
      ` : formatStatusBadge(g.status);

      tbody.innerHTML += `
        <tr>
          <td>#${g.id}</td>
          <td><b>${g.employee_name}</b></td>
          <td><b>${formatNumberSpaces(g.amount)} so'm</b></td>
          <td>${g.comment}</td>
          <td style="font-size: 0.8rem; color: var(--text-sub);">${formatTashkentDateTime(g.created_at)}</td>
          <td>${actions}</td>
        </tr>
      `;
    });
  } catch (e) {}
}

async function updateGivenStatus(id, status) {
  try {
    const res = await api(`/api/given/${id}/status`, "POST", { status });
    showToast(res.message, "success");
    loadAdminGivens();
  } catch (e) {}
}

// Admin 3: Karta so'rovlarini tasdiqlash
async function loadAdminTopups() {
  try {
    const res = await api("/api/cards/all");
    const tbody = document.getElementById("admin-topups-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-sub);">Hozircha karta so'rovlari yo'q</td></tr>`;
      return;
    }

    res.data.forEach(c => {
      const actions = c.status === "PENDING" ? `
        <button class="btn-success" onclick="updateCardTopupStatus(${c.id}, 'APPROVED')">✅ Tasdiqlash</button>
        <button class="btn-danger" onclick="updateCardTopupStatus(${c.id}, 'REJECTED')">❌ Rad etish</button>
      ` : formatStatusBadge(c.status, c.approved_by_name || 'Bosh Rahbar');

      tbody.innerHTML += `
        <tr>
          <td>#${c.transaction_number}</td>
          <td><b>${c.employee_name}</b></td>
          <td><span class="copyable-card" onclick="copyToClipboard('${c.card_number}')">${c.card_number} 📋</span></td>
          <td>${c.card_holder}</td>
          <td>${formatNumberSpaces(c.amount)} so'm</td>
          <td style="color: var(--accent-success);">${formatNumberSpaces(c.surcharge_amount)} so'm</td>
          <td style="font-size: 0.8rem; color: var(--text-sub);">${formatTashkentDateTime(c.created_at)}</td>
          <td>${actions}</td>
        </tr>
      `;
    });
  } catch (e) {}
}

async function updateCardTopupStatus(id, status) {
  try {
    const res = await api(`/api/cards/${id}/status`, "POST", { status });
    showToast(res.message, "success");
    loadAdminTopups();
  } catch (e) {}
}

// Admin 4: Kassir va Xodim summalarini solishtirish
async function loadAdminComparison() {
  try {
    const res = await api("/api/cashier/comparison");
    const tbody = document.getElementById("admin-comparison-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-sub); padding: 1.5rem;">Taqqoslash uchun ma'lumotlar yo'q</td></tr>`;
      return;
    }

    res.data.forEach(row => {
      const diffBadge = row.difference === 0 && row.report_status !== "TOPSHIRILMAGAN"
        ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border-color: rgba(16, 185, 129, 0.35); font-weight: 700;">MOS (0 so'm)</span>`
        : `<span class="badge badge-admin" style="font-weight: 800;">FARQ: ${formatNumberSpaces(row.difference)} so'm</span>`;

      const uzs = row.cashier_amount_uzs || 0;
      const usd = row.cashier_amount_usd || 0;
      const cashierDisplay = `
        <div class="val-net">${formatNumberSpaces(row.cashier_amount)} so'm</div>
        <div class="val-sub">
          So'mda: ${formatNumberSpaces(uzs)} | Dollarda: ${formatNumberSpaces(usd)} $
        </div>
      `;

      tbody.innerHTML += `
        <tr>
          <td><b>${row.employee_name}</b></td>
          <td><b>${formatNumberSpaces(row.report_amount)} so'm</b> (${formatStatusBadge(row.report_status)})</td>
          <td>${cashierDisplay}</td>
          <td>${diffBadge}</td>
          <td><b>${row.cashier_names}</b></td>
        </tr>
      `;
    });
  } catch (e) {}
}

// Admin 5: Xodimlar va Qarz boshqaruvi
let adminUsersCache = [];

async function loadAdminUsers() {
  try {
    const res = await api("/api/admin/users");
    adminUsersCache = res.data || [];
    const tbody = document.getElementById("admin-users-tbody");
    tbody.innerHTML = "";

    // 1. Qarz belgilash dropdown ro'yxatini yangilash
    const debtSelect = document.getElementById("assign-debt-user-select");
    if (debtSelect) {
      const currentSelected = debtSelect.value;
      debtSelect.innerHTML = `<option value="">-- Xodimni tanlang --</option>`;
      res.data
        .filter(u => u.role !== "ADMIN" && u.is_active)
        .forEach(u => {
          debtSelect.innerHTML += `<option value="${u.id}">${u.full_name} (Mavjud qarz: ${formatNumberSpaces(u.debt_amount ?? 0)} so'm)</option>`;
        });
      if (currentSelected) debtSelect.value = currentSelected;
    }

    // 2. Jadval qatorlarini to'ldirish
    res.data.forEach(u => {
      // Bosh Rahbar daxlsiz - uni hech kim bo'shata olmaydi va tizimdan chiqara olmaydi!
      const activeBtn = u.role === "ADMIN"
        ? `<span class="badge" style="background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.35); color: #c7d2fe; font-size: 0.78rem; padding: 0.35rem 0.65rem; border-radius: 6px; display: inline-flex; align-items: center; gap: 4px;">🛡️ Daxlsiz</span>`
        : (u.is_active 
            ? `<button class="btn-danger" onclick="toggleUserActive(${u.id})">Bo'shatish</button>`
            : `<button class="btn-success" onclick="toggleUserActive(${u.id})">Faollashtirish</button>`);

      const appointCashierBtn = u.role !== "ADMIN" && u.is_active
        ? (u.role === "CASHIER"
            ? `<button class="btn-logout" style="border-color: #3b82f6; color: #93c5fd;" onclick="dismissCashier(${u.id})">👤 Xodim qilish</button>`
            : `<button class="btn-logout" style="border-color: var(--accent-warning); color: #fbbf24;" onclick="appointCashier(${u.id})">💼 Kassir qilish</button>`)
        : "";

      const debtBtn = u.role !== "ADMIN" && u.is_active
        ? `<button class="btn-logout" style="border-color: #f59e0b; color: #fbbf24;" onclick="selectUserForDebt(${u.id})">+ Qarz</button>`
        : "";

      tbody.innerHTML += `
        <tr style="opacity: ${u.is_active ? 1 : 0.5};">
          <td><b>${u.full_name}</b></td>
          <td><code>${u.telegram_id}</code></td>
          <td><span class="badge ${u.role === 'ADMIN' ? 'badge-admin' : u.role === 'CASHIER' ? 'badge-cashier' : 'badge-employee'}">${formatRoleName(u.role)}</span></td>
          <td><b>${formatNumberSpaces(u.debt_amount ?? 0)} so'm</b></td>
          <td>${u.is_active ? '<span style="color: #34d399;">Faol</span>' : '<span style="color: #f87171;">Bo\'shatilgan</span>'}</td>
          <td style="display: flex; gap: 0.35rem; flex-wrap: wrap; align-items: center;">
            ${activeBtn}
            ${debtBtn}
            <button class="btn-logout" onclick="promptUpdatePassword(${u.id}, '${u.full_name}')">Parol</button>
            ${appointCashierBtn}
          </td>
        </tr>
      `;
    });
  } catch (e) {}
}

async function toggleUserActive(userId) {
  const targetUser = (adminUsersCache || []).find(u => u.id === userId);
  if (targetUser && targetUser.role === "ADMIN") {
    showToast("Bosh Rahbar daxlsiz! Uni tizimdan hech kim bo'shata olmaydi va chiqara olmaydi!", "danger");
    return;
  }
  const actionText = (targetUser && targetUser.is_active) ? "ishdan bo'shatmoqchimisiz" : "qaytadan faollashtirmoqchimisiz";
  if (!confirm(`Haqiqatan ham bu xodimni ${actionText}?`)) return;
  try {
    const res = await api(`/api/admin/users/${userId}/toggle-active`, "POST");
    showToast(res.message, "success");
    loadAdminUsers();
  } catch (e) {}
}

function selectUserForDebt(userId) {
  const sel = document.getElementById("assign-debt-user-select");
  if (sel) {
    sel.value = userId;
  }
  const amtInput = document.getElementById("assign-debt-amount");
  if (amtInput) {
    amtInput.focus();
    amtInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

async function handleCreateUserSubmit(e) {
  e.preventDefault();
  const tgId = document.getElementById("new-user-tg-id").value;
  const name = document.getElementById("new-user-name").value.trim();

  if (!tgId || !name) {
    showToast("Iltimos, Telegram ID va xodim ismini kiriting!", "danger");
    return;
  }

  try {
    const res = await api("/api/admin/users/create", "POST", {
      telegram_id: parseInt(tgId),
      full_name: name,
      initial_debt: 0
    });
    showToast(res.message, "success");
    document.getElementById("create-user-form").reset();
    loadAdminUsers();
  } catch (e) {}
}

async function handleAssignDebtSubmit(e) {
  e.preventDefault();
  const userId = document.getElementById("assign-debt-user-select").value;
  const amountVal = document.getElementById("assign-debt-amount").value;
  const reason = document.getElementById("assign-debt-reason").value.trim();
  const amount = parseFormattedNumber(amountVal);

  if (!userId) {
    showToast("Iltimos, xodimni tanlang!", "danger");
    return;
  }
  if (amount <= 0) {
    showToast("Qarz summasi 0 dan katta bo'lishi shart!", "danger");
    return;
  }
  if (!reason || reason.length < 2) {
    showToast("Iltimos, qarz sababi yoki izohini kiriting!", "danger");
    return;
  }

  try {
    const res = await api(`/api/admin/users/${userId}/debt`, "POST", {
      user_id: parseInt(userId),
      debt_amount: amount,
      reason: reason
    });
    showToast(res.message, "success");
    document.getElementById("assign-debt-form").reset();
    loadAdminUsers();
  } catch (e) {}
}

async function promptUpdatePassword(userId, name) {
  const newPass = prompt(`${name} uchun yangi parolni kiriting:`);
  if (!newPass || newPass.trim().length < 3) return;

  try {
    const res = await api(`/api/admin/users/${userId}/password`, "POST", {
      user_id: userId,
      new_password: newPass.trim()
    });
    showToast(res.message, "success");
  } catch (e) {}
}

async function appointCashier(userId) {
  if (!confirm("Ushbu xodimni yangi Kassir etib tayinlamoqchimisiz? Tizimda faqat 1 ta kassir bo'ladi, oldingi kassir avtomatik oddiy xodimga aylanadi.")) return;
  try {
    const res = await api("/api/admin/cashier/appoint", "POST", { user_id: userId });
    showToast(res.message, "success");
    loadAdminUsers();
    loadAdminCashierTab();
  } catch (e) {}
}

async function dismissCashier(userId) {
  if (!confirm("Ushbu kassirni kassirlikdan bo'shatib, oddiy xodim holatiga qaytarmoqchimisiz?")) return;
  try {
    const res = await api("/api/admin/cashier/dismiss", "POST", { user_id: userId });
    showToast(res.message, "success");
    loadAdminUsers();
    loadAdminCashierTab();
  } catch (e) {}
}

// Admin 6: Kassir tayinlash va Kassirlik tarixi oynasi
async function loadAdminCashierTab() {
  try {
    // 1. Dropdown xodimlar
    const usersRes = await api("/api/admin/users");
    const select = document.getElementById("appoint-cashier-select");
    if (select) {
      select.innerHTML = `<option value="">-- Xodimni tanlang --</option>`;
      usersRes.data
        .filter(u => u.is_active && u.role !== "ADMIN")
        .forEach(u => {
          const isCurrentCashier = u.role === "CASHIER" ? " (Hozirgi Kassir ⭐)" : "";
          select.innerHTML += `<option value="${u.id}">${u.full_name}${isCurrentCashier}</option>`;
        });
    }

    // 2. Barcha topshirilgan summalar tarixi (Admin ko'rinishi)
    const handRes = await api("/api/cashier/all-handovers");
    const handTbody = document.getElementById("admin-all-handovers-tbody");
    if (handTbody) {
      handTbody.innerHTML = "";
      if (!handRes.data || handRes.data.length === 0) {
        handTbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-sub); padding: 1.5rem;">Hozircha topshirilgan summalar yo'q</td></tr>`;
      } else {
        handRes.data.forEach(h => {
          handTbody.innerHTML += `
            <tr>
              <td><b>${formatDateOnly(h.handover_date)}</b></td>
              <td><b>${h.employee_name}</b></td>
              <td><span class="val-uzs">${formatNumberSpaces(h.amount_uzs)} so'm</span></td>
              <td><span class="val-usd">${formatNumberSpaces(h.amount_usd)} $</span></td>
              <td><b class="val-net">${formatNumberSpaces(h.amount)} so'm</b></td>
              <td><b>${h.cashier_name}</b></td>
              <td style="font-size: 0.8rem; color: var(--text-sub);">${formatTashkentDateTime(h.created_at)}</td>
            </tr>
          `;
        });
      }
    }

    // 3. Kassirlik tayinlovlari tarixi
    const histRes = await api("/api/admin/cashier/history");
    const histTbody = document.getElementById("admin-cashier-history-tbody");
    if (histTbody) {
      histTbody.innerHTML = "";
      if (!histRes.data || histRes.data.length === 0) {
        histTbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-sub);">Tayinlovlar tarixi mavjud emas</td></tr>`;
      } else {
        histRes.data.forEach(ch => {
          const actionBadge = ch.action === 'APPOINTED'
            ? `<span class="badge badge-cashier">Tayinlandi ✅</span>`
            : `<span class="badge badge-employee">Oddiy xodim 👤</span>`;
          histTbody.innerHTML += `
            <tr>
              <td><b>${ch.cashier_name}</b></td>
              <td>${actionBadge}</td>
              <td>${ch.admin_name}</td>
              <td style="font-size: 0.8rem; color: var(--text-sub);">${formatTashkentDateTime(ch.created_at)}</td>
            </tr>
          `;
        });
      }
    }
  } catch (e) {}
}

async function handleAppointCashierSubmit() {
  const select = document.getElementById("appoint-cashier-select");
  const userId = select?.value;
  if (!userId) {
    showToast("Iltimos, xodimni tanlang!", "danger");
    return;
  }
  if (!confirm("Ushbu xodimni yangi Kassir etib tayinlamoqchimisiz? Tizimda faqat 1 ta kassir bo'ladi, oldingi kassir avtomatik oddiy xodimga aylanadi.")) return;

  try {
    const res = await api("/api/admin/cashier/appoint", "POST", { user_id: parseInt(userId) });
    showToast(res.message, "success");
    loadAdminCashierTab();
    loadAdminUsers();
  } catch (e) {}
}

// 7. Reyting va Liderlar jadvali (Oylik va Umumiy, Admin va Xodim ko'rinishi)
async function loadLeaderboard(period = "monthly", viewType = "emp") {
  try {
    const res = await api(`/api/rating/leaderboard?period=${period}`);
    const tbodyId = viewType === "admin" ? "admin-rating-tbody" : "emp-rating-tbody";
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    tbody.innerHTML = "";

    // Tugma klasslarini almashtirish
    const monthlyBtn = document.getElementById(`btn-${viewType}-rating-monthly`);
    const overallBtn = document.getElementById(`btn-${viewType}-rating-overall`);
    if (monthlyBtn && overallBtn) {
      if (period === "monthly") {
        monthlyBtn.className = "btn-primary";
        overallBtn.className = "btn-logout";
      } else {
        monthlyBtn.className = "btn-logout";
        overallBtn.className = "btn-primary";
      }
    }

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-sub);">Hozircha reyting ma'lumotlari mavjud emas</td></tr>`;
      return;
    }

    res.data.forEach(item => {
      const isTop3 = item.rank <= 3;
      const rankHtml = isTop3 
        ? `<b style="font-size: 1.1rem;">${item.badge}</b>` 
        : `<span style="color: var(--text-muted); font-weight: 600;">${item.badge}</span>`;

      tbody.innerHTML += `
        <tr style="${isTop3 ? 'background: rgba(245, 158, 11, 0.05);' : ''}">
          <td>${rankHtml}</td>
          <td><b>${item.employee_name}</b> <span class="badge ${item.role === 'CASHIER' ? 'badge-cashier' : 'badge-employee'}">${formatRoleName(item.role)}</span></td>
          <td><b>${formatNumberSpaces(item.total_sum)} so'm</b></td>
          <td><span class="val-uzs">${item.money_points} ball</span></td>
          <td><span class="val-net">${item.total_sim_cards} dona (${item.sim_points} ball)</span></td>
          <td><b style="color: var(--accent-warning); font-size: 1.1rem;">${item.total_score} ball</b></td>
          <td>${item.reports_count} kun</td>
        </tr>
      `;
    });
  } catch (e) {}
}

// Admin 8: Audit loglar va 90 kunlik saqlanish holati
async function loadAdminAudit() {
  try {
    // 1. 90 kunlik saqlanish holatini olish
    try {
      const retRes = await api("/api/admin/retention/status");
      const badge = document.getElementById("retention-cutoff-badge");
      if (badge && retRes.success) {
        badge.innerHTML = `📅 Chegara: <b>${formatTashkentDate(retRes.cutoff_date)}</b> gacha (90 kun)`;
      }
    } catch(err) {}

    // 2. Audit loglarni olish
    const res = await api("/api/admin/audit-logs");
    const tbody = document.getElementById("admin-audit-tbody");
    tbody.innerHTML = "";

    if (!res.data || res.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-sub);">Hozircha audit loglar yo'q</td></tr>`;
      return;
    }

    res.data.forEach(a => {
      tbody.innerHTML += `
        <tr>
          <td>#${a.id}</td>
          <td><b>${a.entity_type}</b></td>
          <td><span class="badge">${a.action}</span></td>
          <td>${a.actor_name || 'Tizim'}</td>
          <td>${a.details || '-'}</td>
          <td style="font-size: 0.8rem; color: var(--text-sub);">${formatTashkentDateTime(a.created_at, true)}</td>
        </tr>
      `;
    });
  } catch (e) {}
}

async function triggerManualRetentionCleanup() {
  if (!confirm("90 kundan eski barcha tarix ma'lumotlarini tozalashni tasdiqlaysizmi?")) return;
  try {
    const res = await api("/api/admin/retention/run-cleanup", "POST");
    if (res.success) {
      showToast(res.message, "success");
      await loadAdminAudit();
    } else {
      showToast(res.detail || "Tozalashda xatolik yuz berdi", "danger");
    }
  } catch (e) {
    showToast("Server bilan bog'lanishda xatolik!", "danger");
  }
}

async function handleClearAllHistory() {
  const confirmed = confirm(
    "⚠️ DIQQAT: Barcha test operatsiyalari (karta so'rovlari, berilgan summalar, kunlik hisobotlar, kassa topshirishlar, sim-kartalar va audit tarixi) to'liq tozalanadi va xodimlar qarzlari 0 ga tenglashtiriladi!\n\nHaqiqatan ham barcha tarixni tozalashni tasdiqlaysizmi?"
  );
  if (!confirmed) return;

  try {
    const res = await api("/api/admin/clear-history", "POST");
    if (res.success) {
      showToast(res.message || "Barcha tarix muvaffaqiyatli tozalandi!", "success");
      await loadAdminAudit();
      if (typeof loadAdminTopups === "function") loadAdminTopups();
      if (typeof loadAdminReports === "function") loadAdminReports();
      if (typeof loadAdminUsers === "function") loadAdminUsers();
      if (typeof loadAdminCashierHandovers === "function") loadAdminCashierHandovers();
      if (typeof loadSimDistributionsHistory === "function") loadSimDistributionsHistory();
    } else {
      showToast(res.detail || "Xatolik yuz berdi", "danger");
    }
  } catch (err) {
    showToast(err.message || "Tarixni tozalashda xatolik yuz berdi", "danger");
  }
}

// ==========================================
// SIM-KARTA BOSHQARUVI VA QIDIRUV (Rahbar & Kassir)
// ==========================================

function getOperatorBadge(op) {
  const operator = op || "Uzmobile";
  const cls = `badge-${operator.toLowerCase()}`;
  return `<span class="badge ${cls}" style="font-weight: 700;">${operator}</span>`;
}

async function loadAdminSimsTab() {
  await loadSimEmployeesSelect('admin');
  await loadSimSummary('admin');
}

async function loadCashierSimsTab() {
  await loadSimEmployeesSelect('cashier');
  await loadSimSummary('cashier');
}

async function loadSimEmployeesSelect(prefix) {
  try {
    const res = await api("/api/sim-cards/employees");
    const select = document.getElementById(`${prefix}-sim-employee-select`);
    if (!select) return;
    select.innerHTML = '<option value="">-- Xodimni tanlang --</option>';
    if (res.data && res.data.length > 0) {
      res.data
        .filter(emp => emp.role !== 'ADMIN')
        .forEach(emp => {
          const roleText = emp.role === 'CASHIER' ? 'Kassir' : 'Xodim';
          select.innerHTML += `<option value="${emp.id}">${emp.full_name} (${roleText})</option>`;
        });
    } else {
      select.innerHTML += '<option value="" disabled>Faol xodimlar topilmadi</option>';
    }
  } catch (e) {
    console.error("loadSimEmployeesSelect xatosi:", e);
  }
}

async function loadSimSummary(prefix) {
  try {
    const res = await api("/api/sim-cards/summary");
    const balanceTbody = document.getElementById(`${prefix}-sim-balance-tbody`);
    if (balanceTbody) {
      balanceTbody.innerHTML = "";
      if (!res.balances || res.balances.length === 0) {
        balanceTbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-sub);">Xodimlar ro'yxati bo'sh</td></tr>`;
      } else {
        res.balances.forEach(b => {
          balanceTbody.innerHTML += `
            <tr>
              <td><b>${b.full_name}</b></td>
              <td><span class="badge badge-primary">${b.in_stock || 0} dona</span></td>
              <td><span class="badge badge-success">${b.sold_count || 0} dona</span></td>
            </tr>
          `;
        });
      }
    }

    if (prefix === "admin") {
      const recentTbody = document.getElementById("admin-sim-recent-tbody");
      if (recentTbody) {
        recentTbody.innerHTML = "";
        if (!res.recent || res.recent.length === 0) {
          recentTbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-sub);">Hali sim-karta tarqatilmagan</td></tr>`;
        } else {
          res.recent.forEach(s => {
            const statusBadge = s.status === "GIVEN" 
              ? `<span class="badge badge-primary">Xodimda</span>` 
              : `<span class="badge badge-success">Sotilgan ✅</span>`;

            const startS = s.start_serial || s.serial_number || "";
            const endS = s.end_serial || s.serial_number || "";
            const count = s.total_count || 1;

            let serialHtml = "";
            if (!endS || startS === endS) {
              serialHtml = `<span class="copyable-card" onclick="copyToClipboard('${startS}')" title="Nusxalash uchun bosing"><code>${startS}</code></span> <span class="badge badge-primary" style="margin-left: 4px;">1 dona</span>`;
            } else {
              serialHtml = `
                <div style="font-size: 0.88rem; line-height: 1.4;">
                  <span class="copyable-card" onclick="copyToClipboard('${startS}')" title="Boshlang'ich seriyani nusxalash"><code>${startS}</code></span> dan<br>
                  <span class="copyable-card" onclick="copyToClipboard('${endS}')" title="Tugash seriyasini nusxalash"><code>${endS}</code></span> gacha 
                  <span class="badge badge-primary" style="margin-left: 4px; font-weight: bold;">${count} dona</span>
                </div>
              `;
            }

            recentTbody.innerHTML += `
              <tr>
                <td>${serialHtml}</td>
                <td>${getOperatorBadge(s.operator_type)}</td>
                <td><b>${s.employee_name}</b></td>
                <td>${s.distributor_name}</td>
                <td>${statusBadge}</td>
              </tr>
            `;
          });
        }
      }
    }
  } catch (e) {}
}

async function searchSimCard() {
  const input = document.getElementById("admin-sim-search-input");
  const resultContainer = document.getElementById("admin-sim-search-result");
  const serial = input.value.trim().replace(/[^0-9]/g, "");

  if (!serial || serial.length < 3) {
    showToast("Qidirish uchun kamida 3 ta raqam kiriting!", "danger");
    return;
  }

  try {
    resultContainer.style.display = "block";
    resultContainer.innerHTML = `<div style="text-align: center; color: var(--text-sub); padding: 0.5rem;">Qidirilmoqda...</div>`;

    const res = await api(`/api/sim-cards/search?serial=${encodeURIComponent(serial)}`);
    if (!res.data || res.data.length === 0) {
      resultContainer.innerHTML = `
        <div style="color: #f87171; text-align: center; padding: 0.5rem;">
          ❌ Ushbu seriya raqamli (<b>${serial}</b>) sim-karta tizimda topilmadi.
        </div>
      `;
      return;
    }

    let html = `
      <div style="font-size: 0.95rem; margin-bottom: 0.75rem; color: #a5b4fc;">
        Topildi: <b>${res.data.length} dona</b> sim-karta:
      </div>
      <div class="table-container">
        <table class="custom-table">
          <thead>
            <tr>
              <th>Seriya raqami</th>
              <th>Operator (Turi)</th>
              <th>Xodim (Qabul qiluvchi)</th>
              <th>Tarqatuvchi</th>
              <th>Berilgan vaqti</th>
              <th>Holati</th>
            </tr>
          </thead>
          <tbody>
    `;

    res.data.forEach(item => {
      const statusBadge = item.status === "GIVEN"
        ? `<span class="badge badge-primary">Xodimda (Sotilmagan)</span>`
        : `<span class="badge badge-success">Sotilgan ✅</span>`;
      html += `
        <tr>
          <td><code style="font-size: 1.05rem; font-weight: 700; color: #60a5fa;">${item.serial_number}</code></td>
          <td>${getOperatorBadge(item.operator_type)}</td>
          <td><b>${item.employee_name}</b> (TG: ${item.employee_tg})</td>
          <td>${item.distributor_name}</td>
          <td style="font-size: 0.85rem; color: var(--text-sub);">${formatTashkentDateTime(item.distributed_at)}</td>
          <td>${statusBadge}</td>
        </tr>
      `;
    });

    html += `</tbody></table></div>`;
    resultContainer.innerHTML = html;
  } catch (err) {
    resultContainer.innerHTML = `<div style="color: #f87171; padding: 0.5rem;">Xatolik: ${err.message}</div>`;
  }
}

async function handleDistributeSim(e, role) {
  e.preventDefault();
  const operatorSelect = document.getElementById(`${role}-sim-operator`);
  const startInput = document.getElementById(`${role}-sim-start`);
  const endInput = document.getElementById(`${role}-sim-end`);
  const empSelect = document.getElementById(`${role}-sim-employee-select`);

  const operatorType = operatorSelect ? operatorSelect.value : "Uzmobile";
  const startSerial = startInput.value.trim().replace(/[^0-9]/g, "");
  const endSerial = endInput.value.trim().replace(/[^0-9]/g, "");
  const empId = parseInt(empSelect.value);

  if (!startSerial || startSerial.length !== 18) {
    showToast("Boshlang'ich seriya raqami aynan 18 ta raqam bo'lishi shart!", "danger");
    return;
  }

  if (endSerial && endSerial.length !== 18) {
    showToast("Tugash seriya raqami aynan 18 ta raqam bo'lishi shart!", "danger");
    return;
  }

  if (!empId) {
    showToast("Iltimos, xodimni tanlang!", "danger");
    return;
  }

  try {
    const res = await api("/api/sim-cards/distribute", "POST", {
      operator_type: operatorType,
      start_serial: startSerial,
      end_serial: endSerial || startSerial,
      employee_id: empId
    });

    showToast(res.message, "success");
    startInput.value = "";
    endInput.value = "";
    empSelect.value = "";

    await loadSimSummary(role);
  } catch (err) {}
}

// ==========================================
// DOLLAR KURSI BOSHQARUVI (RAHBAR & XODIMLAR)
// ==========================================

let currentUsdRate = 12000;

async function loadUsdRate() {
  try {
    const res = await api("/api/settings/usd-rate");
    if (res && res.formatted) {
      currentUsdRate = res.rate;
      const textEl = document.getElementById("usd-rate-text");
      if (textEl) {
        textEl.innerText = res.formatted;
      }
      const sideTextEl = document.getElementById("sidebar-usd-rate-text");
      if (sideTextEl) {
        sideTextEl.innerText = res.formatted;
      }
    }
  } catch (err) {
    console.warn("Dollar kursini yuklashda xatolik:", err);
  }
}

function handleUsdRateClick() {
  if (!currentUser || currentUser.role !== "ADMIN") {
    // Xodimlar uchun faqat ko'rinadi (bosilganda o'zgartirish chiqmaydi)
    return;
  }
  openUsdRateModal();
}

function openUsdRateModal() {
  const modal = document.getElementById("usd-rate-modal");
  const input = document.getElementById("usd-rate-input");
  const preview = document.getElementById("usd-rate-preview");
  if (!modal) return;

  input.value = formatNumberSpaces(currentUsdRate);
  preview.innerHTML = `Ko'rinishi: <b>1$ = ${formatNumberSpaces(currentUsdRate)} so'm</b>`;
  modal.style.display = "flex";
  setTimeout(() => input.focus(), 50);
}

function closeUsdRateModal() {
  const modal = document.getElementById("usd-rate-modal");
  if (modal) modal.style.display = "none";
}

function handleUsdRateOverlayClick(e) {
  if (e.target && e.target.id === "usd-rate-modal") {
    closeUsdRateModal();
  }
}

async function handleUsdRateSubmit(e) {
  e.preventDefault();
  const input = document.getElementById("usd-rate-input");
  const rateVal = parseFormattedNumber(input.value);

  if (!rateVal || rateVal <= 0) {
    showToast("Iltimos, to'g'ri dollar kursini kiriting!", "danger");
    return;
  }

  try {
    const res = await api("/api/settings/usd-rate", "POST", { rate: rateVal });
    showToast(res.message, "success");
    closeUsdRateModal();
    await loadUsdRate();
  } catch (err) {}
}

function setupUsdRateInput() {
  const input = document.getElementById("usd-rate-input");
  const preview = document.getElementById("usd-rate-preview");
  if (!input) return;

  input.addEventListener("input", (e) => {
    const raw = e.target.value.replace(/\D/g, "");
    e.target.value = formatNumberSpaces(raw);
    const num = parseFormattedNumber(e.target.value);
    preview.innerHTML = `Ko'rinishi: <b>1$ = ${formatNumberSpaces(num || 0)} so'm</b>`;
  });
}

// ==========================================
// PROGRESSIVE WEB APP (PWA) SERVICE WORKER
// ==========================================
function registerServiceWorker() {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' })
        .then((reg) => {
          console.log('PWA ServiceWorker muvaffaqiyatli ro\'yxatdan o\'tdi:', reg.scope);
        })
        .catch((err) => {
          console.warn('PWA ServiceWorker ro\'yxatdan o\'tishida ogohlantirish:', err);
        });
    });
  }
}

// Window load init
window.addEventListener("DOMContentLoaded", () => {
  initTheme();
  setupCardTopupInputs();
  setupGivenAmountInputs();
  setupReportCalculationListeners();
  setupUsdRateInput();
  registerServiceWorker();

  document.getElementById("login-form-step-1")?.addEventListener("submit", handleLoginStep1);
  document.getElementById("login-form-step-2")?.addEventListener("submit", handleVerifyOtp);
  document.getElementById("card-topup-form")?.addEventListener("submit", handleCardTopupSubmit);
  document.getElementById("given-amount-form")?.addEventListener("submit", handleGivenAmountSubmit);
  document.getElementById("daily-report-form")?.addEventListener("submit", handleReportSubmit);
  document.getElementById("cashier-handover-form")?.addEventListener("submit", handleCashierHandoverSubmit);
  document.getElementById("create-user-form")?.addEventListener("submit", handleCreateUserSubmit);
  document.getElementById("assign-debt-form")?.addEventListener("submit", handleAssignDebtSubmit);

  const debtAmtInput = document.getElementById("assign-debt-amount");
  if (debtAmtInput) {
    debtAmtInput.addEventListener("input", (e) => {
      e.target.value = formatNumberSpaces(e.target.value);
    });
  }

  initApp();
});
