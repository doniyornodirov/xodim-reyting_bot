// =========================================================================
// PM2 Konfiguratsiya Fayli (ecosystem.config.js)
// Maqsad: Hetzner / VPS serverlarida tizimni avtomatik qayta yondirish (Self-Healing)
// Ishga tushirish: pm2 start ecosystem.config.js
// =========================================================================

module.exports = {
  apps: [
    {
      name: "xodim-reyting-crm",
      script: "run.py",
      interpreter: "python3", // Yoki virtualenv yo'li: "/home/ubuntu/venv/bin/python3"
      instances: 1,
      exec_mode: "fork",

      // 1. O'z-o'zini tiklash (Auto-Restart on Crash)
      autorestart: true,
      watch: false, // Productionda doimiy o'qish shart emas
      max_restarts: 20,
      restart_delay: 3000, // Qayta ishga tushishdan oldin 3 soniya kutish

      // 2. Xotira sizishidan (Memory Leak) himoya
      // Agar xotira 500MB dan oshsa, tizim o'zini avtomatik qayta yondiradi
      max_memory_restart: "500M",

      // 3. Loglar va vaqt belgisi
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      error_file: "./logs/pm2-error.log",
      out_file: "./logs/pm2-out.log",
      merge_logs: true,

      // 4. Muhit o'zgaruvchilari
      env: {
        PORT: 8000,
        HOST: "0.0.0.0",
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      }
    }
  ]
};
