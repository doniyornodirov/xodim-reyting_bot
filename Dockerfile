# =========================================================================
# Dockerfile: Xodim-Reyting & Paynet CRM (Production Ready)
# Python 3.12 Slim, Xavfsiz non-root foydalanuvchi, Healthcheck bilan
# =========================================================================

FROM python:3.12-slim AS base

# Muhit o'zgaruvchilari
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Tizim paketlari (healthcheck uchun curl va kerakli kutubxonalar)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Bog'liqliklarni o'rnatish
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Xavfsiz non-root foydalanuvchi yaratish
RUN groupadd -r crmgroup && useradd -r -g crmgroup -d /app -s /sbin/nologin crmuser

# Loyiha kodlarini ko'chirish
COPY . .

# Ruxsatlarni berish
RUN chown -R crmuser:crmgroup /app

# Non-root foydalanuvchiga o'tish
USER crmuser

# Port
EXPOSE 8000

# Sog'lomlikni tekshirish (Healthcheck)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Ishga tushirish buyrug'i
CMD ["python", "run.py"]
