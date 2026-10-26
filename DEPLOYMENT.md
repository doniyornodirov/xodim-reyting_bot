# 🚀 Xodim-Reyting & Paynet CRM: To'liq Bulutli Joylashtirish Qo'llanmasi (Deployment Guide)

Ushbu qo'llanma tizimning **100% uzluksiz (High-Availability)**, **xavfsiz**, **o'z-o'zini tiklaydigan (Self-Healing)** va **avtomatik zaxiralanadigan** zamonaviy arxitektura asosida bulutli muhitlarga joylashtirish tartibini bosqichma-bosqich tushuntiradi.

---

## 🏛️ 1. Tizim Arxitekturasi

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. STATIK FRONTEND (Vercel)                                            │
│    - Global Anycast CDN, Bepul avtomatik SSL (HTTPS)                   │
│    - Har doim onlayn, server yuklamasidan mutlaqo ozod                 │
│    - Manzil: https://xodim-reyting.vercel.app                          │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │  REST API So'rovlari (CORS / Proxy)
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 2. BACKEND & TELEGRAM BOT (Railway yoki Hetzner Cloud VPS)             │
│    - FastAPI asinxron server + aiogram 3 Telegram bot                  │
│    - Docker (restart: always) yoki PM2 / systemd avtomatik tiklash     │
│    - Healthcheck (/health) va fon scheduleri                           │
│    - Manzil: https://api.xodim-reyting.com                             │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │  SSL Encrypted Connection
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 3. AVTOMATIK ZAXIRALANUVCHI BAZA (Supabase / Managed PostgreSQL 16)     │
│    - Kunlik avtomatik zaxiralash (Automated Daily Backups & PITR)      │
│    - Server buzilsa ham barcha moliyaviy ma'lumotlar xavfsiz saqlanadi │
│    - 11 ta jadval, kompozit indekslar va 90 kunlik retention           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 2. 1-BOSQICH: Bulutli Ma'lumotlar Bazasi (Supabase)

Server ichidagi lokal bazalar server buzilganda yo'qolish xavfiga ega. Shuning uchun avtomatik zaxiralanuvchi **Supabase** dan foydalanamiz:

