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
// Yordamchi Xavfsizlik Funksiyalari (HTML Escape)
// ==========================================
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatTashkentDate(dateStr) {
  return formatDateOnly(dateStr);
}

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
      if (res.status === 403 && json.detail && json.detail.includes("Obunangizni uzaytiring")) {
        showSubscriptionExpiredModal(json.detail);
      }
      throw new Error(json.detail || json.message || "Xatolik yuz berdi");
    }
    return json;
  } catch (err) {
    if (!err.message || !err.message.includes("Obunangizni uzaytiring")) {
      showToast(err.message, "danger");
    }
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
  if (role === "DEVELOPER") return "Dasturchi Admin";
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

// ==========================================
// ANDROID NATIVE BRIDGE INTEGRATSIYASI
// ==========================================
function syncWithAndroidBridge() {
  if (window.AndroidBridge && authToken && currentUser) {
    try {
      window.AndroidBridge.saveAuth(
        authToken,
        currentUser.role || "",
        currentUser.full_name || "",
        currentUser.id || 0
      );
      console.log("AndroidBridge bilan sinxronlandi:", currentUser.full_name, currentUser.role);
    } catch (e) {
      console.warn("AndroidBridge saveAuth xatoligi:", e);
    }
  }
}

function clearAndroidBridgeAuth() {
  if (window.AndroidBridge) {
    try {
      window.AndroidBridge.clearAuth();
      console.log("AndroidBridge ma'lumotlari tozalandi");
    } catch (e) {
      console.warn("AndroidBridge clearAuth xatoligi:", e);
    }
  }
}

async function initApp() {
  if (authToken) {
    if (checkInactivityTimeout()) {
      return;
    }
    try {
      const res = await api("/api/auth/me");
      currentUser = res.user;
      localStorage.setItem("crm_last_activity", Date.now().toString());
      hideSubscriptionExpiredModal();
      try {
        renderApp();
      } catch (renderErr) {
        console.error("renderApp xatosi:", renderErr);
      }
      syncWithAndroidBridge();
      return;
    } catch (e) {
      console.warn("Auth token yaroqsiz yoki obuna tugagan:", e);
      if (e.message && e.message.includes("Obunangizni uzaytiring")) {
        showSubscriptionExpiredModal(e.message);
        return;
      }
      authToken = null;
      localStorage.removeItem("crm_token");
      localStorage.removeItem("crm_last_activity");
    }
  }
  showLoginModal();
}

function logout() {
  stopAutoLocationTracking();
  clearAndroidBridgeAuth();
  hideSubscriptionExpiredModal();
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
    if (errText.includes("Obunangizni uzaytiring")) {
      showSubscriptionExpiredModal(errText);
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
    try {
      renderApp();
    } catch (renderErr) {
      console.error("renderApp xatosi:", renderErr);
    }
    syncWithAndroidBridge();
  } catch (err) {
    if (alertEl) {
      alertEl.innerText = err.message || "Kodni tekshirishda xatolik!";
      alertEl.style.display = "block";
    }
    if (err.message && err.message.includes("Obunangizni uzaytiring")) {
      showSubscriptionExpiredModal(err.message);
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

function updateDebtBadges() {
  const debtBadge = document.getElementById("nav-user-debt");
  const sidebarDebt = document.getElementById("sidebar-user-debt");
  const hasDebt = currentUser && currentUser.role !== "ADMIN" && currentUser.debt_amount && Number(currentUser.debt_amount) > 0;
  const debtText = hasDebt ? `Qarz: ${formatNumberSpaces(currentUser.debt_amount)} so'm` : "";

  if (debtBadge) {
    if (hasDebt) {
      debtBadge.style.display = "inline-flex";
      debtBadge.innerText = debtText;
    } else {
      debtBadge.style.display = "none";
      debtBadge.innerText = "";
    }
  }
  if (sidebarDebt) {
    if (hasDebt) {
      sidebarDebt.style.display = "inline-flex";
      sidebarDebt.innerText = debtText;
    } else {
      sidebarDebt.style.display = "none";
      sidebarDebt.innerText = "";
    }
  }
}

function updateShiftStatusBadgesAndBanner() {
  const navShiftBadge = document.getElementById("nav-user-shift");
  const sidebarShiftBadge = document.getElementById("sidebar-user-shift");
  const banner = document.getElementById("employee-resting-banner");

  if (!currentUser || currentUser.role === "ADMIN" || currentUser.role === "DEVELOPER") {
    if (navShiftBadge) navShiftBadge.style.display = "none";
    if (sidebarShiftBadge) sidebarShiftBadge.style.display = "none";
    if (banner) banner.style.display = "none";
    applyShiftFormRestrictions(false);
    return;
  }

  const isResting = (currentUser.shift_status === "RESTING");

  if (navShiftBadge) {
    navShiftBadge.style.display = "inline-flex";
    if (isResting) {
      navShiftBadge.innerText = "🌙 Damda";
      navShiftBadge.style.background = "rgba(245, 158, 11, 0.18)";
      navShiftBadge.style.borderColor = "rgba(245, 158, 11, 0.45)";
      navShiftBadge.style.color = "#fbbf24";
      navShiftBadge.title = "Siz hozirda dam olish (damda) rejimidasiz";
    } else {
      navShiftBadge.innerText = "🟢 Ishda";
      navShiftBadge.style.background = "rgba(16, 185, 129, 0.18)";
      navShiftBadge.style.borderColor = "rgba(16, 185, 129, 0.45)";
      navShiftBadge.style.color = "#34d399";
      navShiftBadge.title = "Siz faol ish rejimidasiz";
    }
  }

  if (sidebarShiftBadge) {
    sidebarShiftBadge.style.display = "inline-flex";
    if (isResting) {
      sidebarShiftBadge.innerText = "🌙 Damda";
      sidebarShiftBadge.style.background = "rgba(245, 158, 11, 0.18)";
      sidebarShiftBadge.style.borderColor = "rgba(245, 158, 11, 0.45)";
      sidebarShiftBadge.style.color = "#fbbf24";
    } else {
      sidebarShiftBadge.innerText = "🟢 Ishda";
      sidebarShiftBadge.style.background = "rgba(16, 185, 129, 0.18)";
      sidebarShiftBadge.style.borderColor = "rgba(16, 185, 129, 0.45)";
      sidebarShiftBadge.style.color = "#34d399";
    }
  }

  if (banner) {
    banner.style.display = isResting ? "flex" : "none";
  }

  applyShiftFormRestrictions(isResting);
}

function applyShiftFormRestrictions(isResting) {
  const formSubmitButtons = [
    "#card-topup-form button[type='submit']",
    "#given-amount-form button[type='submit']",
    "#daily-report-form button[type='submit']",
    "#cashier-handover-form button[type='submit']",
    "#cashier-distribute-sim-form button[type='submit']"
  ];

  formSubmitButtons.forEach(selector => {
    const btn = document.querySelector(selector);
    if (btn) {
      if (isResting) {
        btn.disabled = true;
        if (!btn.dataset.originalText) {
          btn.dataset.originalText = btn.innerHTML;
        }
        btn.innerHTML = "<span>🌙</span> Dam olish rejimidasiz (Amallar cheklangan)";
        btn.style.opacity = "0.55";
        btn.style.cursor = "not-allowed";
      } else {
        btn.disabled = false;
        if (btn.dataset.originalText) {
          btn.innerHTML = btn.dataset.originalText;
        }
        btn.style.opacity = "1";
        btn.style.cursor = "pointer";
      }
    }
  });
}

function updateSidebarContent() {
  if (!currentUser) return;

  const nameEl = document.getElementById("sidebar-user-name");
  const roleEl = document.getElementById("sidebar-user-role");
  const usdRateEl = document.getElementById("sidebar-usd-rate-text");

  if (usdRateEl && currentUsdRate) {
    usdRateEl.innerText = `1$ = ${formatNumberSpaces(currentUsdRate)} so'm`;
  }

  if (nameEl) {
    if (currentUser.role === "DEVELOPER") {
      nameEl.innerText = "💻 Dasturchi Admin";
      if (roleEl) {
        roleEl.style.display = "inline-flex";
        roleEl.className = "badge badge-developer";
        roleEl.innerText = "Dasturchi";
      }
    } else if (currentUser.role === "ADMIN" && (currentUser.full_name === "Bosh Rahbar" || !currentUser.full_name)) {
      nameEl.innerText = isRahbarCashierMode ? "💼 Kassir (Rejim)" : "👑 Bosh Rahbar";
      if (roleEl) roleEl.style.display = "none";
    } else {
      nameEl.innerText = currentUser.full_name;
      if (roleEl) roleEl.style.display = "inline-flex";
    }
  }

  if (roleEl && currentUser.role !== "ADMIN" && currentUser.role !== "DEVELOPER") {
    if (currentUser.role === "CASHIER") {
      roleEl.className = "badge badge-cashier";
      roleEl.innerText = "💼 Kassir";
    } else {
      roleEl.className = "badge badge-employee";
      roleEl.innerText = "👤 Xodim";
    }
  }

  updateDebtBadges();
  updateShiftStatusBadgesAndBanner();

  const navContainer = document.getElementById("sidebar-nav-list");
  if (!navContainer) return;

  let menuItems = [];

  if (currentUser.role === "DEVELOPER") {
    menuItems = [
      { id: "saas", icon: "🏢", title: "Firmalar (SaaS)", isAdmin: true }
    ];
  } else if (currentUser.role === "ADMIN") {
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
        { id: "location", icon: "📍", title: "Geolokatsiya nazorati", isAdmin: true },
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
  // SaaS: Agar kompaniya obunasi tugagan bo'lsa (Dasturchi Admin va UNLIMITED bundan mustasno)
  if (currentUser && currentUser.role !== "DEVELOPER" && !currentUser.is_super_admin && currentUser.company_plan !== "UNLIMITED") {
    if (currentUser.company_subscription_expires_at) {
      try {
        const expTime = new Date(currentUser.company_subscription_expires_at).getTime();
        if (Date.now() > expTime) {
          showSubscriptionExpiredModal(
            null,
            currentUser.company_name,
            formatDateOnly(currentUser.company_subscription_expires_at)
          );
          return;
        }
      } catch (e) {
        console.warn("Obuna muddati tekshirishda xatolik:", e);
      }
    }
  }

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

  const navCompBadge = document.getElementById("nav-company-badge");
  const navCompName = document.getElementById("nav-company-name");
  const sidebarCompBadge = document.getElementById("sidebar-company-badge");
  const sidebarCompName = document.getElementById("sidebar-company-name");

  const usdRateBadge = document.getElementById("usd-rate-badge");
  const rahbarCashierToggle = document.getElementById("btn-rahbar-cashier-toggle");

  const isDev = (currentUser.role === "DEVELOPER");

  // Dollar kursini faqat oddiy foydalanuvchilar va rahbar uchun yuklash
  if (!isDev) {
    loadUsdRate();
  }

  // Dasturchi Admin xodim ham, rahbar ham emas — alohida SaaS Platforma boshqaruvchisi!
  if (isDev) {
    if (navCompBadge) navCompBadge.style.display = "none";
    if (sidebarCompBadge) sidebarCompBadge.style.display = "none";
    if (usdRateBadge) usdRateBadge.style.display = "none";
    if (userNameEl) userNameEl.style.display = "none";
  } else {
    const compName = currentUser.company_name || "Bosh Tashkilot";
    if (navCompName) navCompName.innerText = compName;
    if (sidebarCompName) sidebarCompName.innerText = compName;
    if (navCompBadge) navCompBadge.style.display = "inline-flex";
    if (sidebarCompBadge) sidebarCompBadge.style.display = "inline-flex";
  }

  if (currentUser.role === "DEVELOPER") {
    roleBadge.className = "badge badge-developer";
    roleBadge.style.background = "";
    roleBadge.style.borderColor = "";
    roleBadge.style.color = "";
    roleBadge.innerText = "💻 Dasturchi Admin";
    debtBadge.style.display = "none";
    if (rahbarCashierToggle) rahbarCashierToggle.style.display = "none";

    isRahbarCashierMode = false;

    // Dasturchi Admin uchun BARCHA boshqa admin tablarini YASHIRISH!
    // Faqat bitta yagona "Firmalar (SaaS)" tabi ko'rinadi!
    document.querySelectorAll("#nav-tabs-admin .tab-btn").forEach(btn => {
      btn.style.display = (btn.id === "tab-btn-admin-saas") ? "inline-flex" : "none";
    });
    adminNav.style.display = "flex";
    adminNav.style.flexWrap = "wrap";
    employeeNav.style.display = "none";

    // Boshlang'ich va yagona oyna: Firmalar (SaaS)
    switchAdminTab("saas");
  } else if (currentUser.role === "ADMIN") {
    roleBadge.className = "badge badge-admin";
    roleBadge.innerText = "👑 Bosh Rahbar";
    debtBadge.style.display = "none";
    if (usdRateBadge) {
      usdRateBadge.style.display = "inline-flex";
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

    // Bosh Rahbar uchun barcha operatsion tablarni ko'rsatish, lekin SaaS tabini MUTLAQO YASHIRISH!
    document.querySelectorAll("#nav-tabs-admin .tab-btn").forEach(btn => {
      btn.style.display = (btn.id === "tab-btn-admin-saas") ? "none" : "inline-flex";
    });
    adminNav.style.display = "flex";
    adminNav.style.flexWrap = "nowrap";
    employeeNav.style.display = "none";

    // Rahbar uchun boshlang'ich oyna: Kunlik hisobotlarni qabul qilish
    switchAdminTab("reports");
  } else if (currentUser.role === "CASHIER") {
    roleBadge.className = "badge badge-cashier";
    roleBadge.innerText = "💼 Kassir";
    updateDebtBadges();
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
    updateDebtBadges();
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

  // Dam olish / ish rejimi va banner holatini yangilash
  updateShiftStatusBadgesAndBanner();

  // Yon menyuni ham foydalanuvchi ma'lumotlari bilan to'liq sinxronlash
  updateSidebarContent();

  // Bosh Rahbar va Dasturchi Admin o'zi kuzatilmaydi! Faqat xodimlar avtomatik kuzatiladi
  if (currentUser.role === "ADMIN" || currentUser.role === "DEVELOPER") {
    const locBadge = document.getElementById("nav-user-location");
    if (locBadge) locBadge.style.display = "none";
    stopAutoLocationTracking();
  } else {
    startAutoLocationTracking();
  }
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

  // Avvalgi geolokatsiya monitoring intervalini to'xtatish
  if (adminLocationPollInterval) {
    clearInterval(adminLocationPollInterval);
    adminLocationPollInterval = null;
  }

  if (tabName === "reports") loadAdminReports();
  else if (tabName === "analytics") loadAdminAnalytics();
  else if (tabName === "givens") loadAdminGivens();
  else if (tabName === "topups") loadAdminTopups();
  else if (tabName === "comparison") loadAdminComparison();
  else if (tabName === "users") loadAdminUsers();
  else if (tabName === "location") {
    loadAdminLocationTab();
    adminLocationPollInterval = setInterval(() => loadAdminLocationTab(false), 15000);
  }
  else if (tabName === "cashier") loadAdminCashierTab();
  else if (tabName === "sims") loadAdminSimsTab();
  else if (tabName === "rating") loadLeaderboard("monthly", "admin");
  else if (tabName === "audit") loadAdminAudit();
  else if (tabName === "saas") loadSaasCompanies();
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

  // Damda bo'lgan xodimlar uchun shakllarni cheklash
  applyShiftFormRestrictions(currentUser && currentUser.role !== "ADMIN" && currentUser.shift_status === "RESTING");

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
  if (currentUser && currentUser.role !== "ADMIN" && currentUser.shift_status === "RESTING") {
    showToast("Siz hozirda dam olish (damda) rejimidasiz! Amallarni bajarish cheklangan.", "warning");
    return;
  }
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
  if (currentUser && currentUser.role !== "ADMIN" && currentUser.shift_status === "RESTING") {
    showToast("Siz hozirda dam olish (damda) rejimidasiz! Amallarni bajarish cheklangan.", "warning");
    return;
  }
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
    document.getElementById("rep-given-amount").value = formatNumberSpaces(res.given_amount);

    // Xodimning qarzdorlik ma'lumotini sinxronlash va nishonlarni yangilash
    if (currentUser && currentUser.role !== "ADMIN") {
      currentUser.debt_amount = initialDebt;
      updateDebtBadges();
    }

    const snapGroup = document.getElementById("rep-group-debt-snapshot");
    const paidGroup = document.getElementById("rep-group-debt-paid");
    const debtPaidInput = document.getElementById("rep-debt-paid");
    const debtSnapInput = document.getElementById("rep-debt-snapshot");

    if (initialDebt > 0) {
      if (snapGroup) snapGroup.style.display = "";
      if (paidGroup) paidGroup.style.display = "";
      if (debtSnapInput) debtSnapInput.value = formatNumberSpaces(remainingDebt);
      if (debtPaidInput) {
        debtPaidInput.disabled = false;
        debtPaidInput.placeholder = "0 (kamida 50 000)";
      }
    } else {
      if (snapGroup) snapGroup.style.display = "none";
      if (paidGroup) paidGroup.style.display = "none";
      if (debtSnapInput) debtSnapInput.value = "0";
      if (debtPaidInput) {
        debtPaidInput.value = "0";
        debtPaidInput.disabled = true;
      }
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
      if (initialDebt > 0) {
        document.getElementById("rep-debt-paid").value = formatNumberSpaces(res.existing_report.debt_paid);
      } else {
        document.getElementById("rep-debt-paid").value = "0";
      }
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
  let debtPaid = 0;

  if (initialDebt > 0) {
    debtPaid = parseFormattedNumber(document.getElementById("rep-debt-paid")?.value || "0");
    // Agar qarz uchun to'lov mavjud qarzdorlikdan oshib ketsa, uni chegara qilish
    if (debtPaid > initialDebt) {
      debtPaid = initialDebt;
      const paidEl = document.getElementById("rep-debt-paid");
      if (paidEl) paidEl.value = formatNumberSpaces(debtPaid);
    }
    const remainingDebt = Math.max(0, initialDebt - debtPaid);
    const snapEl = document.getElementById("rep-debt-snapshot");
    if (snapEl) snapEl.value = formatNumberSpaces(remainingDebt);
  } else {
    debtPaid = 0;
    const snapEl = document.getElementById("rep-debt-snapshot");
    if (snapEl) snapEl.value = "0";
    const paidEl = document.getElementById("rep-debt-paid");
    if (paidEl) paidEl.value = "0";
  }

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
  if (currentUser && currentUser.role !== "ADMIN" && currentUser.shift_status === "RESTING") {
    showToast("Siz hozirda dam olish (damda) rejimidasiz! Amallarni bajarish cheklangan.", "warning");
    return;
  }

  const paynet = parseFormattedNumber(document.getElementById("rep-paynet").value);
  const leviy = parseFormattedNumber(document.getElementById("rep-leviy").value);
  const initialDebt = prefillData.debt_snapshot || 0;
  const debtPaid = (initialDebt > 0) ? parseFormattedNumber(document.getElementById("rep-debt-paid").value) : 0;

  if (initialDebt > 0 && debtPaid > 0) {
    const minAllowed = Math.min(50000, initialDebt);
    if (debtPaid < minAllowed) {
      showToast(`Qarz uchun to'lov eng kamida ${formatNumberSpaces(minAllowed)} so'm bo'lishi kerak!`, "danger");
      const paidInput = document.getElementById("rep-debt-paid");
      if (paidInput) paidInput.focus();
      return;
    }
  }

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
  if (currentUser && currentUser.role !== "ADMIN" && currentUser.shift_status === "RESTING") {
    showToast("Siz hozirda dam olish (damda) rejimidasiz! Kassa amallarini bajarish cheklangan.", "warning");
    return;
  }
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
  label: "Sanani tanlash"
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
    displayEl.textContent = adminReportDateFilter.label || "Sanani tanlash";
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
    label: "Sanani tanlash"
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
    adminReportDateFilter.label = "Sanani tanlash";
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
let adminComparisonCache = [];

async function loadAdminComparison() {
  try {
    const res = await api("/api/cashier/comparison");
    adminComparisonCache = res.data || [];
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

      const isResting = (u.shift_status === "RESTING");
      const shiftToggleBtn = (u.role !== "ADMIN" && u.is_active)
        ? (isResting
            ? `<button class="btn-success" style="font-size: 0.78rem; padding: 0.35rem 0.65rem;" onclick="toggleEmployeeShift(${u.id}, 'WORKING')">🟢 Ishga chiqarish</button>`
            : `<button class="btn-logout" style="border-color: #fbbf24; color: #fbbf24; font-size: 0.78rem; padding: 0.35rem 0.65rem;" onclick="toggleEmployeeShift(${u.id}, 'RESTING')">🌙 Damga chiqarish</button>`)
        : "";

      let statusHtml = '<span style="color: #f87171;">Bo\'shatilgan</span>';
      if (u.is_active) {
        if (u.role === "ADMIN") {
          statusHtml = '<span style="color: #34d399;">Faol</span>';
        } else if (isResting) {
          statusHtml = '<span class="badge" style="background: rgba(245, 158, 11, 0.18); border: 1px solid rgba(245, 158, 11, 0.45); color: #fbbf24; font-size: 0.75rem; padding: 0.2rem 0.55rem; font-weight: 600;">🌙 Damda</span>';
        } else {
          statusHtml = '<span class="badge" style="background: rgba(16, 185, 129, 0.18); border: 1px solid rgba(16, 185, 129, 0.45); color: #34d399; font-size: 0.75rem; padding: 0.2rem 0.55rem; font-weight: 600;">🟢 Ishda</span>';
        }
      }

      tbody.innerHTML += `
        <tr style="opacity: ${u.is_active ? 1 : 0.5};">
          <td><b>${u.full_name}</b></td>
          <td><code>${u.telegram_id}</code></td>
          <td><span class="badge ${u.role === 'ADMIN' ? 'badge-admin' : u.role === 'CASHIER' ? 'badge-cashier' : 'badge-employee'}">${formatRoleName(u.role)}</span></td>
          <td><b>${formatNumberSpaces(u.debt_amount ?? 0)} so'm</b></td>
          <td>${statusHtml}</td>
          <td style="display: flex; gap: 0.35rem; flex-wrap: wrap; align-items: center;">
            ${activeBtn}
            ${debtBtn}
            <button class="btn-logout" onclick="promptUpdatePassword(${u.id}, '${u.full_name}')">Parol</button>
            ${appointCashierBtn}
            ${shiftToggleBtn}
          </td>
        </tr>
      `;
    });
  } catch (e) {}
}

async function toggleEmployeeShift(userId, targetStatus) {
  const targetUser = (adminUsersCache || []).find(u => u.id === userId);
  const name = targetUser ? targetUser.full_name : "xodim";
  const isToRest = targetStatus === "RESTING";
  const confirmMsg = isToRest
    ? `Haqiqatan ham '${name}'ni dam olish (damda) rejimiga o'tkazmoqchimisiz?\n\n(Xodim ilovaga kira oladi, lekin amallarni bajara olmaydi)`
    : `Haqiqatan ham '${name}'ni faol ish rejimiga qaytarmoqchimisiz?`;
  if (!confirm(confirmMsg)) return;

  try {
    const res = await api(`/api/admin/users/${userId}/toggle-shift`, "POST", { shift_status: targetStatus });
    showToast(res.message || "Holat muvaffaqiyatli o'zgartirildi!", "success");
    loadAdminUsers();
    if (typeof loadAdminLocationTab === "function") loadAdminLocationTab(false);
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
let adminLeaderboardCache = { period: "monthly", data: [] };

async function loadLeaderboard(period = "monthly", viewType = "emp") {
  try {
    const res = await api(`/api/rating/leaderboard?period=${period}`);
    if (viewType === "admin") {
      adminLeaderboardCache = { period, data: res.data || [] };
    }
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

let adminSimBalancesCache = [];
let adminSimRecentCache = [];

async function loadSimSummary(prefix) {
  try {
    const res = await api("/api/sim-cards/summary");
    if (prefix === "admin") {
      adminSimBalancesCache = res.balances || [];
      adminSimRecentCache = res.recent || [];
    }
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
  if (currentUser && currentUser.role !== "ADMIN" && currentUser.shift_status === "RESTING") {
    showToast("Siz hozirda dam olish (damda) rejimidasiz! Sim-karta amallarini bajarish cheklangan.", "warning");
    return;
  }
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

// ==========================================
// ISH JOYI GEOLOKATSIYASI VA GEOFENCING (RAHBAR VA XODIM)
// ==========================================
let myAssignedWorkplace = null;
let locationWatchId = null;
let lastLocationPingTime = 0;
let lastPingedCoords = null;
let adminLocationPollInterval = null;
let adminEmployeesLocationCache = [];

function formatLocationTimeAgo(isoString) {
  if (!isoString) return "";
  try {
    const date = parseUtcDate(isoString);
    if (!date || typeof date === "string") return "";
    const now = new Date();
    const diffSec = Math.floor((now.getTime() - date.getTime()) / 1000);
    if (diffSec < 45) return "Hozirgina";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin} daqiqa oldin`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours} soat oldin`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays === 1) return "Kecha";
    if (diffDays < 7) return `${diffDays} kun oldin`;
    return formatTashkentDateTime(isoString);
  } catch (e) {
    return "";
  }
}

function calculateClientDistanceMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000.0;
  const phi1 = (lat1 * Math.PI) / 180.0;
  const phi2 = (lat2 * Math.PI) / 180.0;
  const deltaPhi = ((lat2 - lat1) * Math.PI) / 180.0;
  const deltaLambda = ((lon2 - lon1) * Math.PI) / 180.0;

  const a = (Math.sin(deltaPhi / 2.0) ** 2) +
            Math.cos(phi1) * Math.cos(phi2) * (Math.sin(deltaLambda / 2.0) ** 2);
  const c = 2.0 * Math.atan2(Math.sqrt(a), Math.sqrt(1.0 - a));
  return Math.round(R * c);
}

// ==========================================
// RAHBAR UCHUN: GEOLOKATSIYA MONITORINGI TABI
// ==========================================
async function loadAdminLocationTab(showToastNotice = false) {
  try {
    const res = await api("/api/location/employees");
    if (!res || !res.success) return;

    adminEmployeesLocationCache = res.employees || [];

    // 1. Statistika
    const total = adminEmployeesLocationCache.length;
    let configured = 0;
    let inside = 0;
    let outside = 0;

    adminEmployeesLocationCache.forEach(emp => {
      if (emp.is_workplace_configured) configured++;
      if (emp.is_within_hours && emp.is_inside === true) inside++;
      else if (emp.is_within_hours && emp.is_inside === false) outside++;
    });

    const totalEl = document.getElementById("geo-stat-total");
    const confEl = document.getElementById("geo-stat-configured");
    const inEl = document.getElementById("geo-stat-inside");
    const outEl = document.getElementById("geo-stat-outside");

    if (totalEl) totalEl.innerText = total;
    if (confEl) confEl.innerText = configured;
    if (inEl) inEl.innerText = inside;
    if (outEl) outEl.innerText = outside;

    // 2. Jadval
    const tbody = document.getElementById("admin-location-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (adminEmployeesLocationCache.length === 0) {
      tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Tizimda hozircha faol xodimlar mavjud emas.</td></tr>`;
      return;
    }

    adminEmployeesLocationCache.forEach(emp => {
      const isConfigured = emp.is_workplace_configured;
      const wpName = isConfigured ? `<b>${emp.workplace_name}</b>` : `<span style="color: #fbbf24; opacity: 0.85;">⚠️ Kordinata kiritilmagan</span>`;
      const wpCoords = isConfigured ? `<code>${emp.workplace_latitude.toFixed(5)}, ${emp.workplace_longitude.toFixed(5)}</code>` : `<span style="opacity: 0.5;">-</span>`;
      const wpRadius = isConfigured ? `<span class="badge" style="font-size: 0.75rem;">${emp.workplace_radius_meters} m</span>` : `<span style="opacity: 0.5;">-</span>`;

      const workStart = emp.work_start_time || '09:00';
      const workEnd = emp.work_end_time || '19:00';
      const isWithin = emp.is_within_hours !== false;
      const hoursBadge = `<span class="badge" style="background: ${isWithin ? 'rgba(99, 102, 241, 0.15)' : 'rgba(100, 116, 139, 0.15)'}; color: ${isWithin ? '#a5b4fc' : '#94a3b8'}; font-size: 0.75rem; white-space: nowrap;">⏰ ${workStart} - ${workEnd} ${isWithin ? '🟢' : '🌙'}</span>`;

      let distCell = "";
      let statusBadge = "";

      if (emp.shift_status === "RESTING") {
        distCell = `<span style="opacity: 0.85; font-size: 0.75rem; color: #fbbf24;">🌙 Damda (Rahbar belgilagan)</span>`;
        statusBadge = `<span class="badge" style="background: rgba(245, 158, 11, 0.18); border: 1px solid rgba(245, 158, 11, 0.45); color: #fbbf24; font-size: 0.75rem;">🌙 Damda</span>`;
      } else if (!isConfigured) {
        distCell = `<span style="opacity: 0.5;">-</span>`;
        statusBadge = `<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: #94a3b8; font-size: 0.75rem;">⚪ Belgilanmagan</span>`;
      } else if (!isWithin) {
        distCell = `<span style="opacity: 0.65; font-size: 0.75rem; color: #94a3b8;">🌙 Ish vaqti emas</span>`;
        statusBadge = `<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: #cbd5e1; font-size: 0.75rem;">🌙 Dam olish vaqti</span>`;
      } else if (emp.last_distance_meters !== null && emp.last_distance_meters !== undefined) {
        const distM = Math.round(emp.last_distance_meters);
        const distText = distM >= 1000 ? (distM / 1000).toFixed(1) + " km" : distM + " m";
        if (emp.is_inside) {
          distCell = `<b style="color: #34d399;">📍 ${distText}</b>`;
          statusBadge = `<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 0.75rem;">🟢 Ish joyida (${distText})</span>`;
        } else {
          distCell = `<b style="color: #f87171;">📍 ${distText}</b>`;
          statusBadge = `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 0.75rem;">🔴 Tashqarida (${distText})</span>`;
        }
      } else {
        distCell = `<span style="opacity: 0.6; font-size: 0.78rem;">Kutilmoqda...</span>`;
        statusBadge = `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; font-size: 0.75rem;">⏳ Aniqlanmoqda</span>`;
      }

      const timeAgo = formatLocationTimeAgo(emp.last_location_updated_at);
      const exactTime = formatTashkentDateTime(emp.last_location_updated_at, true);
      const timeCell = timeAgo 
        ? `<span style="font-size: 0.75rem; color: var(--text-muted); cursor: help;" title="Aniq Toshkent vaqti: ${exactTime}">🕒 ${timeAgo}</span>` 
        : `<span style="opacity: 0.5; font-size: 0.75rem;">-</span>`;

      // Xaritada ko'rish tugmasi (xodimning oxirgi jonli lokatsiyasi)
      const mapBtn = (emp.last_latitude && emp.last_longitude)
        ? `<a href="https://www.google.com/maps?q=${emp.last_latitude},${emp.last_longitude}" target="_blank" rel="noopener noreferrer" class="btn-logout" style="padding: 3px 7px; font-size: 0.72rem; text-decoration: none; display: inline-flex; align-items: center; gap: 3px;" title="Xodimning joylashuvi xaritada">🗺️ Xodim</a>`
        : "";

      // Ish joyini xaritada ko'rish tugmasi (agar belgilangan bo'lsa)
      const wpMapBtn = isConfigured
        ? `<a href="https://www.google.com/maps?q=${emp.workplace_latitude},${emp.workplace_longitude}" target="_blank" rel="noopener noreferrer" class="btn-logout" style="padding: 3px 7px; font-size: 0.72rem; text-decoration: none; display: inline-flex; align-items: center; gap: 3px;" title="Ish joyi manzili">🏢 Ish joyi</a>`
        : "";

      // Ish joyini tozalash tugmasi
      const clearBtn = isConfigured
        ? `<button type="button" class="btn-logout" style="padding: 3px 7px; font-size: 0.72rem; color: #f87171; border-color: rgba(239, 68, 68, 0.35);" onclick="handleClearEmployeeWorkplace(${emp.id}, '${emp.full_name}')" title="Kordinatani tozalash">🗑️</button>`
        : "";

      tbody.innerHTML += `
        <tr>
          <td><b>${emp.full_name}</b></td>
          <td><code>${emp.telegram_id}</code></td>
          <td><span class="badge ${emp.role === 'CASHIER' ? 'badge-cashier' : 'badge-employee'}">${formatRoleName(emp.role)}</span></td>
          <td>${wpName}</td>
          <td>${hoursBadge}</td>
          <td>${wpCoords}</td>
          <td>${wpRadius}</td>
          <td>${distCell}</td>
          <td>${statusBadge}</td>
          <td>${timeCell}</td>
          <td>
            <div style="display: flex; gap: 4px; align-items: center; flex-wrap: wrap;">
              <button type="button" class="btn-primary" style="padding: 3px 8px; font-size: 0.75rem;" onclick="openSetEmployeeLocationModal(${emp.id})">
                ${isConfigured ? '✏️ Sozlash' : '📍 Kordinata & Vaqt'}
              </button>
              ${mapBtn}
              ${wpMapBtn}
              ${clearBtn}
            </div>
          </td>
        </tr>
      `;
    });

    if (showToastNotice) {
      showToast("Xodimlar geolokatsiyasi yangilandi", "info");
    }
  } catch (err) {
    console.warn("Geolokatsiya ma'lumotlarini yuklashda xatolik:", err);
  }
}

function openSetEmployeeLocationModal(userId) {
  const emp = (adminEmployeesLocationCache || []).find(u => u.id === userId);
  if (!emp) return;

  const modal = document.getElementById("set-employee-location-modal");
  if (!modal) return;

  document.getElementById("modal-emp-id").value = emp.id;
  document.getElementById("modal-emp-name-display").innerText = `${emp.full_name} (TG: ${emp.telegram_id})`;
  document.getElementById("modal-emp-wp-name").value = emp.workplace_name || `${emp.full_name} ish joyi`;
  document.getElementById("modal-emp-wp-lat").value = emp.workplace_latitude ?? "";
  document.getElementById("modal-emp-wp-lon").value = emp.workplace_longitude ?? "";
  document.getElementById("modal-emp-wp-radius").value = emp.workplace_radius_meters || 50;
  document.getElementById("modal-emp-work-start").value = emp.work_start_time || "09:00";
  document.getElementById("modal-emp-work-end").value = emp.work_end_time || "19:00";

  modal.style.display = "flex";
}

function closeSetEmployeeLocationModal() {
  const modal = document.getElementById("set-employee-location-modal");
  if (modal) modal.style.display = "none";
}

function handleEmployeeLocationModalOverlayClick(e) {
  if (e.target && e.target.id === "set-employee-location-modal") {
    closeSetEmployeeLocationModal();
  }
}

async function handleSetEmployeeLocationSubmit(e) {
  if (e) e.preventDefault();
  const userId = parseInt(document.getElementById("modal-emp-id").value, 10);
  const name = document.getElementById("modal-emp-wp-name")?.value?.trim() || "Ish joyi";
  const lat = parseFloat(document.getElementById("modal-emp-wp-lat")?.value);
  const lon = parseFloat(document.getElementById("modal-emp-wp-lon")?.value);
  const radius = parseInt(document.getElementById("modal-emp-wp-radius")?.value || "50", 10);
  const workStart = document.getElementById("modal-emp-work-start")?.value || "09:00";
  const workEnd = document.getElementById("modal-emp-work-end")?.value || "19:00";

  if (isNaN(lat) || isNaN(lon)) {
    showToast("Kenglik va uzunlik to'g'ri kiritilishi shart!", "danger");
    return;
  }

  try {
    const res = await api("/api/location/set-employee-workplace", "POST", {
      user_id: userId,
      workplace_name: name,
      latitude: lat,
      longitude: lon,
      radius_meters: radius,
      work_start_time: workStart,
      work_end_time: workEnd
    });

    showToast(res.message || "Xodim uchun kordinata va ish vaqti saqlandi!", "success");
    closeSetEmployeeLocationModal();
    await loadAdminLocationTab(false);
  } catch (err) {
    showToast("Xatolik: " + err.message, "danger");
  }
}

async function handleFillEmployeeCurrentLocationToModal() {
  const userId = parseInt(document.getElementById("modal-emp-id").value, 10);
  const btn = document.getElementById("btn-modal-fill-emp-gps");
  const origText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = "<span>⏳</span> Xodim kordinatasi tekshirilmoqda...";
  }

  try {
    const res = await api("/api/location/employees");
    if (res && res.employees) {
      adminEmployeesLocationCache = res.employees;
    }

    const emp = (adminEmployeesLocationCache || []).find(u => u.id === userId);
    if (!emp) {
      showToast("Xodim ma'lumotlari topilmadi", "danger");
      return;
    }

    if (emp.last_latitude && emp.last_longitude) {
      document.getElementById("modal-emp-wp-lat").value = emp.last_latitude.toFixed(6);
      document.getElementById("modal-emp-wp-lon").value = emp.last_longitude.toFixed(6);
      const timeAgo = formatLocationTimeAgo(emp.last_location_updated_at);
      const timeText = timeAgo ? ` (${timeAgo})` : "";
      showToast(`✅ ${emp.full_name}ning ayni damdagi turgan joyi olindi!${timeText}`, "success");
    } else {
      showToast(`⚠️ ${emp.full_name} hali dasturga kirmagan yoki GPS signali kelmagan. Xodim telefonida ilovani ochgach, qayta bosing.`, "danger");
    }
  } catch (err) {
    showToast("Xatolik: " + err.message, "danger");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}

async function handleClearEmployeeWorkplace(userId, fullName) {
  if (!confirm(`Haqiqatan ham '${fullName}' xodimining ish joyi koordinatasini tozalamoqchimisiz?`)) return;
  try {
    const res = await api(`/api/location/clear-employee-workplace/${userId}`, "POST");
    showToast(res.message, "success");
    await loadAdminLocationTab(false);
  } catch (err) {
    showToast("Xatolik: " + err.message, "danger");
  }
}

// ==========================================
// XODIM UCHUN: AVTOMATIK GEOLOKATSIYA KUZATUVI
// Xodim HECH NARSA kiritmaydi!
// ==========================================
function updateNavbarLocationBadge(distM, isInside, isConfigured = true) {
  const badge = document.getElementById("nav-user-location");
  if (!badge) return;

  if (currentUser && currentUser.role === "ADMIN") {
    badge.style.display = "none";
    return;
  }

  badge.style.display = "inline-flex";

  if (currentUser && currentUser.shift_status === "RESTING") {
    badge.style.background = "rgba(245, 158, 11, 0.15)";
    badge.style.color = "#fbbf24";
    badge.style.border = "1px solid rgba(245, 158, 11, 0.4)";
    badge.innerHTML = "<span>🌙</span> Dam olish (damda)";
    badge.title = "Rahbar sizni dam olish rejimiga o'tkazgan.";
    return;
  }

  if (!isConfigured) {
    badge.style.background = "rgba(100, 116, 139, 0.2)";
    badge.style.color = "#94a3b8";
    badge.style.border = "1px solid rgba(100, 116, 139, 0.4)";
    badge.innerHTML = "<span>📍</span> Ish joyi belgilanmagan";
    badge.title = "Rahbar hali sizga ish joyi koordinatasini biriktirmagan";
    return;
  }

  // Agar hozir xodimning ish soatlari bo'lmasa:
  if (myAssignedWorkplace && myAssignedWorkplace.is_within_hours === false) {
    badge.style.background = "rgba(100, 116, 139, 0.2)";
    badge.style.color = "#cbd5e1";
    badge.style.border = "1px solid rgba(100, 116, 139, 0.4)";
    const hours = (myAssignedWorkplace.work_start_time || '09:00') + ' - ' + (myAssignedWorkplace.work_end_time || '19:00');
    badge.innerHTML = `<span>🌙</span> Dam olish (${hours})`;
    badge.title = `Ish vaqti emas (${hours}). Geolokatsiya kuzatuvi to'xtatilgan.`;
    return;
  }

  if (distM === null || distM === undefined) {
    badge.style.background = "rgba(100, 116, 139, 0.2)";
    badge.style.color = "#94a3b8";
    badge.style.border = "1px solid rgba(100, 116, 139, 0.4)";
    badge.innerHTML = "<span>📍</span> Masofa aniqlanmoqda...";
    return;
  }

  const distText = distM >= 1000 ? (distM / 1000).toFixed(1) + " km" : distM + " m";

  if (isInside) {
    badge.style.background = "rgba(16, 185, 129, 0.2)";
    badge.style.color = "#34d399";
    badge.style.border = "1px solid rgba(16, 185, 129, 0.4)";
    badge.innerHTML = `<span>📍</span> ${distText} (Ish joyida ✅)`;
    badge.title = `Siz ish joyingizdasiz (${distText})`;
  } else {
    badge.style.background = "rgba(239, 68, 68, 0.15)";
    badge.style.color = "#f87171";
    badge.style.border = "1px solid rgba(239, 68, 68, 0.35)";
    badge.innerHTML = `<span>📍</span> ${distText} (Tashqarida ⚠️)`;
    badge.title = `Siz ish joyingizdan ${distText} uzoqlikdasiz`;
  }
}

async function startAutoLocationTracking() {
  if (!authToken || !currentUser) return;
  // Bosh Rahbar hech qachon kuzatilmaydi!
  if (currentUser.role === "ADMIN") {
    const badge = document.getElementById("nav-user-location");
    if (badge) badge.style.display = "none";
    return;
  }

  if (locationWatchId !== null) return;

  if (!("geolocation" in navigator)) {
    console.warn("Geolocation brauzerda qo'llab-quvvatlanmaydi.");
    return;
  }

  // Xodimning o'ziga biriktirilgan ish joyi kordinatalarini olish
  try {
    const res = await api("/api/location/my-workplace");
    if (res && res.success) {
      myAssignedWorkplace = res;
    }
  } catch (e) {
    console.warn("Xodim ish joyini yuklashda xatolik:", e);
  }

  const onPositionSuccess = async (pos) => {
    const lat = pos.coords.latitude;
    const lon = pos.coords.longitude;
    const now = Date.now();

    // Lokal masofani hisoblab, zudlik bilan navbar badgeni yangilash
    if (myAssignedWorkplace && myAssignedWorkplace.is_configured) {
      const localDist = calculateClientDistanceMeters(
        myAssignedWorkplace.latitude,
        myAssignedWorkplace.longitude,
        lat,
        lon
      );
      const isInside = localDist <= (myAssignedWorkplace.radius_meters || 50);
      updateNavbarLocationBadge(localDist, isInside, true);
    } else {
      updateNavbarLocationBadge(null, false, false);
    }

    // Backend serverga ping yuborish mezonlari (har 30 soniyada yoki 20m siljiganda)
    let shouldPing = false;
    if (!lastPingedCoords || (now - lastLocationPingTime > 30000)) {
      shouldPing = true;
    } else {
      const distFromLastPing = calculateClientDistanceMeters(
        lastPingedCoords.latitude,
        lastPingedCoords.longitude,
        lat,
        lon
      );
      if (distFromLastPing >= 20) {
        shouldPing = true;
      }
    }

    if (shouldPing && authToken) {
      lastLocationPingTime = now;
      lastPingedCoords = { latitude: lat, longitude: lon };
      try {
        const pingRes = await api("/api/location/ping", "POST", { latitude: lat, longitude: lon });
        if (pingRes && pingRes.success) {
          if (pingRes.is_within_hours === false) {
            if (myAssignedWorkplace) myAssignedWorkplace.is_within_hours = false;
            updateNavbarLocationBadge(null, false, true);
          } else if (pingRes.is_configured) {
            if (myAssignedWorkplace) myAssignedWorkplace.is_within_hours = true;
            updateNavbarLocationBadge(
              Math.round(pingRes.distance_meters),
              pingRes.is_inside,
              true
            );
          }
        }
      } catch (err) {
        console.warn("Lokatsiya serverga yuborilmadi:", err.message);
      }
    }
  };

  const onPositionError = (err) => {
    console.warn("GPS lokatsiya xatoligi:", err.message);
    const badge = document.getElementById("nav-user-location");
    if (!badge || (currentUser && currentUser.role === "ADMIN")) return;
    badge.style.display = "inline-flex";
    if (err.code === 1) { // PERMISSION_DENIED
      badge.style.background = "rgba(245, 158, 11, 0.15)";
      badge.style.color = "#fbbf24";
      badge.style.border = "1px solid rgba(245, 158, 11, 0.35)";
      badge.innerHTML = "<span>📍</span> GPS ruxsati kerak";
      badge.title = "Avtomatik masofa hisoblash uchun brauzerda lokatsiyaga ruxsat bering";
    }
  };

  const geoOptions = {
    enableHighAccuracy: true,
    timeout: 20000,
    maximumAge: 10000
  };

  navigator.geolocation.getCurrentPosition(onPositionSuccess, onPositionError, geoOptions);

  try {
    locationWatchId = navigator.geolocation.watchPosition(onPositionSuccess, onPositionError, geoOptions);
  } catch (e) {
    console.warn("watchPosition xatosi:", e);
  }
}

function stopAutoLocationTracking() {
  if (locationWatchId !== null && navigator.geolocation) {
    navigator.geolocation.clearWatch(locationWatchId);
    locationWatchId = null;
  }
  const badge = document.getElementById("nav-user-location");
  if (badge) badge.style.display = "none";
  lastLocationPingTime = 0;
  lastPingedCoords = null;
  myAssignedWorkplace = null;
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && authToken && currentUser && currentUser.role !== "ADMIN" && navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(() => {}, () => {}, { enableHighAccuracy: true, timeout: 10000 });
  }
});

// ==========================================
// SAAS MULTI-TENANT MANAGEMENT (Dasturchi Admin)
// ==========================================

async function loadSaasCompanies() {
  if (!currentUser || (!currentUser.is_super_admin && currentUser.role !== "DEVELOPER")) return;

  initSaasCreateFormDate();

  const tbody = document.getElementById("saas-companies-tbody");
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: #94a3b8; padding: 2rem;">Ma'lumotlar yuklanmoqda...</td></tr>`;
  }

  try {
    const res = await api("/api/saas/companies");
    if (!res.success || !res.data) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: #ef4444; padding: 2rem;">Yuklashda xatolik yuz berdi.</td></tr>`;
      return;
    }

    const companies = res.data;

    // Statistikalar
    const totalCompanies = companies.length;
    const activeCompanies = companies.filter(c => c.is_active).length;
    const totalUsers = companies.reduce((sum, c) => sum + (c.employees_count || 0), 0);
    const totalReports = companies.reduce((sum, c) => sum + (c.reports_count || 0), 0);

    const statTotalEl = document.getElementById("saas-stat-total-companies");
    const statActiveEl = document.getElementById("saas-stat-active-companies");
    const statUsersEl = document.getElementById("saas-stat-total-users");
    const statReportsEl = document.getElementById("saas-stat-total-reports");

    if (statTotalEl) statTotalEl.innerText = totalCompanies;
    if (statActiveEl) statActiveEl.innerText = activeCompanies;
    if (statUsersEl) statUsersEl.innerText = totalUsers;
    if (statReportsEl) statReportsEl.innerText = totalReports;

    if (!tbody) return;
    if (companies.length === 0) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: #94a3b8; padding: 2rem;">Hozircha firmalar mavjud emas.</td></tr>`;
      return;
    }

    tbody.innerHTML = companies.map(c => {
      const isMain = (c.id === 1);
      const statusBadge = c.is_active 
        ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.35); font-weight: 600;">🟢 Faol</span>`
        : `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.35); font-weight: 600;">🔴 To'xtatilgan</span>`;

      let expiryText = "";
      if (c.plan === "UNLIMITED") {
        expiryText = `<span class="badge" style="background: rgba(99, 102, 241, 0.15); color: #6366f1; font-weight: 600;">Cheksiz (Unlimited)</span>`;
      } else if (c.days_left !== null && c.days_left !== undefined) {
        if (c.days_left <= 0) {
          expiryText = `<b style="color: #ef4444;">Tugagan ⚠️</b>`;
        } else if (c.days_left > 365) {
          const yearsLeft = (c.days_left / 365).toFixed(1);
          expiryText = `<span style="color: #10b981; font-weight: 700;">${yearsLeft} yil qoldi (${c.days_left} kun) 🌟</span>`;
        } else if (c.days_left <= 5) {
          expiryText = `<b style="color: #f59e0b;">${c.days_left} kun qoldi ⏳</b>`;
        } else {
          expiryText = `<span style="color: #10b981; font-weight: 600;">${c.days_left} kun qoldi</span>`;
        }
      } else {
        expiryText = "-";
      }

      let planBadge = "";
      if (c.plan === "UNLIMITED") {
        planBadge = `<span class="badge" style="background: rgba(147, 51, 234, 0.15); color: #a855f7; border: 1px solid rgba(147, 51, 234, 0.35); font-weight: 700;">UNLIMITED ♾️</span>`;
      } else if (c.plan === "5_YEARS") {
        planBadge = `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.35); font-weight: 700;">5 YIL 🌟</span>`;
      } else {
        planBadge = `<span class="badge" style="background: rgba(236, 72, 153, 0.15); color: #db2777; border: 1px solid rgba(236, 72, 153, 0.35); font-weight: 700;">${c.plan}</span>`;
      }

      // Amallar tugmalari
      const safeCompName = (c.name || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      let actionsHtml = `<div style="display: flex; gap: 0.4rem; align-items: center; flex-wrap: wrap;">`;
      if (!isMain && c.plan !== "UNLIMITED") {
        actionsHtml += `
          <button type="button" class="btn btn-primary" style="font-size: 0.72rem; padding: 0.25rem 0.5rem; background: linear-gradient(135deg, #6366f1, #8b5cf6); border: none; font-weight: 600;" onclick="openSaasExtendModal(${c.id}, '${safeCompName}', '${c.subscription_expires_at || ''}')" title="Sanani belgilash">
            📅 Sanani uzaytirish
          </button>
          <button type="button" class="btn btn-secondary" style="font-size: 0.72rem; padding: 0.25rem 0.5rem;" onclick="extendCompanySubscription(${c.id}, 30)" title="+30 kun qo'shish">
            +30 kun
          </button>
        `;
      }
      if (!isMain) {
        if (c.is_active) {
          actionsHtml += `
            <button type="button" class="btn btn-danger" style="font-size: 0.72rem; padding: 0.25rem 0.5rem; background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4);" onclick="toggleCompanyActive(${c.id}, true)">
              Bloklash
            </button>
          `;
        } else {
          actionsHtml += `
            <button type="button" class="btn btn-success" style="font-size: 0.72rem; padding: 0.25rem 0.5rem; background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4);" onclick="toggleCompanyActive(${c.id}, false)">
              Faollashtirish
            </button>
          `;
        }
      } else {
        actionsHtml += `<span style="font-size: 0.75rem; color: #94a3b8;">Bosh Tashkilot (Daxlsiz)</span>`;
      }
      actionsHtml += `</div>`;

      return `
        <tr>
          <td><b>#${c.id}</b></td>
          <td>
            <b style="color: var(--text-main); font-size: 0.95rem; display: block;">${escapeHtml(c.name)}</b>
            <span style="font-size: 0.75rem; color: #94a3b8;">${escapeHtml(c.slug)}</span>
          </td>
          <td>
            <div style="font-weight: 600; color: var(--text-main);">${escapeHtml(c.owner_name)}</div>
            <code style="font-size: 0.75rem; color: #6366f1;">TG: ${c.owner_telegram_id || '-'}</code>
          </td>
          <td>
            <code style="font-size: 0.75rem;">${escapeHtml(c.telegram_group_id || 'Mavjud emas')}</code>
          </td>
          <td>
            ${planBadge}
            ${!isMain ? `<button type="button" onclick="promptChangeCompanyPlan(${c.id}, '${c.plan}')" style="background: none; border: none; font-size: 0.72rem; color: #818cf8; text-decoration: underline; cursor: pointer; padding: 0; display: block; margin-top: 3px;">🔄 Tarifni o'zgartirish</button>` : ''}
          </td>
          <td>
            <div>${expiryText}</div>
            ${c.subscription_expires_at ? `<span style="font-size: 0.72rem; color: var(--text-sub); font-weight: 600; display: block; margin-top: 2px;">📅 ${formatDateOnly(c.subscription_expires_at)} gacha</span>` : ''}
          </td>
          <td>
            <b style="color: #6366f1;">${c.employees_count || 0} / ${c.max_employees || 20} ta</b>
            ${c.cashiers_count ? `<span style="font-size: 0.75rem; color: #f59e0b; display: block;">(${c.cashiers_count} kassir)</span>` : ''}
            ${!isMain ? `<button type="button" onclick="promptChangeCompanyLimit(${c.id}, ${c.max_employees || 20})" style="background: none; border: none; font-size: 0.72rem; color: #818cf8; text-decoration: underline; cursor: pointer; padding: 0; display: block; margin-top: 3px;">⚙️ Limitni o'zgartirish</button>` : ''}
          </td>
          <td><b>${c.reports_count || 0} ta</b></td>
          <td>${statusBadge}</td>
          <td>${actionsHtml}</td>
        </tr>
      `;
    }).join("");

  } catch (e) {
    console.error("loadSaasCompanies xatosi:", e);
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; color: #ef4444; padding: 2rem;">${escapeHtml(e.message || "Server bilan aloqada xatolik yuz berdi.")}</td></tr>`;
    }
  }
}

function handleSaasPlanChange(plan) {
  const dateContainer = document.getElementById("saas-new-date-container");
  const dateInput = document.getElementById("saas-new-expires-date");
  if (!dateContainer || !dateInput) return;
  if (plan === "UNLIMITED") {
    dateContainer.style.display = "none";
    dateInput.required = false;
    dateInput.value = "";
  } else if (plan === "5_YEARS") {
    dateContainer.style.display = "block";
    dateInput.required = true;
    const d = new Date();
    d.setFullYear(d.getFullYear() + 5);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    dateInput.value = `${y}-${m}-${day}`;
  } else {
    dateContainer.style.display = "block";
    dateInput.required = true;
    const d = new Date();
    d.setDate(d.getDate() + 30);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    dateInput.value = `${y}-${m}-${day}`;
  }
}

function initSaasCreateFormDate() {
  const dateInput = document.getElementById("saas-new-expires-date");
  if (!dateInput) return;
  const d = new Date();
  const todayStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  dateInput.min = todayStr;

  const planSelect = document.getElementById("saas-new-plan");
  if (planSelect && planSelect.value === "5_YEARS") {
    d.setFullYear(d.getFullYear() + 5);
    const fiveYearStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    dateInput.value = fiveYearStr;
    return;
  }

  if (!dateInput.value) {
    d.setDate(d.getDate() + 30);
    const nextMonthStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    dateInput.value = nextMonthStr;
  }
}

async function handleCreateCompanySubmit(event) {
  event.preventDefault();
  const nameInput = document.getElementById("saas-new-name");
  const ownerNameInput = document.getElementById("saas-new-owner-name");
  const ownerTgInput = document.getElementById("saas-new-owner-tg");
  const passwordInput = document.getElementById("saas-new-password");
  const groupIdInput = document.getElementById("saas-new-group-id");
  const dateInput = document.getElementById("saas-new-expires-date");
  const planSelect = document.getElementById("saas-new-plan");
  const maxEmpInput = document.getElementById("saas-new-max-employees");

  const name = nameInput?.value.trim();
  const ownerName = ownerNameInput?.value.trim();
  const ownerTg = parseInt(ownerTgInput?.value);
  const initialPassword = passwordInput?.value.trim() || null;
  const groupId = groupIdInput?.value.trim() || null;
  const plan = planSelect?.value || "STANDARD";
  const expiresDate = dateInput?.value || null;
  const maxEmployees = parseInt(maxEmpInput?.value || "20") || 20;

  if (!name || !ownerName || !ownerTg) {
    showToast("Iltimos, barcha majburiy maydonlarni to'ldiring!", "error");
    return;
  }

  if (plan === "STANDARD" && !expiresDate) {
    showToast("Iltimos, firmaning amal qilish sanasini belgilang!", "warning");
    return;
  }

  try {
    const res = await api("/api/saas/companies/create", "POST", {
      name: name,
      owner_name: ownerName,
      owner_telegram_id: ownerTg,
      initial_password: initialPassword,
      telegram_group_id: groupId,
      expires_date: plan === "STANDARD" ? expiresDate : null,
      plan: plan,
      max_employees: maxEmployees
    });

    if (res.success) {
      showToast(res.message || "Firma muvaffaqiyatli ro'yxatdan o'tkazildi!", "success");
      document.getElementById("saas-create-company-form")?.reset();
      initSaasCreateFormDate();
      loadSaasCompanies();
    } else {
      showToast(res.detail || res.message || "Xatolik yuz berdi!", "error");
    }
  } catch (e) {
    showToast(e.message || "Server bilan aloqa xatosi!", "error");
  }
}

let saasExtendingCompanyId = null;

function openSaasExtendModal(companyId, companyName, currentExpiresAt) {
  saasExtendingCompanyId = companyId;
  const modal = document.getElementById("saas-extend-modal");
  const nameEl = document.getElementById("saas-extend-modal-comp-name");
  const curDateEl = document.getElementById("saas-extend-modal-cur-date");
  const dateInput = document.getElementById("saas-extend-new-date");

  if (nameEl) nameEl.innerText = companyName;
  if (curDateEl) {
    curDateEl.innerText = currentExpiresAt ? `${formatDateOnly(currentExpiresAt)} gacha` : "Muddatsiz / Belgilanmagan";
  }

  let baseDate = new Date();
  if (currentExpiresAt) {
    try {
      const curD = new Date(currentExpiresAt);
      if (curD > baseDate) {
        baseDate = curD;
      }
    } catch (e) {}
  }
  baseDate.setDate(baseDate.getDate() + 30);
  const y = baseDate.getFullYear();
  const m = String(baseDate.getMonth() + 1).padStart(2, "0");
  const d = String(baseDate.getDate()).padStart(2, "0");

  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  if (dateInput) {
    dateInput.min = todayStr;
    dateInput.value = `${y}-${m}-${d}`;
  }

  if (modal) modal.style.display = "flex";
}

function closeSaasExtendModal() {
  const modal = document.getElementById("saas-extend-modal");
  if (modal) modal.style.display = "none";
  saasExtendingCompanyId = null;
}

function handleSaasExtendModalOverlayClick(e) {
  if (e.target.id === "saas-extend-modal") {
    closeSaasExtendModal();
  }
}

function setExtendModalDays(days) {
  const dateInput = document.getElementById("saas-extend-new-date");
  if (!dateInput) return;
  const d = new Date();
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  dateInput.value = `${y}-${m}-${day}`;
}

function setExtendYears(years) {
  const dateInput = document.getElementById("saas-extend-new-date");
  if (!dateInput) return;
  const d = new Date();
  d.setFullYear(d.getFullYear() + years);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  dateInput.value = `${y}-${m}-${day}`;
}

async function handleSaasExtendFormSubmit(event) {
  event.preventDefault();
  if (!saasExtendingCompanyId) return;
  const dateInput = document.getElementById("saas-extend-new-date");
  const newDate = dateInput?.value;
  if (!newDate) {
    showToast("Iltimos, yangi amal qilish sanasini tanlang!", "warning");
    return;
  }

  try {
    const res = await api(`/api/saas/companies/${saasExtendingCompanyId}/extend`, "POST", {
      new_expires_date: newDate
    });
    if (res.success) {
      showToast(res.message || "Firma obunasi muvaffaqiyatli uzaytirildi!", "success");
      closeSaasExtendModal();
      loadSaasCompanies();
    } else {
      showToast(res.detail || "Xatolik yuz berdi!", "error");
    }
  } catch (e) {
    showToast(e.message || "Server xatosi!", "error");
  }
}

async function toggleCompanyActive(companyId, currentIsActive) {
  const actionText = currentIsActive ? "to'xtatish (bloklash)" : "faollashtirish";
  if (!confirm(`Haqiqatan ham #${companyId} firmadagi xizmatni ${actionText}ni xohlaysizmi?`)) {
    return;
  }

  try {
    const res = await api(`/api/saas/companies/${companyId}/toggle-active`, "POST");
    if (res.success) {
      showToast(res.message, "success");
      loadSaasCompanies();
    } else {
      showToast(res.detail || "Xatolik yuz berdi!", "error");
    }
  } catch (e) {
    showToast(e.message || "Server xatosi!", "error");
  }
}

async function extendCompanySubscription(companyId, days = 30) {
  if (!confirm(`Firma obunasini +${days} kunga uzaytirishni tasdiqlaysizmi?`)) {
    return;
  }

  try {
    const res = await api(`/api/saas/companies/${companyId}/extend`, "POST", { days: days });
    if (res.success) {
      showToast(res.message, "success");
      loadSaasCompanies();
    } else {
      showToast(res.detail || "Xatolik yuz berdi!", "error");
    }
  } catch (e) {
    showToast(e.message || "Server xatosi!", "error");
  }
}

// ==========================================
// OBUNA MUDDATI TUGAGANLIGI (Client Device Overlay)
// ==========================================

let subscriptionAutoCheckTimer = null;

function showSubscriptionExpiredModal(message = null, compName = null, expDate = null) {
  const modal = document.getElementById("subscription-expired-modal");
  if (!modal) return;

  const compNameEl = document.getElementById("expired-modal-comp-name");
  const expDateEl = document.getElementById("expired-modal-exp-date");

  const companyName = compName || (currentUser && currentUser.company_name) || "Kompaniyangiz";
  let expirationDate = expDate;
  if (!expirationDate && currentUser && currentUser.company_subscription_expires_at) {
    expirationDate = formatDateOnly(currentUser.company_subscription_expires_at);
  }
  if (!expirationDate) expirationDate = "Muddati tugagan";

  if (compNameEl) compNameEl.innerText = companyName;
  if (expDateEl) expDateEl.innerText = `${expirationDate} da tugagan`;

  modal.style.display = "flex";

  // Har 15 soniyada avtomatik tekshirib turish
  if (!subscriptionAutoCheckTimer) {
    subscriptionAutoCheckTimer = setInterval(() => {
      checkSubscriptionStatusAgain(true);
    }, 15000);
  }
}

function hideSubscriptionExpiredModal() {
  const modal = document.getElementById("subscription-expired-modal");
  if (modal) modal.style.display = "none";
  if (subscriptionAutoCheckTimer) {
    clearInterval(subscriptionAutoCheckTimer);
    subscriptionAutoCheckTimer = null;
  }
}

async function checkSubscriptionStatusAgain(silent = false) {
  if (!authToken) {
    hideSubscriptionExpiredModal();
    showLoginModal();
    return;
  }

  try {
    const res = await api("/api/auth/me");
    if (res && res.success && res.user) {
      currentUser = res.user;
      hideSubscriptionExpiredModal();
      try {
        renderApp();
      } catch (e) {
        console.error("renderApp error:", e);
      }
      showToast("Obunangiz muvaffaqiyatli uzaytirildi! Tizimdan to'liq foydalanishingiz mumkin.", "success");
    }
  } catch (err) {
    if (!silent) {
      showToast("Obuna muddati hali uzaytirilmadi. Iltimos, Dasturchi Admin bilan bog'laning.", "warning");
    }
  }
}

// ==========================================
// KOMPANIYA SOZLAMALARI MODALI (Tenant Admin)
// ==========================================

async function openCompanySettingsModal() {
  const modal = document.getElementById("company-settings-modal");
  if (!modal) return;

  try {
    const res = await api("/api/saas/my-company");
    if (res.success && res.data) {
      const comp = res.data;
      const nameEl = document.getElementById("company-modal-name");
      const planEl = document.getElementById("company-modal-plan");
      const daysLeftEl = document.getElementById("company-modal-days-left");
      const expiresEl = document.getElementById("company-modal-expires");
      const groupInput = document.getElementById("company-modal-group-input");
      const saveBtn = document.getElementById("btn-company-save-settings");

      if (nameEl) nameEl.innerText = comp.name;
      if (planEl) planEl.innerText = comp.plan;
      if (daysLeftEl) {
        if (comp.plan === "UNLIMITED") {
          daysLeftEl.innerText = "Cheksiz (UNLIMITED) ♾️";
          daysLeftEl.style.color = "#818cf8";
        } else if (comp.days_left <= 0) {
          daysLeftEl.innerText = "Muddati tugagan 🔴";
          daysLeftEl.style.color = "#ef4444";
        } else {
          daysLeftEl.innerText = `${comp.days_left} kun qoldi ⏳`;
          daysLeftEl.style.color = "#34d399";
        }
      }
      if (expiresEl) {
        expiresEl.innerText = comp.subscription_expires_at ? formatDateOnly(comp.subscription_expires_at) : "Cheksiz";
      }
      if (groupInput) {
        groupInput.value = comp.telegram_group_id || "";
        groupInput.readOnly = (currentUser.role !== "ADMIN");
      }
      if (saveBtn) {
        saveBtn.style.display = (currentUser.role === "ADMIN") ? "inline-flex" : "none";
      }

      modal.style.display = "flex";
    }
  } catch (e) {
    showToast("Kompaniya ma'lumotlarini yuklashda xatolik!", "error");
  }
}

function closeCompanySettingsModal() {
  const modal = document.getElementById("company-settings-modal");
  if (modal) modal.style.display = "none";
}

function handleCompanyModalOverlayClick(event) {
  if (event.target && event.target.id === "company-settings-modal") {
    closeCompanySettingsModal();
  }
}

async function handleCompanySettingsSubmit(event) {
  event.preventDefault();
  const groupInput = document.getElementById("company-modal-group-input");
  const groupId = groupInput ? groupInput.value.trim() : "";

  try {
    const res = await api("/api/saas/my-company/settings", "POST", {
      telegram_group_id: groupId
    });
    if (res.success) {
      showToast(res.message || "Sozlamalar muvaffaqiyatli saqlandi!", "success");
      closeCompanySettingsModal();
    } else {
      showToast(res.detail || "Xatolik yuz berdi!", "error");
    }
  } catch (e) {
    showToast(e.message || "Server xatosi!", "error");
  }
}

// =========================================================
// TIJORIY & B2B EXCEL EKSPORTI VA BOSHQARUV QUROLLARI
// =========================================================

// Super Admin: Firmaning xodimlar limitini o'zgartirish
async function promptChangeCompanyLimit(companyId, currentLimit) {
  const newLimitStr = prompt("Ushbu firma uchun xodimlar limitini kiriting (soni):", currentLimit);
  if (!newLimitStr) return;
  const newLimit = parseInt(newLimitStr.trim());
  if (isNaN(newLimit) || newLimit < 1 || newLimit > 10000) {
    showToast("Noto'g'ri son kiritildi (1 dan 10000 gacha)! ", "error");
    return;
  }
  try {
    const res = await api(`/api/saas/companies/${companyId}/update-limit?max_employees=${newLimit}`, "POST");
    if (res.success) {
      showToast(res.message || "Limit muvaffaqiyatli o'zgartirildi!", "success");
      loadSaasCompanies();
    } else {
      showToast(res.detail || res.message || "Xatolik yuz berdi!", "error");
    }
  } catch (e) {
    showToast(e.message || "Server xatosi!", "error");
  }
}

// Super Admin: Firmaning tarif rejasini o'zgartirish (STANDARD, 5_YEARS, UNLIMITED)
async function promptChangeCompanyPlan(companyId, currentPlan) {
  const chosen = prompt(
    `Firma uchun yangi tarifni tanlang yoki kiriting:\n1 = STANDARD (Sana bo'yicha)\n2 = 5_YEARS (5 yillik obuna)\n3 = UNLIMITED (Cheksiz)`,
    currentPlan
  );
  if (!chosen) return;

  let newPlan = chosen.trim().toUpperCase();
  if (newPlan === "1" || newPlan === "STANDARD") newPlan = "STANDARD";
  else if (newPlan === "2" || newPlan === "5_YEARS" || newPlan === "5 YIL" || newPlan === "5") newPlan = "5_YEARS";
  else if (newPlan === "3" || newPlan === "UNLIMITED") newPlan = "UNLIMITED";
  else {
    alert("Noto'g'ri tarif kiritildi! Qabul qilinadigan variantlar: STANDARD, 5_YEARS, UNLIMITED");
    return;
  }

  if (newPlan === currentPlan) {
    showToast("Tanlangan tarif hozirgi tarif bilan bir xil.", "info");
    return;
  }

  const confirmMsg = newPlan === "5_YEARS" 
    ? `Haqiqatan ham ushbu firma tarifini '5_YEARS' (bugungi kundan boshlab rosa 5 yil) ga o'zgartirmoqchimisiz?`
    : `Haqiqatan ham ushbu firma tarifini '${newPlan}' ga o'zgartirmoqchimisiz?`;

  if (!confirm(confirmMsg)) return;

  try {
    const res = await api(`/api/saas/companies/${companyId}/update-plan?new_plan=${newPlan}`, "POST");
    if (res.success) {
      showToast(res.message || "Firma tarifi muvaffaqiyatli yangilandi!", "success");
      loadSaasCompanies();
    } else {
      showToast(res.detail || res.message || "Xatolik yuz berdi!", "error");
    }
  } catch (e) {
    showToast(e.message || "Server xatosi!", "error");
  }
}

// Baza zaxira nusxasini (Snapshot .db) yuklab olish
async function downloadDatabaseBackup() {
  const token = authToken || localStorage.getItem("crm_token") || localStorage.getItem("token");
  if (!token) {
    showToast("Avtorizatsiyadan o'tilmagan!", "error");
    return;
  }
  showToast("Baza zaxira nusxasi tayyorlanmoqda, iltimos kuting...", "info");
  try {
    const backupUrl = (currentUser && (currentUser.is_super_admin || currentUser.role === "DEVELOPER"))
      ? "/api/saas/backup-db"
      : "/api/admin/backup-db";
    const response = await fetch(backupUrl, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });
    if (!response.ok) {
      let errMsg = "Zaxira nusxasini yuklab olishda xatolik yuz berdi";
      try {
        const errJson = await response.json();
        errMsg = errJson.detail || errMsg;
      } catch (_) {}
      throw new Error(errMsg);
    }
    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    const now = new Date();
    const dateStr = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}_${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}`;
    a.download = `backup_xodim_reyting_${dateStr}.db`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);
    showToast("Baza zaxirasi (.db) muvaffaqiyatli yuklab olindi! Uni xavfsiz joyda saqlang.", "success");
  } catch (e) {
    showToast(e.message || "Zaxirani yuklashda xatolik yuz berdi", "error");
  }
}

// Bugungi yoki tanlangan sana/davr bo'yicha svodkani Rahbar shaxsiy Telegram lichkasiga yuborish
async function sendTodayDigestToTelegram() {
  const s = adminReportDateFilter?.startDate;
  const e = adminReportDateFilter?.endDate;

  let promptText = "";
  if (s && e && s === e) {
    promptText = `${formatDateOnly(s)} sanasi bo'yicha hisobot svodkasini shaxsiy Telegramingizga (@xodim_reyting_bot) yuborishni tasdiqlaysizmi?`;
  } else if (s && e && s !== e) {
    promptText = `${formatDateOnly(s)} dan ${formatDateOnly(e)} gacha bo'lgan davriy svodkani shaxsiy Telegramingizga (@xodim_reyting_bot) yuborishni tasdiqlaysizmi?`;
  } else if (s && !e) {
    promptText = `${formatDateOnly(s)} sanasi bo'yicha hisobot svodkasini shaxsiy Telegramingizga (@xodim_reyting_bot) yuborishni tasdiqlaysizmi?`;
  } else {
    promptText = "Bugungi kun yakuniy hisobot svodkasini shaxsiy Telegramingizga (@xodim_reyting_bot) yuborishni tasdiqlaysizmi?";
  }

  if (!confirm(promptText)) return;
  showToast("Svodka hisoblanmoqda va shaxsiy Telegramingizga yuborilmoqda...", "info");

  try {
    let url = "/api/reports/send-daily-digest";
    const params = [];
    if (s) params.push(`target_date=${encodeURIComponent(s)}`);
    if (e && e !== s) params.push(`end_date=${encodeURIComponent(e)}`);
    if (params.length > 0) url += `?${params.join("&")}`;

    const res = await api(url, "POST");
    if (res.success) {
      showToast(res.message || "Svodka shaxsiy Telegramingizga muvaffaqiyatli yuborildi!", "success");
    } else {
      showToast(res.message || res.detail || "Telegramga yuborib bo'lmadi", "warning");
    }
  } catch (e) {
    showToast(e.message || "Xatolik yuz berdi!", "error");
  }
}

// Har qanday XLSX faylini rahbar shaxsiy Telegram lichkasiga yuborish yordamchisi
async function sendGeneratedXlsxToTelegram(wb, filename, caption) {
  try {
    if (typeof XLSX === "undefined") return;
    const wbout = XLSX.write(wb, { bookType: "xlsx", type: "base64" });
    await api("/api/reports/send-excel-telegram", "POST", {
      filename: filename,
      file_base64: wbout,
      caption: caption
    });
  } catch (e) {
    console.warn("Telegramga Excel yuborishda xatolik:", e);
  }
}

// 1. Kunlik hisobotlarni Excelga (.xlsx) eksport qilish va Rahbar shaxsiy Telegramiga yuborish
async function exportAdminReportsToExcel() {
  let s = adminReportDateFilter?.startDate;
  let e = adminReportDateFilter?.endDate;

  // Agar sana tanlanmagan bo'lsa, bugungi sana bo'yicha amal qiladi
  if (!s) {
    const today = getTashkentTodayIso();
    s = today;
    e = today;
  }

  showToast(`Excel hisoboti (${formatDateOnly(s)}) tayyorlanmoqda va Telegramingizga yuborilmoqda...`, "info");

  try {
    const token = authToken || localStorage.getItem("crm_token") || localStorage.getItem("token") || sessionStorage.getItem("token");
    let url = "/api/reports/export-excel";
    const params = [];
    if (s) params.push(`start_date=${encodeURIComponent(s)}`);
    if (e && e !== s) params.push(`end_date=${encodeURIComponent(e)}`);
    if (params.length > 0) url += `?${params.join("&")}`;

    const resp = await fetch(url, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    if (!resp.ok) {
      const errJson = await resp.json().catch(() => null);
      throw new Error(errJson?.detail || "Excel hisobotini yuklab olishda xatolik");
    }

    let filename = `Hisobotlar_${s || 'barcha'}.xlsx`;
    const disp = resp.headers.get("Content-Disposition");
    if (disp && disp.includes("filename=")) {
      const match = disp.match(/filename="?([^";]+)"?/);
      if (match && match[1]) filename = match[1];
    }

    const blob = await resp.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(downloadUrl);
    a.remove();

    showToast("Excel hisoboti yuklab olindi va shaxsiy Telegramingizga (@xodim_reyting_bot) yuborildi! 📥", "success");
    return;
  } catch (err) {
    console.warn("Backend Excel export xatoligi, mijoz tomonidan yuklanmoqda:", err);
  }

  // Fallback: Agar tarmoq uzilsa mijoz tomonida XLSX orqali generatsiya
  if (typeof XLSX === "undefined") {
    showToast("Excel kutubxonasi yuklanmadi. Sahifani qayta yangilang!", "error");
    return;
  }
  if (!adminReportsCache || adminReportsCache.length === 0) {
    showToast("Eksport qilish uchun hisobotlar topilmadi!", "warning");
    return;
  }

  const exportData = adminReportsCache.map((r, idx) => ({
    "№": idx + 1,
    "Sana": formatDateOnly(r.report_date),
    "Xodim F.I.SH": r.employee_name || "-",
    "Paynet (so'm)": r.paynet || 0,
    "Karta (+3%) (so'm)": r.card_amount || 0,
    "Leviy (so'm)": r.leviy || 0,
    "Qarz to'lovi (so'm)": r.debt_paid || 0,
    "Jami Kirim (so'm)": r.total_inflow || 0,
    "Kunlik (so'm)": r.kunlik || 0,
    "Terminal (so'm)": r.terminal || 0,
    "Berilgan summa (so'm)": r.given_amount || 0,
    "Skidka (so'm)": r.skidka || 0,
    "Xarajat (so'm)": r.xarajat || 0,
    "Jami Chiqim (so'm)": r.total_outflow || 0,
    "Sof Kassa (Net) (so'm)": r.net_amount || 0,
    "Sotilgan Sim-karta (dona)": r.sim_cards_count || 0,
    "Status": r.status === "APPROVED" ? "Tasdiqlangan" : (r.status === "REJECTED" ? "Rad etilgan" : "Kutilmoqda"),
    "Izoh": r.comment || ""
  }));

  const ws = XLSX.utils.json_to_sheet(exportData);
  ws["!cols"] = [
    { wch: 6 }, { wch: 12 }, { wch: 22 }, { wch: 15 }, { wch: 18 },
    { wch: 14 }, { wch: 16 }, { wch: 16 }, { wch: 14 }, { wch: 14 },
    { wch: 18 }, { wch: 14 }, { wch: 14 }, { wch: 16 }, { wch: 18 },
    { wch: 20 }, { wch: 15 }, { wch: 30 }
  ];

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Kunlik Hisobotlar");
  const dateLabel = adminReportDateFilter?.startDate || getTashkentTodayIso();
  const fileName = `Hisobotlar_${dateLabel}_${new Date().toISOString().slice(0,10)}.xlsx`;
  XLSX.writeFile(wb, fileName);
  sendGeneratedXlsxToTelegram(wb, fileName, `📥 <b>KUNLIK HISOBOTLAR (${dateLabel})</b>\n\n📎 <i>Excel fayli biriktirildi.</i>`);
  showToast("Kunlik hisobotlar Excel (.xlsx) fayliga yuklandi va Telegramingizga yuborildi! 📥", "success");
}

// 2. Kassa taqqoslash jadvalini Excelga (.xlsx) eksport qilish
function exportComparisonToExcel() {
  if (typeof XLSX === "undefined") {
    showToast("Excel kutubxonasi yuklanmadi!", "error");
    return;
  }
  if (!adminComparisonCache || adminComparisonCache.length === 0) {
    showToast("Eksport qilish uchun taqqoslash ma'lumotlari topilmadi!", "warning");
    return;
  }

  const exportData = adminComparisonCache.map((row, idx) => ({
    "№": idx + 1,
    "Xodim F.I.SH": row.employee_name || "-",
    "Xodim hisoboti (so'm)": row.report_amount || 0,
    "Hisobot holati": row.report_status || "-",
    "Kassir qabul qilgan (Jami ekvivalent so'm)": row.cashier_amount || 0,
    "So'mda qabul (so'm)": row.cashier_amount_uzs || 0,
    "Dollarda qabul ($)": row.cashier_amount_usd || 0,
    "Tafovut / Farq (so'm)": row.difference || 0,
    "Qabul qilgan Kassir": row.cashier_names || "-"
  }));

  const ws = XLSX.utils.json_to_sheet(exportData);
  ws["!cols"] = [
    { wch: 6 },
    { wch: 22 },
    { wch: 22 },
    { wch: 18 },
    { wch: 26 },
    { wch: 18 },
    { wch: 18 },
    { wch: 20 },
    { wch: 22 }
  ];

  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Kassa Taqqoslash");
  const fileName = `Kassa_Taqqoslash_${new Date().toISOString().slice(0,10)}.xlsx`;
  XLSX.writeFile(wb, fileName);
  sendGeneratedXlsxToTelegram(wb, fileName, "📥 <b>KASSA TAQQOSLASH HISOBOTI</b>\n\n📎 <i>Excel fayli biriktirildi.</i>");
  showToast("Kassa taqqoslash ma'lumotlari Excelga yuklandi va Telegramingizga yuborildi! 📥", "success");
}

// 3. Sim-kartalar hisobi va balansini Excelga (.xlsx) eksport qilish
function exportSimCardsToExcel() {
  if (typeof XLSX === "undefined") {
    showToast("Excel kutubxonasi yuklanmadi!", "error");
    return;
  }
  if (!adminSimBalancesCache || adminSimBalancesCache.length === 0) {
    showToast("Eksport qilish uchun sim-karta balansi topilmadi!", "warning");
    return;
  }

  const wb = XLSX.utils.book_new();

  // 1-varaqa: Balanslar
  const balanceData = adminSimBalancesCache.map((b, idx) => ({
    "№": idx + 1,
    "Xodim F.I.SH": b.full_name || "-",
    "Qo'lidagi zaxira (dona)": b.in_stock || 0,
    "Sotilgan sim-kartalar (dona)": b.sold_count || 0,
    "Jami biriktirilgan (dona)": (b.in_stock || 0) + (b.sold_count || 0)
  }));
  const ws1 = XLSX.utils.json_to_sheet(balanceData);
  ws1["!cols"] = [{ wch: 6 }, { wch: 24 }, { wch: 22 }, { wch: 24 }, { wch: 24 }];
  XLSX.utils.book_append_sheet(wb, ws1, "Xodimlar Balansi");

  // 2-varaqa: Oxirgi Partiyalar
  if (adminSimRecentCache && adminSimRecentCache.length > 0) {
    const recentData = adminSimRecentCache.map((s, idx) => ({
      "№": idx + 1,
      "Operator": s.operator_type || "Uzmobile",
      "Boshlang'ich seriya": s.start_serial || s.serial_number || "-",
      "Tugash seriyasi": s.end_serial || s.serial_number || "-",
      "Soni (dona)": s.total_count || 1,
      "Biriktirilgan Xodim": s.employee_name || "-",
      "Tarqatuvchi": s.distributor_name || "-",
      "Holati": s.status === "GIVEN" ? "Xodimda" : "Sotilgan",
      "Vaqti": s.created_at || s.distributed_at || "-"
    }));
    const ws2 = XLSX.utils.json_to_sheet(recentData);
    ws2["!cols"] = [{ wch: 6 }, { wch: 14 }, { wch: 22 }, { wch: 22 }, { wch: 14 }, { wch: 22 }, { wch: 20 }, { wch: 14 }, { wch: 20 }];
    XLSX.utils.book_append_sheet(wb, ws2, "Partiyalar Tarixi");
  }

  const fileName = `Sim_Kartalar_Hisobi_${new Date().toISOString().slice(0,10)}.xlsx`;
  XLSX.writeFile(wb, fileName);
  sendGeneratedXlsxToTelegram(wb, fileName, "📱 <b>SIM-KARTALAR HISOBI VA BALANSI</b>\n\n📎 <i>Excel fayli biriktirildi.</i>");
  showToast("Sim-kartalar hisobi Excel fayliga yuklandi va Telegramingizga yuborildi! 📥", "success");
}

// 4. Reyting va Liderlar jadvalini Excelga (.xlsx) eksport qilish
function exportRatingToExcel() {
  if (typeof XLSX === "undefined") {
    showToast("Excel kutubxonasi yuklanmadi!", "error");
    return;
  }
  const items = adminLeaderboardCache?.data || [];
  if (items.length === 0) {
    showToast("Eksport qilish uchun reyting ma'lumotlari mavjud emas!", "warning");
    return;
  }

  const exportData = items.map(item => ({
    "O'rin": item.rank,
    "Nishon": item.badge,
    "Xodim F.I.SH": item.employee_name,
    "Lavozimi": item.role === "CASHIER" ? "Kassir" : "Xodim",
    "Topshirgan summasi (so'm)": item.total_sum || 0,
    "Summa balli": item.money_points || 0,
    "Sotilgan Sim-karta (dona)": item.total_sim_cards || 0,
    "Sim-karta balli": item.sim_points || 0,
    "Jami KPI Ball": item.total_score || 0,
    "Hisobot topshirgan kunlari": item.reports_count || 0
  }));

  const ws = XLSX.utils.json_to_sheet(exportData);
  ws["!cols"] = [
    { wch: 8 },
    { wch: 10 },
    { wch: 24 },
    { wch: 14 },
    { wch: 22 },
    { wch: 14 },
    { wch: 20 },
    { wch: 16 },
    { wch: 16 },
    { wch: 22 }
  ];

  const wb = XLSX.utils.book_new();
  const periodLabel = adminLeaderboardCache.period === "monthly" ? "Oylik" : "Umumiy";
  XLSX.utils.book_append_sheet(wb, ws, `Reyting_${periodLabel}`);
  const fileName = `Reyting_${periodLabel}_${new Date().toISOString().slice(0,10)}.xlsx`;
  XLSX.writeFile(wb, fileName);
  sendGeneratedXlsxToTelegram(wb, fileName, `🏆 <b>XODIMLAR REYTINGI (${periodLabel.toUpperCase()})</b>\n\n📎 <i>Excel fayli biriktirildi.</i>`);
  showToast("Reyting jadvali Excelga yuklandi va Telegramingizga yuborildi! 📥", "success");
}

// ============================================================
// MAXSUS CHIROYLI VA IXCHAM VAQT TANLAGICH (TIME PICKER)
// ============================================================
let activeTimePickerTarget = null;
let currentPickerHour = "09";
let currentPickerMinute = "00";
let activePickerTab = "hour";

function openCompactTimePicker(inputEl, label = "Vaqt") {
  if (!inputEl) return;
  activeTimePickerTarget = inputEl;

  let val = inputEl.value || "09:00";
  if (!val.includes(":")) val = "09:00";
  const parts = val.split(":");
  currentPickerHour = parts[0].padStart(2, "0");
  currentPickerMinute = (parts[1] || "00").padStart(2, "0");
  activePickerTab = "hour";

  const popover = document.getElementById("compact-time-picker-popover");
  if (!popover) return;

  const titleEl = document.getElementById("time-picker-label");
  if (titleEl) {
    titleEl.textContent = label === "start" ? "Ish boshlanishi" : (label === "end" ? "Ish tugashi" : label);
  }

  renderTimePickerDisplay();
  renderTimePickerColumns();
  renderTimePickerPresets();

  popover.style.display = "block";
  const rect = inputEl.getBoundingClientRect();
  const popoverWidth = 235;
  const popoverHeight = 245;

  // O'rtaroqda ochilishi: modal ichida bo'lsa modalning gorizontal markaziga,
  // aks holda kiritish maydonining gorizontal markaziga tekislanadi
  const modal = inputEl.closest(".modal-content");
  let left;
  if (modal) {
    const modalRect = modal.getBoundingClientRect();
    left = window.scrollX + modalRect.left + (modalRect.width - popoverWidth) / 2;
  } else {
    left = window.scrollX + rect.left + (rect.width - popoverWidth) / 2;
  }

  // Ekran chetlaridan chiqib ketmaslik tekshiruvi
  if (left + popoverWidth > window.innerWidth - 10) {
    left = window.innerWidth - popoverWidth - 12;
  }
  if (left < 10) left = 10;

  // Vertikal joylashuv: pastda joy yetarli bo'lsa input tagida, aks holda input tepasida
  let top;
  if (rect.bottom + popoverHeight + 15 > window.innerHeight && rect.top > popoverHeight + 20) {
    top = window.scrollY + rect.top - popoverHeight - 4;
  } else {
    top = window.scrollY + rect.bottom + 4;
  }

  popover.style.top = `${top}px`;
  popover.style.left = `${left}px`;
}

function closeCompactTimePicker() {
  const popover = document.getElementById("compact-time-picker-popover");
  if (popover) popover.style.display = "none";
  activeTimePickerTarget = null;
}

function renderTimePickerDisplay() {
  const hEl = document.getElementById("time-display-hour");
  const mEl = document.getElementById("time-display-minute");
  if (hEl) {
    hEl.textContent = currentPickerHour;
    hEl.classList.toggle("active", activePickerTab === "hour");
  }
  if (mEl) {
    mEl.textContent = currentPickerMinute;
    mEl.classList.toggle("active", activePickerTab === "minute");
  }
}

function setTimePickerTab(tab) {
  activePickerTab = tab;
  renderTimePickerDisplay();
}

function renderTimePickerColumns() {
  const hoursCol = document.getElementById("time-col-hours");
  const minsCol = document.getElementById("time-col-minutes");

  if (hoursCol) {
    hoursCol.innerHTML = "";
    for (let h = 0; h < 24; h++) {
      const hStr = String(h).padStart(2, "0");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `time-pill-btn ${hStr === currentPickerHour ? 'active' : ''}`;
      btn.textContent = hStr;
      btn.onclick = (e) => {
        e.stopPropagation();
        currentPickerHour = hStr;
        activePickerTab = "minute";
        renderTimePickerDisplay();
        renderTimePickerColumns();
      };
      hoursCol.appendChild(btn);
    }
  }

  if (minsCol) {
    minsCol.innerHTML = "";
    for (let m = 0; m < 60; m += 5) {
      const mStr = String(m).padStart(2, "0");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `time-pill-btn ${mStr === currentPickerMinute ? 'active' : ''}`;
      btn.textContent = mStr;
      btn.onclick = (e) => {
        e.stopPropagation();
        currentPickerMinute = mStr;
        renderTimePickerDisplay();
        renderTimePickerColumns();
      };
      minsCol.appendChild(btn);
    }
  }
}

function renderTimePickerPresets() {
  const presetsBox = document.getElementById("time-quick-presets");
  if (!presetsBox) return;
  const presets = ["08:00", "09:00", "10:00", "18:00", "19:00", "20:00", "21:00"];
  presetsBox.innerHTML = "";
  presets.forEach(p => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "time-chip-btn";
    btn.textContent = p;
    btn.onclick = (e) => {
      e.stopPropagation();
      const parts = p.split(":");
      currentPickerHour = parts[0];
      currentPickerMinute = parts[1];
      applyCompactTimePicker();
    };
    presetsBox.appendChild(btn);
  });
}

function applyCompactTimePicker() {
  if (activeTimePickerTarget) {
    const timeVal = `${currentPickerHour}:${currentPickerMinute}`;
    activeTimePickerTarget.value = timeVal;
    activeTimePickerTarget.dispatchEvent(new Event("change"));
  }
  closeCompactTimePicker();
}

// ============================================================
// DASTURCHI ADMIN UCHUN MAXSUS SAAS SANA TANLAGICH (DATE PICKER)
// ============================================================
let activeSaasDateTarget = null;
let saasCalYear = new Date().getFullYear();
let saasCalMonth = new Date().getMonth();
let selectedSaasDateIso = null;

function openCompactSaasDatePicker(inputEl, title = "Sanani tanlash") {
  if (!inputEl) return;
  activeSaasDateTarget = inputEl;

  const curVal = inputEl.value;
  if (curVal && curVal.includes("-")) {
    const parts = curVal.split("-");
    saasCalYear = parseInt(parts[0], 10);
    saasCalMonth = parseInt(parts[1], 10) - 1;
    selectedSaasDateIso = curVal;
  } else {
    const d = new Date();
    saasCalYear = d.getFullYear();
    saasCalMonth = d.getMonth();
    selectedSaasDateIso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  const popover = document.getElementById("compact-saas-datepicker-popover");
  if (!popover) return;

  const titleEl = document.getElementById("saas-datepicker-title");
  if (titleEl) titleEl.textContent = title;

  renderCompactSaasCalendar();

  popover.style.display = "block";
  const rect = inputEl.getBoundingClientRect();
  const popoverWidth = 280;
  const popoverHeight = 310;

  const modal = inputEl.closest(".modal-content");
  let left;
  if (modal) {
    const modalRect = modal.getBoundingClientRect();
    left = window.scrollX + modalRect.left + (modalRect.width - popoverWidth) / 2;
  } else {
    left = window.scrollX + rect.left + (rect.width - popoverWidth) / 2;
  }

  if (left + popoverWidth > window.innerWidth - 10) {
    left = window.innerWidth - popoverWidth - 12;
  }
  if (left < 10) left = 10;

  let top;
  if (rect.bottom + popoverHeight + 15 > window.innerHeight && rect.top > popoverHeight + 20) {
    top = window.scrollY + rect.top - popoverHeight - 4;
  } else {
    top = window.scrollY + rect.bottom + 4;
  }

  popover.style.top = `${top}px`;
  popover.style.left = `${left}px`;
}

function closeCompactSaasDatePicker() {
  const popover = document.getElementById("compact-saas-datepicker-popover");
  if (popover) popover.style.display = "none";
  activeSaasDateTarget = null;
}

function navigateSaasCalMonth(direction) {
  saasCalMonth += direction;
  if (saasCalMonth < 0) {
    saasCalMonth = 11;
    saasCalYear -= 1;
  } else if (saasCalMonth > 11) {
    saasCalMonth = 0;
    saasCalYear += 1;
  }
  renderCompactSaasCalendar();
}

function applySaasPresetDays(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  saasCalYear = d.getFullYear();
  saasCalMonth = d.getMonth();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  selectedSaasDateIso = `${y}-${m}-${day}`;
  renderCompactSaasCalendar();
}

function applySaasPresetYears(years) {
  const d = new Date();
  d.setFullYear(d.getFullYear() + years);
  saasCalYear = d.getFullYear();
  saasCalMonth = d.getMonth();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  selectedSaasDateIso = `${y}-${m}-${day}`;
  renderCompactSaasCalendar();
}

function renderCompactSaasCalendar() {
  const monthYearLabel = document.getElementById("saas-cal-month-year-text");
  const grid = document.getElementById("saas-cal-days-grid");
  const summaryEl = document.getElementById("saas-cal-summary-text");

  if (monthYearLabel) {
    monthYearLabel.textContent = `${uzbekMonths[saasCalMonth]} ${saasCalYear}`;
  }

  if (grid) {
    grid.innerHTML = "";
    const dayNames = ["D", "S", "Ch", "P", "J", "Sh", "Y"];
    dayNames.forEach(dn => {
      const el = document.createElement("div");
      el.className = "saas-cal-day-name";
      el.textContent = dn;
      grid.appendChild(el);
    });

    const firstDayObj = new Date(saasCalYear, saasCalMonth, 1);
    let firstDayIndex = firstDayObj.getDay();
    if (firstDayIndex === 0) firstDayIndex = 7;

    const daysInMonth = new Date(saasCalYear, saasCalMonth + 1, 0).getDate();
    const prevMonthDays = new Date(saasCalYear, saasCalMonth, 0).getDate();

    const todayD = new Date();
    const todayIso = `${todayD.getFullYear()}-${String(todayD.getMonth() + 1).padStart(2, "0")}-${String(todayD.getDate()).padStart(2, "0")}`;

    for (let i = firstDayIndex - 1; i >= 1; i--) {
      const cell = document.createElement("div");
      cell.className = "saas-cal-day-cell empty-day";
      cell.textContent = prevMonthDays - i + 1;
      grid.appendChild(cell);
    }

    for (let d = 1; d <= daysInMonth; d++) {
      const cell = document.createElement("div");
      const mStr = String(saasCalMonth + 1).padStart(2, "0");
      const dStr = String(d).padStart(2, "0");
      const currentIso = `${saasCalYear}-${mStr}-${dStr}`;

      let classes = "saas-cal-day-cell";
      if (currentIso === selectedSaasDateIso) classes += " is-selected";
      if (currentIso === todayIso) classes += " is-today";

      cell.className = classes;
      cell.textContent = d;
      cell.onclick = (e) => {
        e.stopPropagation();
        selectedSaasDateIso = currentIso;
        renderCompactSaasCalendar();
      };
      grid.appendChild(cell);
    }
  }

  if (summaryEl && selectedSaasDateIso) {
    const parts = selectedSaasDateIso.split("-");
    const dFmt = `${parts[2]}.${parts[1]}.${parts[0]}`;
    const targetD = new Date(selectedSaasDateIso);
    const nowD = new Date();
    const diffDays = Math.ceil((targetD - nowD) / (1000 * 3600 * 24));
    const daysLabel = diffDays > 0 ? `(${diffDays} kun qoladi)` : "";
    summaryEl.innerHTML = `<span>📅</span> Tanlandi: <b>${dFmt}</b> <span style="opacity: 0.8; font-size: 0.72rem;">${daysLabel}</span>`;
  }
}

function applyCompactSaasDatePicker() {
  if (activeSaasDateTarget && selectedSaasDateIso) {
    activeSaasDateTarget.value = selectedSaasDateIso;
    activeSaasDateTarget.dispatchEvent(new Event("change"));
  }
  closeCompactSaasDatePicker();
}

// Tashqariga bosilganda popoverlarni yopish
window.addEventListener("click", (e) => {
  const timePopover = document.getElementById("compact-time-picker-popover");
  if (timePopover && timePopover.style.display !== "none") {
    if (!timePopover.contains(e.target) && !e.target.closest(".custom-time-input") && !e.target.closest(".time-input-icon")) {
      closeCompactTimePicker();
    }
  }

  const saasPopover = document.getElementById("compact-saas-datepicker-popover");
  if (saasPopover && saasPopover.style.display !== "none") {
    if (!saasPopover.contains(e.target) && !e.target.closest(".custom-date-input") && !e.target.closest(".date-input-icon")) {
      closeCompactSaasDatePicker();
    }
  }
});

// Window load init
window.addEventListener("DOMContentLoaded", () => {
  initTheme();
  setupCardTopupInputs();
  setupGivenAmountInputs();
  setupReportCalculationListeners();
  setupUsdRateInput();
  initSaasCreateFormDate();
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