1. [Supabase.com](https://supabase.com) ga kiring va bepul akkaunt oching.
2. **"New Project"** tugmasini bosing:
   - **Name**: `xodim-reyting-db`
   - **Database Password**: Kuchli parol belgilang va uni eslab qoling.
   - **Region**: Frankfurt (`eu-central-1`) yoki o'zingizga yaqin hududni tanlang.
3. Chap menyudan **"SQL Editor"** bo'limiga o'ting.
4. Loyihadagi [`supabase_schema.sql`](file:///c:/Users/Doniyor/Xodim-reyting/supabase_schema.sql) fayli mazmunini nusxalang va SQL Editor oynasiga qo'yib, **"Run"** tugmasini bosing.
   - *Natija*: Barcha 11 ta jadval, indekslar, tizim sozlamalari va Bosh Rahbar admin hisobi (`8686341550`) bir zumda yaratiladi.
5. **Project Settings** -> **Database** bo'limiga o'ting va **Connection string** (URI) nusxasini oling:
   ```text
   postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
   ```
6. **Avtomatik zaxiralash**: Supabase har kuni bazani avtomatik to'liq zaxiralaydi (Database -> Backups bo'limidan ko'rish mumkin).

---

## 🚂 3. 2-BOSQICH (A): Backend va Telegram Botni Railway'ga Joylashtirish

Railway — Docker asosida ishlovchi, server xatoliklarida o'z-o'zini avtomatik qayta yoquvchi (Self-Healing) eng qulay bulutli platforma:

1. [Railway.app](https://railway.app) ga kiring va GitHub orqali kiring.
2. **"New Project"** -> **"Deploy from GitHub repo"** ni tanlang va `Xodim-reyting` repozitoriyasini tanlang.
3. Railway loyihadagi [`Dockerfile`](file:///c:/Users/Doniyor/Xodim-reyting/Dockerfile) va [`railway.json`](file:///c:/Users/Doniyor/Xodim-reyting/railway.json) ni avtomatik taniydi.
4. Loyihaning **"Variables"** bo'limiga quyidagi muhit o'zgaruvchilarini kiriting:
   ```env
   BOT_TOKEN=8932019841:AAFCkLdoBhzmkGJy3L0MY4-esw0_aToQiZY
   TELEGRAM_GROUP_ID=-1005381348358
   RAHBAR_ID=8686341550
   JWT_SECRET=super_kriptografik_maxfiy_jwt_kalit_2026
   DATABASE_URL=postgresql://postgres.xxx:parol@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
   CORS_ORIGINS=*
   PORT=8000
   ```
5. **"Settings"** -> **"Networking"** bo'limidan **"Generate Domain"** tugmasini bosing. Sizga havola beriladi:
   - Masalan: `https://xodim-reyting-production.up.railway.app`
6. Tekshirish: Brauzerda `https://xodim-reyting-production.up.railway.app/health` manzilini oching:
   - Javob: `{"status": "ok", "app": "Xodim-Reyting CRM"}` bo'lishi kerak.

---

## 🖥️ 4. 2-BOSQICH (B): Hetzner yoki Ubuntu VPS Serverda Joylashtirish (Docker / PM2)

Agar Hetzner Cloud yoki shaxsiy VPS serveringiz bo'lsa:

### Variant 1: Docker Compose Orqali (Tavsiya etiladi)
```bash
# 1. Kodni serverga yuklash
git clone https://github.com/Doniyor/Xodim-reyting.git /var/www/xodim-reyting
cd /var/www/xodim-reyting

# 2. .env faylini sozlash
cp .env.example .env
nano .env # (Supabase DATABASE_URL va Bot tokenni kiriting)

# 3. Docker Compose bilan ishga tushirish (restart: always tufayli doim o'zi tiklanadi)
docker compose up -d --build

# 4. Statusni tekshirish
docker compose ps
docker compose logs -f app
```

### Variant 2: PM2 Process Manager Orqali
```bash
# Node.js va PM2 o'rnatish
sudo apt update && sudo apt install -y python3-pip python3-venv npm
sudo npm install -g pm2

# Virtualenv va paketlar
cd /var/www/xodim-reyting
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# PM2 orqali avtomatik qayta yondirish bilan ishga tushirish
pm2 start ecosystem.config.js

# Server qayta yoqilganda (reboot) avtomatik ishga tushishi uchun
pm2 startup
pm2 save
```

### Variant 3: Linux Systemd Xizmati Orqali
```bash
sudo cp systemd/xodim-reyting.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable xodim-reyting
sudo systemctl start xodim-reyting
sudo systemctl status xodim-reyting
```

---

## ⚡ 5. 3-BOSQICH: Frontendni Vercel'ga Joylashtirish

1. [Vercel.com](https://vercel.com) ga kiring va GitHub akkauntingiz bilan kiring.
2. **"Add New..."** -> **"Project"** ni bosing va repozitoriyangizni tanlang.
3. Loyihadagi [`vercel.json`](file:///c:/Users/Doniyor/Xodim-reyting/vercel.json) avtomatik tarzda statik routing va kesh sozlamalarini qo'llaydi.
4. **Environment Variables** bo'limida:
   - `API_BASE_URL` = `https://xodim-reyting-production.up.railway.app` (Railway backend manzilingiz)
5. **"Deploy"** tugmasini bosing!
   - 10-15 soniya ichida frontend butun dunyo bo'ylab eng tezkor CDN tarmog'ida ishga tushadi:
   - Masalan: `https://xodim-reyting.vercel.app`
6. Endi xodimlar va Rahbar bevosita Vercel manziliga kirib tizimdan xavfsiz va uzluksiz foydalanishi mumkin!

---

## 🛡️ 6. 4-BOSQICH: Uzluksizlik va O'z-o'zini Tiklash Sinovi (Fail-Safe Testing)

Tizim quyidagi 3 qatlamli xavfsizlik himoyasiga ega:

| Sinov Holati | Nima Sodir Bo'ladi? | Qanday Tiklanadi? |
|---|---|---|
| **Koddagi xatolik / Kutilmagan Crash** | Jarayon to'xtaydi | Docker `restart: always` yoki PM2 `autorestart: true` uni **3 soniya ichida** avtomatik qayta yondiradi. |
| **Server elektrdan uzilishi / Reboot** | Butun server o'chadi | Server yongan zahoti `systemd` yoki Docker xizmati avtomatik ko'tariladi. |
| **Server diski buzilishi / To'lishi** | Server ishdan chiqadi | Barcha ma'lumotlar **Supabase bulutli bazasida** xavfsiz saqlanadi, yangi serverga 1 daqiqada ulab yuborish mumkin. |
| **Xotira to'lib ketishi (Memory Leak)** | RAM oshib ketadi | PM2 `max_memory_restart: 500M` ko'rsatkichi bilan avtomatik tozalab qayta yondiradi. |
| **90 kundan oshgan eski ma'lumotlar** | Baza og'irlashadi | [`app/retention.py`](file:///c:/Users/Doniyor/Xodim-reyting/app/retention.py) fonda har 24 soatda eskirgan ma'lumotlarni o'chirib, bazani yengil ushlab turadi. |

---

## 📋 7. Tekshirish Nazorat Ro'yxati (Pre-Flight Checklist)

- [x] [`requirements.txt`](file:///c:/Users/Doniyor/Xodim-reyting/requirements.txt) yaratilgan (`fastapi`, `uvicorn`, `aiogram`, `asyncpg`, `pydantic`).
- [x] [`Dockerfile`](file:///c:/Users/Doniyor/Xodim-reyting/Dockerfile) xavfsiz non-root foydalanuvchi va `/health` tekshiruvi bilan yaratilgan.
- [x] [`docker-compose.yml`](file:///c:/Users/Doniyor/Xodim-reyting/docker-compose.yml) `restart: always` siyosati bilan tayyorlangan.
- [x] [`vercel.json`](file:///c:/Users/Doniyor/Xodim-reyting/vercel.json) statik kesh va routing bilan sozlangan.
- [x] [`supabase_schema.sql`](file:///c:/Users/Doniyor/Xodim-reyting/supabase_schema.sql) 11 ta jadval va indekslar bilan tayyorlangan.
- [x] [`ecosystem.config.js`](file:///c:/Users/Doniyor/Xodim-reyting/ecosystem.config.js) va [`systemd/xodim-reyting.service`](file:///c:/Users/Doniyor/Xodim-reyting/systemd/xodim-reyting.service) avtomatik tiklash uchun sozlangan.
- [x] [`app/config.py`](file:///c:/Users/Doniyor/Xodim-reyting/app/config.py) va [`app/main.py`](file:///c:/Users/Doniyor/Xodim-reyting/app/main.py) Vercel uchun CORS hamda `/health` endpointi bilan yangilangan.
- [x] [`static/js/app.js`](file:///c:/Users/Doniyor/Xodim-reyting/static/js/app.js) Vercel'dan backendga dinamik ulanuvchi `API_BASE_URL` bilan jihozlangan.
