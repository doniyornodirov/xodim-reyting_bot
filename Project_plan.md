# 📋 Xodim-Reyting & Paynet CRM: To'liq Loyiha Rejasi (Project_plan.md)

> **Holati**: Loyiha to'liq ishlab chiqildi, mahalliy serverda (`http://127.0.0.1:8000`) ishga tushirildi va foydalanuvchining barcha talab va ko'rsatmalari asosida bosqichma-bosqich takomillashtirildi.  
> **Oxirgi yangilanish**: Kiritilgan barcha o'zgartirishlar, qat'iy rol chegaralari, toza interfeys qoidalari, **Sim-karta tarqatish (18 xonali seriya diapazoni) hamda Rahbar uchun seriya bo'yicha tezkor qidiruv paneli** to'liq hujjatlashtirildi va tizimga integratsiya qilindi.

---

## 1. 🎯 Loyiha Maqsadi
Paynet shaxobchasi va sim-karta ulanishlaridagi kundalik amaliyotlarni (karta to'ldirish, xodimga berilgan pullar, kassa topshirish va kunlik hisobotlar) avtomatlashtirish, xodimlar KPI reytingini hisoblash hamda Telegram Bot + Web CRM integratsiyasi orqali boshqarish.

---

## 2. 🛠️ Texnologik Stek va Xavfsizlik Arxitekturasi

### A. Texnologiyalar Ro'yxati:
1. **Backend & Dasturlash tili**: `Python 3.11+ / 3.12`
2. **Telegram Bot Freymvorki**: `aiogram 3.x` (Asinxron, FSM, Webhook/Polling, Inline tugmalar bilan)
3. **Web API Freymvorki**: `FastAPI` (Asinxron ASGI freymvork, Pydantic v2 validatsiya, avtomatik OpenAPI hujjatlari)
4. **Ma'lumotlar Bazasi**: `PostgreSQL 16` (ACID moliyaviy tranzaksiyalar, qat'iy munosabatlar va indekslar)
5. **ORM & Migratsiyalar**: `SQLAlchemy 2.0 (Async)` + `Alembic`
6. **Kesh va Navbatlar**: `Redis 7` (OTP kodlarni 60s TTL bilan saqlash, real-time leaderboard kesh, so'rovlarni cheklash)
7. **Frontend**: Zamonaviy, chiroyli va responsiv Web CRM (Kompyuter va telefon brauzerlariga to'liq moslashgan Single Page Application, kiritish maskalari, real-time reaktiv emojilar va hisob-kitoblar bilan).

### B. Ma'lumotlar Xavfsizligi va Integratsiya Parametrlari (GEMINI.md asosida):
1. **Rasmiy Telegram Konfiguratsiyasi**:
   - **Bot Tokeni**: `8932019841:AAFCkLdoBhzmkGJy3L0MY4-esw0_aToQiZY`
   - **Bosh Rahbar Telegram ID**: `8686341550` (Tizimga birlamchi Administrator huquqi bilan biriktirilgan)
   - **Telegram Guruh ID**: `-5381348358` (Karta to'ldirish so'rovlari va bildirishnomalar yuboriladigan rasmiy guruh)
2. **2FA / OTP (Ikki bosqichli autentifikatsiya)**:
   - Login va parol kiritilgach, tizim tasodifiy 6 xonali kriptografik xavfsiz OTP kod yaratadi.
   - Kod Redis'da `TTL = 60 soniya` bilan saqlanadi va bot orqali faqat xodimning shaxsiy Telegram lichkasiga yuboriladi.
   - Ekranda hech qanday sinov/dev xabarlari yoki o'rgatuvchi qavsli yozuvlar ko'rsatilmaydi; kod xavfsiz holda faqat bot orqali beriladi.
   - 1 daqiqadan oshsa kod bekor bo'ladi. Noto'g'ri kiritilsa kirish rad etiladi.
3. **Parollar va Sessiyalar**:
   - Parollar xesh orqali saqlanadi. Boshlang'ich parol Telegram ID, Rahbar istalgan payt parolni yangilay oladi.
   - JWT Access Token (15 daqiqa) + HttpOnly Secure Refresh Token.
4. **RBAC va Ruxsatlar**:
   - Tizimda 3 ta qat'iy ajratilgan rol: `Bosh Rahbar` (`ADMIN`), `Kassir` (`CASHIER`), `Xodim` (`EMPLOYEE`).
   - Guruhda so'rovlarni tasdiqlash: Faqat Telegram guruhining rasmiy adminlari (`getChatMember` orqali tekshiriladi).
5. **Bo'shatilgan xodim blokirovkasi**:
   - Rahbar xodimni ishdan bo'shatgan zahoti (`is_active = False`), bot ham, Web ilova ham xodim uchun bir zumda to'liq bloklanadi (barcha aktiv tokenlar bekor qilinadi).
6. **O'zgartirib bo'lmas Audit Log (Append-Only)**:
   - Har bir karta to'ldirish tasdiqlanishi/rad etilishi, hisobot qabul qilinishi va qarz belgilanishi `audit_logs` jadvalida kim, qachon, eski va yangi qiymat bilan qayd etiladi.

---

## 3. 📝 Kelishilgan Qoidalar va Biznes-Mantiq (So'rovnoma va Kiritilgan Aniq Talablar)

1. **3% Ustama hisobi va 1 000 So'mda Yaxlitlash**:
   - Xodim kiritgan summaning ustiga 3% qo'shiladi va **yuqoriga 1 000 so'mda yaxlitlanadi** (masalan: `50 000 so'm` bo'lsa -> `51 500` emas, balki `52 000 so'm`, `30 000 so'm` bo'lsa -> `31 000 so'm`).
   - **Eng kam summa**: Karta to'ldirish uchun kiritiladigan minimal summa qat'iy **30 000 so'm**.
   - **Reaktiv Emojilar va 100 000 000 so'm Rekordi**: Emojilar va statuslar summalarga moslangan bo'lib, `Rekord darajadagi summa! 🤑 💥` faqat summa **100 000 000 so'm (100 million)** va undan oshganda chiqadi (1mln yoki 10mln oddiy to'lov bosqichlarida aks etadi).
   - So'rov guruhda tasdiqlansa, kunlik hisobotdagi "Card" kirimiga avtomatik ravishda yaxlitlangan summa qo'shiladi.
2. **Guruhdagi Adminlik Huquqi**:
   - Telegram guruhdagi karta so'rovlarini "Tasdiqlash" va "Rad etish" tugmalarini guruhdagi barcha rasmiy Telegram adminlari bosa oladi. Bot ularning admin maqomini tekshiradi.
3. **Hisobot Topshirish va Qiymatlarni Dastlabki Holatga Qaytarish (Rollback) Qoidasi**:
   - Xodim hisobotni kuniga 1 marta, **Toshkent vaqti (+5) bilan 00:00 dan 23:59 gacha** topshiradi.
   - **Chalkashlikning oldini olish (Qiymatlarning o'z holiga qaytishi)**: Agar xodim qaytadan hisobot topshirsa va avvalgi hisobot hali Rahbar tomonidan tasdiqlanmagan bo'lsa (`Kutilmoqda` holatida), eski hisobot o'chib yangisi saqlanadi. Bunda eski hisobotdagi barcha oraliq hisob-kitoblar (xususan: "Qarz uchun" kiritilgan summa va hisoblangan qoldiqlar) to'liq bekor qilinadi va qiymatlar asl boshlang'ich holatiga qaytariladi. Shundan so'ng yangi hisobot toza ko'rsatkichlar bilan qabul qilinadi.
4. **Qarzdorlikning Ertangi Kunga O'tishi**:
   - Agar xodim o'ziga belgilangan qarzni o'sha kuni to'liq yopmasa, qolgan qarzdorlik summasi avtomatik ravishda ertangi kungi hisobotga qarz sifatida o'tadi va to'liq yopilguncha saqlanadi.
5. **Rollarning Mutlaq Ajratilishi Qoidasi (Rahbar vs Kassir vs Xodim)**:
   - **Bosh Rahbar**: Tizimga kirganda u xodim emas, balki nazoratchi/administrator hisoblanadi. Shuning uchun Rahbar uchun xodim amaliyot shakllari (`Karta to'ldirish`, `Berilgan summa`, `Hisobot topshirish`) aslo ko'rsatilmaydi. U to'g'ridan-to'g'ri `Kunlik hisobotlar` bo'limiga kiradi va faqat boshqaruv/tasdiqlash bilan shug'ullanadi.
   - **Kassir (`Cashier`)**: Tashkilotdagi xodimlardan biri bo'lib, Rahbar tomonidan bugungi kunga kassir etib tayinlanadi. U oddiy xodim vazifalarini bajarish bilan birga, faqat unga ochiladigan qo'shimcha "Kassadan pul qabul qilish" oynasi orqali boshqa xodimlardan naqd pulni qabul qiladi.
   - **Xodim (`Employee`)**: Faqat o'zining kundalik amaliyotlarini bajaradi (karta to'ldirish, berilgan summa, hisobot topshirish, shaxsiy reyting).
6. **Toza Korporativ Interfeys Qoidasi**:
   - Maydonlar ustidagi va qavs ichidagi o'quv/tushuntirish yozuvlari (`(qo'lda kiritiladi)`, `(avtomatik)`, `(faqat harflar)`, `(donada raqam yoziladi)`, `card-desc` paragraflari) butunlay olib tashlandi.
   - Interfeys professional korporativ uslubda, faqat zaruriy kiritish maydonlari va maskalari bilan ishlaydi.
7. **Plandagi Misollarni Kodga Aralashtirmaslik Standarti**:
   - Rejada tushuntirish uchun keltirilgan ism-familiyalar (masalan: `Aliyev Vali`, `Rustamov Bobur`) yoki shartli karta raqamlari faqat konsepsiyani tushuntirish uchun bo'lib, haqiqiy tizimda ular mavjud emas. Tizimda toza formatlar (`0000 0000 0000 0000`, `0`) qo'llaniladi.
8. **To'liq O'zbek Tili Standarti**:
   - Tizimdagi barcha rollar, statuslar va bildirishnomalar sof o'zbek tilida:
     - `ADMIN` -> `Bosh Rahbar`
     - `CASHIER` -> `Kassir`
     - `EMPLOYEE` -> `Xodim`
     - `APPROVED` -> `Tasdiqlandi ✅`
     - `REJECTED` -> `Rad etildi ❌`
     - `PENDING` -> `Kutilmoqda ⏳`
9. **Sim-karta Tarqatish va Seriya Bo'yicha Qidiruv Qoidasi**:
   - **Sim-karta Turlari (Operatorlar)**: Tizimda 5 ta asosiy mobil operator sim-kartalari qo'llab-quvvatlanadi: `Uzmobile`, `Beeline`, `Ucell`, `Mobiuz`, `Perfectum`.
   - **Tarqatish (Rahbar va Kassir)**: Sim-karta bazaga kiritilayotganda uning turi (operatori) tanlanadi, seriyasi 18 ta raqamdan iborat maydonlarga faqat raqam kiritiladi. Kiritish diapazon ("Boshlang'ich seriya raqami" dan "Tugash seriya raqami" gacha) ko'rinishida amalga oshiriladi va xodimlar ro'yxatidan qabul qiluvchi xodim tanlanadi.
   - **Oxirgi tarqatilganlar jadvali (Partiya ko'rinishida)**: Sim-karta tarqatilganda jadvalda har bir dona sim-karta alohida qator bo'lib chiqmaydi. Ular 1 ta yaxlit qator sifatida `boshlang'ich dan tugash gacha (X dona)` diapazoni shaklida ixcham aks ettiriladi.
   - **Seriya Bo'yicha Qidiruv (Rahbar)**: Bosh Rahbar 18 xonali sim-karta seriyasini yozib qidirganda, tizim ushbu sim-kartaning **turi (Uzmobile, Beeline, Ucell, Mobiuz, Perfectum)**, qaysi xodimga berilganligi, qachon berilganligi, kim tomonidan tarqatilganligi va holatini bir zumda ko'rsatib beradi.
10. **Toshkent Vaqti (UTC+5) va Sana Formati Standarti**:
    - Tizimdagi barcha amaliyotlar (karta to'ldirish, berilgan summa, hisobotlar, kassir operatsiyalari, sim-karta tarqatish va audit loglar) qat'iy ravishda **Toshkent vaqti (UTC+5)** bilan aks ettiriladi.
    - Vaqt formati: `DD.MM.YYYY HH:mm` (audit loglarda aniqlik uchun `DD.MM.YYYY HH:mm:ss`).
    - Sana formati: `DD.MM.YYYY` (kun.oy.yil).
    - SQLite bazasidagi UTC vaqtlar frontendga uzatilganda +5 soatlik farq to'liq hisobga olinadi va hech qanday kechikishsiz to'g'ri ko'rsatiladi.
11. **Dollar Kursi Boshqaruvi va Doimiy Ko'rinishi Standarti**:
    - Tepa o'ng burchakdagi foydalanuvchi profil panelida doimiy **Dollar kursi nishoni** (masalan: `💵 1$ = 12 000 so'm`) joylashtirilgan.
    - **Bosh Rahbar uchun**: Kurs ustiga bosilganda kursni o'zgartirish/belgilash modali ochiladi. Yangi kurs kiritilgach, u bazada saqlanadi va `audit_logs` ga kim tomonidan o'zgartirilganligi yoziladi.
    - **Xodimlar va Kassirlar uchun**: Kurs har doim ko'rinib turadi (masalan: `1$ = 12 000 so'm`), lekin ular uni o'zgartira olmaydi (faqat ma'lumot sifatida ko'rinadi).
12. **Hisobotlarni Kalendar Bo'yicha Saralash va To'liq Tafsilotlarni Ko'rish Standarti**:
    - **Kalendar filtri**: "Hisobotlarni qabul qilish" panelida sana bo'yicha kalendar tanlash maydoni, "Bugun" va "Barcha sanalar" tezkor filtrlari joylashtirilgan. Rahbar istalgan sanani tanlab o'sha kundagi barcha topshirilgan hisobotlarni saralab ko'ra oladi.
    - **To'liq tafsilotlar (Kirim, Chiqim va Sof Kassa)**: Hisobotlar jadvalida har bir hisobotning Kirim tarkibi (`Paynet`, `Karta(+3%)`, `Leviy`) va Chiqim tarkibi (`Kunlik`, `Terminal`, `Berildi`, `Xarajat`) ko'rinadi. Shuningdek, `👁️ Batafsil` tugmasi orqali hisobotning har bir parametri va xodim izohi to'liq 2 ustunli modalda aks ettiriladi.
13. **Kassa Qabul Qilishda So'm va Dollar Taqsimoti, Tarix va Xodimlar Ro'yxatidan O'chish Standarti**:
    - **Valyuta taqsimoti**: Kassir xodimdan kassa topshirish summasini qabul qilayotganda qanchasi so'mda (`amount_uzs`) va qanchasi dollarda (`amount_usd`) ekanligini alohida kiritadi.
    - **Dollar kursi avtomatik tizimdan olinadi**: Dollar kursini kassir belgilamaydi yoki o'zgartira olmaydi! Tizim amaldagi Rahbar belgilagan rasmiy kursni avtomatik oladi va jami summani real-vaqtda ekvivalent formula asosida hisoblaydi (`Jami = So'm + (Dollar * Tizim_Kursi)`).
    - **Tarixning o'zaro ko'rinishi (Kassir va Rahbar uchun birdek)**: Kassir qabul qilsa Rahbar tarixida ham, Rahbar kassir rejimida qabul qilsa Kassir tarixida ham ushbu yozuvlar to'liq ko'rinadi va kim tomonidan qabul qilinganligi (`Qabul qildi` ustunida) aks ettiriladi.
    - **Summa topshirgan xodim ro'yxatdan o'chib borishi**: Bugungi kunda kassa topshirgan xodim o'sha kun uchun "Xodimni tanlang" dropdown ro'yxatidan avtomatik chiqariladi (o'chib boradi). Qayta kassa qabul qilish shaklida faqat bugun hali kassa topshirmagan xodimlar ko'rinadi.
    - **Telegram Botdan xodimga chek**: Kassir kassa topshirilishini tasdiqlagan zahoti, xodimning shaxsiy Telegramiga rasmiy formatlangan elektron qabul cheki bot orqali yuboriladi (Qabul qilingan sana, vaqt, Kassir F.I.Sh, So'm miqdori, Dollar miqdori, Dollar kursi va Jami ekvivalent summa).
14. **Sim-karta Biriktirilganda Telegram Xabari va Rollar Chegaralari Standarti**:
    - **Sim-karta Telegram xabari**: Rahbar yoki Kassir xodimga yangi sim-kartalar partiyasini biriktirganda, xodimning shaxsiy Telegramiga nechta sim-karta olinganligi (`count`), 18 xonali boshlang'ich va tugash seriya raqamlari diapazoni, operator turi (`Uzmobile`, `Beeline`, `Ucell`, `Mobiuz`, `Perfectum`), kim tomonidan tarqatilganligi va Toshkent vaqti ko'rsatilgan rasmiy bildirishnoma yuboriladi.
    - **Rahbarning Kassir roliga o'tishi va cheklovlar**: Rahbar istalgan vaqtda "💼 Kassir rejimi"ga o'tib kassa qabul qilish yoki sim-karta tarqatish amallarini bajara oladi. Biroq **Rahbar aslo xodim bo'la olmaydi** — unga xodimning shakllari (karta to'ldirish, olingan summa so'rash, kunlik hisobot topshirish) ko'rsatilmaydi hamda "Xodimni tanlang" (Kassa qabul qilish, Sim-karta tarqatish, Qarz belgilash) kabi barcha xodimlar ro'yxati va dropdownlaridan Rahbar mutlaqo chiqarib tashlanadi (Rahbar hech qayerda xodim sifatida tanlanmaydi). Istalgan payt "⬅️ Rahbar paneliga qaytish" orqali o'z paneliga qaytadi.
    - **Kassir va Xodim almashinuvi**: Kassir asosiy maqomida xodimdir. Rahbar xodimlar ro'yxatidan istalgan xodimni Kassir etib saylashi (`💼 Kassir qilish`) yoki uni xohlagan vaqtda kassirlikdan ozod qilib yana oddiy xodim roliga qaytarishi (`👤 Xodim qilish`) mumkin.
15. **Qarzdorlik va Qarz Uchun To'lovning Kirimga Ta'siri Standarti**:
    - **Qarzdorlik kirimga qo'shilmaydi**: Xodimning mavjud qarzdorligi (`debt_snapshot`) faqat ma'lumot sifatida ko'rsatiladi va kunlik kassa kirimiga aslo qo'shilmaydi (`total_inflow = paynet + card + leviy`).
    - **Qarz uchun to'lov kirimga qo'shiladi**: Agar xodim "Qarz uchun to'lov" maydoniga summa kiritsa (`debt_paid > 0`), bu naqd summa kassa kirimiga qo'shiladi (`total_inflow = paynet + card + leviy + debt_paid`), chunki xodim o'z qarzini to'lash uchun kassaga mablag' topshirgan bo'ladi.
    - **Qarzdorlikdan ayrilib boriladi**: Xodim qarz uchun to'lov summasini kiritganida "Qarzdorlik" maydoni real-vaqt rejimida qolgan qarzni kamaytirib (`qarzdorlik - qarz uchun to'lov`) boradi va hisobot tasdiqlanganda bazadagi qarzdorlikdan ham ushbu summa rasman chegiriladi.
16. **Bir xil karta raqamiga takroriy so'rov yuborilganda "Bugun bu kartaga to'lov qilindi" ogohlantirish qoidasi**:
    - **Qoida sharti**: Agar bitta karta raqamiga kun davomida (Toshkent vaqti bilan) karta to'ldirish so'rovi yuborilib tasdiqlangan bo'lsa yoki bir kunda ushbu karta raqamiga 2 va undan ortiq so'rov yuborilsa, tizim ushbu kartani takroriy deb aniqlaydi.
    - **Telegram guruh xabari**: Guruhga boradigan so'rov xabarining oxiriga qat'iy ravishda quyidagi ogohlantirish qo'shiladi:
      `⚠️ DIQQAT: Bu kartaga bugun to'lov qilindi! 🔄`
    - **Vaqt va Sanani hisoblash standarti**: SQLite bazasida UTC vaqt saqlanishi sababli, so'rovlarni solishtirish qat'iy Toshkent vaqti (`DATE(created_at, '+5 hours') = DATE('now', '+5 hours')`) va bo'sh joylarsiz tozalangan karta raqami (`REPLACE(card_number, ' ', '')`) bo'yicha amalga oshiriladi. Bu esa sutkaning istalgan vaqtida (shu jumladan tungi 00:00 dan 05:00 gacha ham) takroriy so'rovlarni 100% aniqlik bilan tutib beradi va ogohlantirish xabari chiqishini ta'minlaydi.
17. **Hisobot Tasdiqlanganda Xodimning Sotilgan Sim-kartalari Balansga Qo'shilishi Standarti**:
    - **Qoida sharti**: Xodim kunlik hisobot topshirishda kiritgan sim-kartalar soni (`sim_cards_count`), Rahbar hisobotni tasdiqlagan (`status = 'APPROVED'`) zahoti avtomatik ravishda:
      1) "Xodimlar sim-karta balansi" panelidagi **'Sotilgan'** ustuniga qo'shiladi (`sold_count`).
      2) Xodimning **'Qo'lidagi (Xodimda)'** zaxirasidan mos miqdorda avtomatik chegiriladi (`in_stock = total_given - sold_count`).
      3) `sim_cards` jadvalida xodimning sim-kartalari holati `status = 'SOLD'` va `sold_at` vaqti bilan rasmiylashtiriladi.
    - **Rad etilganda qaytarish**: Agar oldin tasdiqlangan hisobot keyinchalik rad etilsa (`REJECTED`), sotilgan deb belgilangan sim-kartalar avtomatik ravishda yana xodimning qo'lidagi holatiga (`GIVEN`) qaytariladi.
18. **Tizimga Kirishda 1 Minutda 1 Marta Urinish va Qayta Urinish Cooldown Standarti**:
    - **Qoida sharti**: Tizimga kirishda (Login Step 1 va Step 2) bir daqiqada faqat 1 marta urinish mumkin. Bir marta urinilgandan so'ng, keyingi qayta urinish faqat 1 minut (60 soniya) o'tgandan keyingina amalga oshirilishi mumkin.
    - **Interfeysdagi nazorat (Step 2)**: 6 xonali OTP tasdiqlash oynasidagi "⬅️ Qaytadan urinish" (`#btn-retry-login`) tugmasi 60 soniyalik teskari hisob (countdown) tugamaguncha faolsizlantiriladi (`disabled`, `opacity: 0.5`, `cursor: not-allowed`) va tugma matnida qolgan soniyalar real-vaqtda ko'rsatib boriladi (masalan: `⏳ Qaytadan urinish (42s)`). Faqatgina 60 soniya to'liq tugagach, tugma yana faol holatga (`🔄 Qaytadan urinish`) o'tadi va bosilganda 1-qadamga qaytaradi.
    - **Serverdagi qat'iy nazorat (Backend Rate Limiting)**: Agar foydalanuvchi sahifani yangilasa yoki to'g'ridan-to'g'ri API orqali 60 soniya ichida qayta kirishga urinsa, server darajasida (`/api/auth/login`) ma'lumotlar bazasidagi oxirgi OTP yaratilgan vaqt tekshiriladi va HTTP 429 (Too Many Requests) xatoligi bilan qolgan soniyalar ko'rsatilgan xabar qaytariladi: `"1 minutda faqat 1 marta urinish mumkin! Qayta urinish {seconds_left} soniyadan keyin."`.
19. **Mobil, Planshet va Kompyuter Uchun To'liq Responsiv Interfeys Standarti (Cross-Device Responsive Engine)**:
    - **Kompyuter (Desktop > 1024px)**: Keng ekranli boshqaruv panellari, zamonaviy ko'p ustunli setkalar (`.grid-2`, `.grid-3`), sarlavha va status panellari to'liq qatorda joylashadi.
    - **Planshet (Tablet 769px - 1024px)**: Boshqaruv modullari va tablar gorizontal suriladigan (swipe) silliq lentaga o'tadi, jadvallar sensorli surilish bilan to'liq ma'lumotlarni qulay ochib beradi, formalar 2 ustunli optimal ko'rinishga moslashadi.
    - **Mobil Qurilmalar (Mobile < 768px va < 480px)**:
      1) **Navigatsiya (Navbar)**: 2 pog'onali ixcham va chiroyli tartibga o'tadi. Yuqorida brend logosi va Dollar kursi nishoni, pastki qatorda esa xodim profili, roli, qarzi, kassir rejimi va chiqish tugmasi qulay joylashadi.
      2) **Tablar lentasi**: Barcha 9 ta Rahbar yoki 4 ta Xodim modullari vertikal taxlanib ekranni to'sib qo'ymasligi uchun, barmoq bilan gorizontal suriladigan (swipeable touch ribbon) zamonaviy mobil ilova ko'rinishiga keltirildi.
      3) **Formalar va kiritish maydonlari**: 1 ustunli vertikal moslashuvchan tartibga o'tkazildi, mobil ekranlarda kiritish vaqtida iOS va Android klaviaturalarida ekranning noqulay yaqinlashib (auto-zoom) ketishining oldini olish uchun shriftlar va teginish maydonlari (kamida 44px) standartlashtirildi. Karta raqami va OTP kodlari har qanday ekran kengligiga avtomatik moslashuvchi `clamp()` formulasi bilan himoyalandi.
      4) **Jadvallar va modallar**: Barcha jadvallar gorizontal teginish bilan qulay suriladi, modallar esa mobil ekranga to'liq moslashib, ma'lumotlarni bemalol o'qish va tugmalarni qulay bosish imkoniyatini ta'minlaydi.
20. **Yagona Kassir Standarti va Oldingi Kassirning Avtomatik Oddiy Xodimga Aylanish Qoidasi**:
    - **Qoida sharti**: Tizimda Rahbar tomonidan tayinlanadigan Kassir (`CASHIER`) bir vaqtning o'zida qat'iy **faqat 1 ta** bo'ladi.
    - **Avtomatik almashtirish (Auto-demotion)**: Rahbar qaysi moduldagi amallar orqali bo'lishidan qat'i nazar ("Kassir tayinlash" panelidan yoki "Xodimlar boshqaruvi" jadvalidagi `💼 Kassir qilish` tugmasidan) yangi xodimni kassir etib tayinlasa, bazadagi mavjud oldingi barcha kassirlar avtomatik ravishda oddiy xodim (`role = 'EMPLOYEE'`) holatiga qaytariladi.
    - **Tarix va Audit yozuvi**: Yangi kassir tayinlanganda `cashier_history` jadvalida:
      1) Oldingi kassir uchun `DISMISSED` ("Oddiy xodim holatiga qaytdi") amali saqlanadi.
      2) Yangi kassir uchun `APPOINTED` ("Kassir etib tayinlandi") amali saqlanadi.
      3) `audit_logs` jadvaliga kim kimni tayinlagani va qaysi oldingi kassir xodimga aylangani to'liq qayd etib boriladi.
    - **Xavfsizlik**: Bosh Rahbar hech qachon kassir etib tayinlanishi mumkin emas, va ishdan bo'shatilgan (`is_active = 0`) xodimlar ham kassir bo'la olmaydi.
21. **Aqlli Responsiv Menyu va [☰ Menyu] Tugmasi Ko'rinish Qoidasi**:
    - **Qoida sharti**: `[ ☰ Menyu ]` tugmasi faqat ekranga xalaqit beradigan darajaga kelganda (masalan, telefonlar va ekrani kichik planshetlarda, `<= 1024px`) chiqadi. Ulardan kattaroq ekranlarda (kompyuter, noutbuk, katta monitorlarda) tepadagi gorizontal menyu o'z holida to'liq ko'rinib turadi, `[ ☰ Menyu ]` tugmasi esa mutlaqo ko'rinmaydi (`display: none`).
    - **Interfeysdagi ishlashi**:
      1) **Katta ekranlar (> 1024px)**: `[ ☰ Menyu ]` tugmasi yashiringan. Barcha bo'limlar (`💳 Karta to'ldirish`, `💵 Berilgan summa`, `📊 Hisobot topshirish` va boshqalar) navbardan pastda o'zining tabiiy gorizontal ko'rinishida erkin va chiroyli turadi.
      2) **Kichik ekranlar (telefon va kichik planshetlar, <= 1024px)**: Tepadagi gorizontal menyu ekranga xalaqit bermasligi va joyni tejash uchun avtomatik yashiriladi (`display: none !important`). Buning o'rniga navbarda `[ ☰ Menyu ]` tugmasi paydo bo'ladi (`display: inline-flex !important`).
      3) Ushbu tugma bosilganda chap tomondan silliq animatsiya bilan to'liq qoramtir-shaffof (glassmorphic) yon menyu paneli ochiladi.
      4) Menyuda foydalanuvchi profil ma'lumotlari (ism, rol, qarz) va uning roliga mos barcha bo'limlar vertikal qulay ro'yxatda (har biri o'z emojisi va yorqin nishonlari bilan) hamda pastda doimiy "Tizimdan chiqish 🚪" tugmasi bilan aks etadi.
      5) **Mobil Navbar Ixchamligi**: Telefon va planshetlarda tepadagi navbar ekranning ko'p qismini olib qo'ymasligi uchun `[ 💼 Kassir ]`, `Qarz: ...` va `Chiqish 🚪` tugmalari navbardan yashirilib, to'liq chapdagi `[ ☰ Menyu ]` ichiga o'tkazildi. Shu tufayli mobil navbar bitta toza va ingichka qatorda qulay joylashadi.
      6) Istalgan bo'lim tanlanganda menyu avtomatik yopilib, kerakli sahifa bir zumda ochiladi.
      7) Tashqariga yoki `✕` tugmasiga bosilganda yoki klaviaturadagi `Esc` tugmasi orqali menyu bir zumda yopiladi.
22. **Barcha Interfeys Elementlarining O'ziga Xos Responsiv Standarti**:
    - **Jadvallar (Tables)**: Gorizontal surilganda adashib ketmaslik uchun birinchi ustun (Tartib #, Xodim yoki ID) doimiy chapga yopishib (`position: sticky; left: 0;`) turadi. Keng jadvallarda maxsus ingichka binafsharang silliq scrollbar va ma'lumotlar ustunlari (`white-space: nowrap`) joriy etildi.
    - **Ogohlantirish va Reaktiv Bloklar**: Qizil ogohlantirish banneri kichik ekranlarda ixcham va yorqin pulsatsiyalovchi alert kartaga aylanadi. Karta to'ldirishdagi reaktiv blok (+3% ustama va so'z bilan o'qilish) har qanday ekranda matn sig'ishi uchun dinamik `clamp()` o'lchamlariga ega.
    - **Kiritish Maydonlari Orasini Qisqartirish**: Formalardagi barcha kiritish maydonlari (masalan, Paynet, Karta, Leviy, Qarzdorlik, Qarz uchun to'lov) orasidagi ortiqcha bo'shliqlar 50% dan ortiqqa ixchamlashtirildi (`gap: 0.42rem`, `margin-bottom: 0 !important`), maydonlar yorliqlari (label) va kiritish darchalari orasi yaqinlashtirildi, bu orqali butun forma bitta ekranga bemalol sig'ishi ta'minlandi.
    - **Formalar va Kiritish Maydonlari**: 16 va 18 xonali raqamlar (karta raqami, OTP kodi, sim-karta seriyalari) kichik smartfonlarda ham kesilib qolmasligi uchun `clamp()` orqali moslashadi. Barcha tugma va maydonlar sensorli ekranda qulay bosilishi uchun kamida `38-44px` balandlikka ega.
    - **Kassa va Ekvivalent Bannerlari**: Hisobotdagi Kirim/Chiqim/Net banneri hamda Kassirning So'm + Dollar ekvivalent hisob-kitob bloki mobilda 2 pog'onali premium kartaga aylanadi.
    - **Modallar va Reyting Bo'limi**: Modallar mobilda sensorli boshqaruvga mos pastdan chiquvchi (bottom sheet) formatga o'tadi; Reyting filtrlari ("Oylik reyting" va "Umumiy reyting") barmoq bilan bosishga qulay 50/50 segmentli tugmalarga aylanadi.
23. **Tungi (Dark mode) va Kunduzgi (Day mode) Rejim Standarti**:
    - **Rejimlar**: Tungi rejim (chuqur to'q ko'k/qora `#0b0f19`, neon binafsharang va feruza aksentlar) hamda Kunduzgi rejim (och oq/kulrang `#f8fafc`, toza oq kartalar, chuqur to'q matn `#0f172a`, yuqori kontrast va silliq soyalar).
    - **Sozlash tugmasining joylashuvi**:
      1) **Kompyuter ekrani (> 1024px)**: Tepadagi o'ng burchakda (`#nav-user-area`), Dollar kursi, Foydalanuvchi ma'lumotlari va Chiqish tugmasi yonida `[ 🌙 Tungi ]` / `[ ☀️ Kunduzgi ]` tugmasi joylashgan.
      2) **Kichik va responsiv ekranlar (<= 1024px)**: Ekranni to'ldirib qo'ymaslik uchun yuqori o'ng burchakdagi tugma avtomatik yashiriladi (`display: none !important`), va mavzuni boshqarish to'g'ridan-to'g'ri `[ ☰ Menyu ]` (sidebar drawer) ichidagi pastki panelga (`sidebar-footer`) o'tadi: `[ 🌙 Rejim: Tungi rejim ]` / `[ ☀️ Rejim: Kunduzgi rejim ]`.
    - **Xotirada saqlash**: Foydalanuvchi tanlagan rejim brauzerning `localStorage` xotirasida (`app_theme`) saqlanadi va sahifa qayta yuklanganda fonga ko'z qamashishisiz (zero-flicker) o'sha rejimda ochiladi.
    - **O'tish effektlari**: Rejim almashtirilganda barcha kartalar, fonlar, matnlar va jadvallar `0.25s` silliq animatsiya bilan o'zgaradi va ekranda chiroyli xabarnoma (Toast) aks etadi.
24. **Faqatgina Rahbar Uchun Savdo Monitoringi va Diagrammalar Standarti**:
    - **Kirish Huquqi (Access Control)**: Faqat `Bosh Rahbar` (Admin) roliga ega foydalanuvchilar uchun ochiq. Xodimlar yoki Kassirlar uchun ushbu modul va backend endpoint (`/api/admin/analytics/monitoring`) mutlaqo yopiq (HTTP 403 Forbidden).
    - **Monitoring qilinadigan asosiy ko'rsatkichlar**:
      1) **Umumiy topshirilayotgan summalar**: Xodimlar topshirgan kassa tushumi (`total_inflow`) va kassaga topshirilishi kerak bo'lgan sof summa (`net_amount`).
      2) **Sotilayotgan sim-kartalar**: Kunlik sotilgan sim-kartalar soni (dona).
      3) **To'ldirilayotgan kartalar**: Tasdiqlangan karta to'ldirish summasi (+3% ustama bilan) va to'ldirishlar soni.
    - **O'sish va Pasayish Dinamikasi (Trend & Growth %)**:
      - Har bir metrika uchun tanlangan davr (masalan, oxirgi 7 kun yoki 30 kun) o'tgan teng muddat bilan solishtirilib, o'sish/pasayish foizi aniqlanadi: `🟢 +X.X%` (O'sish ↗️) yoki `🔴 -X.X%` (Pasayish ↘️).
    - **Vaqt miqyosidagi diagrammalar (Charts)**:
      1) **Asosiy Ko'p Tarmoqli Dinamika Diagrammasi**: Vaqt shkalasi bo'yicha kassa tushumi, to'ldirilgan kartalar va sotilgan sim-karta egri chiziqlari (Area/Line) va interaktiv ma'lumotlar nishoni (tooltip). Metrika tanlovchi: "Hammasi", "Topshirilgan summa", "Sim-kartalar", "Karta to'ldirish".
      2) **Kunbay O'sish/Pasayish Bar Chart**: Har bir kunning o'tgan kunga nisbatan o'sish (yashil) va pasayish (qizil) foizlarini ko'rsatuvchi ustunli diagramma.
      3) **Operatorlar Bo'yicha Sim-karta Taqsimoti (Doughnut Chart)**: Uzmobile, Beeline, Ucell, Mobiuz, Perfectum sotuvlari ulushi.
    - **Filtrlar**: `Oxirgi 7 kun`, `Oxirgi 30 kun`, `Joriy oy`, `Barcha davr`.
    - **Kunlik tafsilotlar jadvali**: Barcha kunlik sonlarni solishtirish jadvali.
    - **Moslashuvchanlik**: Chart.js va offline Canvas fallback asosida to'liq responsiv, mobil va kompyuterga mos, Tungi va Kunduzgi mavzular bilan uyg'un ishlaydi.
25. **Tailwind CSS v3 va Tailwind UI Dizayn Tizimi (Tungi va Kunduzgi Rejim Mukammalligi)**:
    - **Tailwind UI Dizayn Tili**: Sayt CRM interfeysi to'liq Tailwind CSS v3 (CDN) va uning rasmiy Slate & Indigo dizayn tizimiga muvofiqlashtirildi (`slate-950`/`slate-900` dark theme, `slate-50`/white light theme, indigo accents `#4f46e5`, emerald `#10b981`, amber `#f59e0b`, rose `#f43f5e`).
    - **Tungi Rejim (Dark mode)**: Chuqur Slate 950 (`#020617`) foni, Slate 900 (`#0f172a`) kartalar, Slate 800 (`#1e293b`) chegaralar va kirish maydonlari, mayin Indigo 600 (`#4f46e5`) va Violet aksentlar, pastel yorqinlikdagi pill chiplar (`rounded-full`), doimiy ko'rinadigan qoramtir birinchi ustunli (sticky) ma'lumotlar jadvallari.
    - **Kunduzgi Rejim (Day / Light mode)**: Toza Slate 50 (`#f8fafc`) foni, oq (`#ffffff`) kartalar, Slate 200 (`#e2e8f0`) nafis chegaralar, Slate 900 (`#0f172a`) va Slate 600 (`#475569`) yuqori kontrastli korporativ matnlar, yumshoq yorug'lik soyalari (`shadow-sm`, `shadow-md`), och pastel nishonlar (`rose-50/700`, `amber-50/700`, `indigo-50/700`, `emerald-50/700`), hamda ko'zni toliqtirmaydigan qulay o'qiluvchanlik.
    - **Segmented Control Tablar**: Barcha Rahbar va Xodim modullari Tailwind UI segmented control uslubiga keltirildi (faol holatda Indigo 600, `shadow-md`, silliq o'tishlar).
    - **Interaktiv Sinxronizatsiya**: Rejim almashtirilganda bir vaqtning o'zida `localStorage` saqlanadi, `<html>` va `<body>` teglari `dark` hamda `theme-light` sinflari bilan sinxron yangilanadi va barcha Chart.js grafiklari yangi rejim ranglariga mos qayta chiziladi.
26. **90-Kunlik Ma'lumotlarni Saqlash va Avtomatik Tozalash Standarti (Rolling 90-Day Retention Policy)**:
    - **Qoida sharti**: Tizimdan foydalanish jarayonida hosil bo'ladigan barcha operatsiya, tranzaksiya va tarixiy ma'lumotlar qat'iy **90 kun davomida** saqlanadi.
    - **Avtomatik tozalash (Retention Scheduler)**: 90 kundan oshgan eski ma'lumotlar fonda avtomatik ravishda tozalanib boriladi, yangi ma'lumotlar esa uzluksiz yoziladi (xulosa: tizimda doimiy 90 kunlik yangi tarix saqlanadi).
    - **Qamrab olinadigan tarixiy jadvallar**:
      1) `card_topups` — Karta to'ldirish so'rovlari va tarixi (`created_at`).
      2) `given_amounts` — Berilgan summalar so'rovlari va tarixi (`created_at`).
      3) `daily_reports` — Kunlik hisobotlar tarixi (`report_date` va `created_at`).
      4) `cashier_handovers` — Kassir topshirgan summalar tarixi (`handover_date` va `created_at`).
      5) `cashier_history` — Kassirlik tayinlash tarixi (`created_at`).
      6) `otp_codes` — Eskirgan bir martalik tasdiqlash kodlari.
      7) `sim_cards` — Faqat sotilgan (`status = 'SOLD'`) sim-kartalar tarixi. Xodim qo'lidagi sotilmagan sim-karta zaxirasi (`status = 'GIVEN'`) aslo o'chirilmaydi va xodim hisobida xavfsiz saqlanadi.
      8) `sim_distributions` — Sim-karta partiyalari tarixi (`created_at`).
      9) `audit_logs` — Tizim audit jurnali yozuvlari.
    - **Fonda va Ishga Tushishda Avtomatlashtirish**: Tizim har gal ishga tushganda (startup lifespan) 90 kunlik chegarani tekshiradi hamda fonda har 24 soatda (`asyncio` scheduler) muntazam tozalash vazifasini bajaradi.
    - **Indekslar va Yuqori Yuklama (High-Load)**: Barcha sana ustunlari bo'yicha indekslar yaratilgan, tozalash jarayoni API so'rovlarini aslo bloklamaydi va SQLite bazasini optimal holatda ushlab turadi.
27. **Bulutli Arxitektura va Uzluksiz Ishlash Standarti (Vercel, Railway, Supabase & Self-Healing)**:
    - **Statik Frontend (Vercel)**: Tizim interfeysi serverdan ajratilgan holda global Anycast CDN va avtomatik SSL ta'minlovchi Vercel platformasiga joylashtiriladi (`vercel.json`).
    - **Backend va Telegram Bot (Railway / Hetzner)**: FastAPI va aiogram boti Docker konteynerida (`Dockerfile`, `docker-compose.yml`) yoki PM2 / systemd orqali yurgiziladi.
    - **Ma'lumotlar Xavfsizligi va Zaxiralash (Supabase PostgreSQL)**: Barcha ma'lumotlar avtomatik kunlik zaxiralanuvchi (automated daily backups) bulutli PostgreSQL bazasida (`supabase_schema.sql`) saqlanadi.
    - **O'z-o'zini tiklash (Self-Healing)**: Docker'ning `restart: always` siyosati, PM2'ning `autorestart: true` va `max_memory_restart: 500M` ko'rsatkichlari, hamda `/health` monitoringi orqali tizim kutilmagan to'xtashlarda inson aralashuvisiz bir necha soniyada qayta ko'tariladi.

---

## 4. 🖥️ Foydalanuvchi Interfeyslari va Panellar

### A. Xodim Paneli (Tartib bilan 4 ta asosiy oyna)

1. **Karta To'ldirish Oynasi**:
   - **Ogohlantirish**: Maydon ustida doimiy eslatma: *"Sizning birgina xatoyingiz sizni qiyin ahvolga soladi"*.
   - **Karta raqami**: 16 xonali, har 4 raqamdan keyin bo'sh joy (`0000 0000 0000 0000`), faqat raqam, majburiy.
   - **Karta egasi**: Faqat harflar, majburiy.
   - **Summa**: Faqat raqam, har 3 tadan probel ajratgich bilan.
     - So'z bilan o'qilishi avtomatik ko'rsatiladi.
     - 3% ustama bilan mijozdan olinadigan yakuniy summa real-vaqtda hisoblanadi.
     - Summa hajmiga qarab reaktiv emojilar (😃 -> 😲 -> 🤯 -> 🤑).
   - **Tugma**: "Karta to'ldirish".
   - **Tarix jadvali**: So'rovlar ro'yxati va holati: `Kutilmoqda ⏳`, `Tasdiqlandi ✅`, `Rad etildi ❌`.
   - **Telegram Guruhga Yuboriladigan Format**:
     - Tartib raqami, xodim ismi, nusxalanadigan karta raqami, karta egasi, kiritilgan summa va +3% ustamasi.
     - Ortiqcha matnlarsiz, faqat emojilar va qiymatlar (👤 Ism, 🔢 Karta raqami, 🏷️ Egasi, 💰 Summa, 📈 +3% ustama; "(nusxalash uchun bosing)" yoki maydon so'zlarisiz faqat toza emojilar).
     - Bir kunda bir xil kartaga takroriy to'lov bo'lsa: `⚠️ Bu kartaga bugun to'lov qilindi!` ogohlantirishi.
     - Faqat guruh rasmiy adminlari uchun `[ ✅ Tasdiqlash ]` va `[ ❌ Rad etish ]` tugmalari.

2. **Berilgan Summa Oynasi**:
   - **Summa**: Faqat raqam, kiritish maskasi bilan.
   - **Izoh**: Faqat matn, majburiy.
   - **Tarix jadvali**: Yuborilgan so'rovlar holati (`Kutilmoqda ⏳`, `Tasdiqlandi ✅`, `Rad etildi ❌`).

3. **Hisobot Topshirish Oynasi**:
   - **Kirimlar**:
     - `Paynet` (faqat raqam).
     - `Card` (Tasdiqlangan karta so'rovlaridan avtomatik +3% bilan to'ldiriladi, xodim o'zgartira olmaydi).
     - `Leviy` (faqat raqam).
     - `Qarzdorlik` (Rahbar belgilagan qoldiq qarz, xodim o'zgartira olmaydi).
     - `Qarz uchun` (Qarzdorlik summasidan qoplanadigan qism).
   - **Sim-karta**: Soni (donada, KPI hisobi uchun, pul balansiga ta'sir qilmaydi).
   - **Chiqimlar**:
     - `Kunlik` (faqat raqam).
     - `Terminal` (faqat raqam).
     - `Berildi` (Tasdiqlangan berilgan summalardan avtomatik olinadi).
     - `Skidka` (faqat raqam).
     - `Xarajat` (faqat raqam).
   - **Izoh**: Xodim sharhi.
   - **Kassa hisobi**: `Kirimlar - Chiqimlar = Umumiy summa` (avtomatik hisoblanadi).
   - **Tarix va Qayta Topshirish (Rollback)**:
     - Oldin topshirilgan hisobot hali `Kutilmoqda ⏳` bo'lsa va yangisi topshirilsa: eski oraliq hisob-kitoblar to'liq dastlabki holatiga qaytariladi (rollback) va yangi hisobot qabul qilinadi.

4. **Reyting Oynasi**:
   - Xodimlar Liderlar jadvali (Oylik va Umumiy reyting).
   - **Ball hisoblash**: Tasdiqlangan har **1 000 000 so'mga = 1 ball**, har **1 dona sim-kartaga = 1 ball**.

---

### B. Rahbar Paneli (10 ta Boshqaruv Bo'limi)

Rahbar uchun xodim amaliyot shakllari yashirilgan. U tizimga kirganida quyidagi 10 ta boshqaruv bo'limi orqali to'liq nazoratni amalga oshiradi:

1. **Kunlik hisobotlar**:
   - Barcha xodimlar topshirgan kunlik hisobotlar ro'yxati, to'liq tafsilotlar (kirim, chiqim, kassa qoldig'i, sim-karta), `Tasdiqlash ✅` va `Rad etish ❌` amallari.
2. **Savdo monitoringi va Diagrammalar**:
   - Umumiy topshirilayotgan summalar, sotilayotgan sim-kartalar va to'ldirilayotgan kartalarning vaqt bo'yicha o'sishi va pasayishi dinamikasi, 4 ta KPI kartochkasi, ko'p tarmoqli diagrammalar va kunlik tahlil jadvali.
3. **Berilgan summalar**:
   - Xodimlarning olingan pullar bo'yicha so'rovlarini ko'rib chiqish va tasdiqlash.
3. **Kassa taqqoslash**:
   - Xodim hisobotida ko'rsatilgan naqd summa bilan bugungi Kassir topshirgan summani yonma-yon solishtirish. Farq aniqlansa ogohlantirish berish.
4. **Xodimlar va Qarz boshqaruvi**:
   - **Yangi xodim qo'shish**: Faqat Telegram ID va F.I.SH orqali yangi xodimlarni ro'yxatdan o'tkazish (boshlang'ich qarz alohida mustaqil modulda yuritiladi).
   - **Xodimga qarz belgilash**: Alohida maxsus modul. Mavjud faol xodimlar ro'yxatidan xodim tanlanadi, berilayotgan qarz summasi va qarz sababi/izohi (kamomad, avans va h.k.) kiritilib biriktiriladi (mavjud qarzdorlikka qo'shiladi).
   - **Xodimlar jadvali**: Barcha xodimlar, ularning rollari, aniq mavjud qarzdorligi (0 so'm bo'lsa ham aniq aks etadi), parolni yangilash, bo'shatish/faollashtirish va qarzga yo'naltirish amallari. **Bosh Rahbar butunlay daxlsiz (`🛡️ Daxlsiz`)**: uni hech kim bo'shata olmaydi va tizimdan chiqara olmaydi.
5. **Kassir tayinlash**:
   - Xodimlar orasidan bugungi kunga Kassirni biriktirish, o'tmishdagi barcha tayinlashlar va ularning hisobot qabullari tarixini ko'rish.
6. **Sim-karta boshqaruvi va Qidiruv**:
   - **Sim-karta tarqatish (Diapazonli qo'shish)**:
     - **Operator turi**: `Uzmobile`, `Beeline`, `Ucell`, `Mobiuz`, `Perfectum` tanlanadi.
     - 18 xonali seriya raqami maydonlari (faqat raqam kiritiladi).
     - Format: `Boshlang'ich seriya raqami` (18 ta raqam) dan `Tugash seriya raqami` (18 ta raqam) gacha.
     - Xodimlar ro'yxatidan sim-karta biriktirilayotgan xodim tanlanadi.
     - Tizim kiritilgan diapazondagi barcha sim-kartalarni tanlangan operator turi bilan xodimga biriktiradi (masalan: `899981234567890001` dan `899981234567890050` gacha = 50 ta sim-karta).
   - **Seriya raqami bo'yicha tezkor qidiruv**:
     - Rahbar istalgan 18 xonali sim-karta seriyasini yozib qidirganda tizim darhol ma'lumot beradi:
       - **Sim-karta turi (Operator)**: `Uzmobile`, `Beeline`, `Ucell`, `Mobiuz` yoki `Perfectum`.
       - Qaysi xodimga berilgan (Xodimning F.I.Sh va Telegram ID).
       - Qachon berilgan (Sana va vaqt).
       - Kim tomonidan tarqatilgan (`Bosh Rahbar` yoki `Kassir`).
       - Holati (`Xodimda` / `Kunlik hisobotda sotilgan`).
   - **Xodimlar balansi**: Har bir xodim qo'lidagi mavjud faol sim-kartalar soni va sotilganlar balansi.
7. **Audit loglar**:
   - Tizimdagi har bir muhim operatsiya (kim, qachon, qaysi parametrni o'zgartirdi) bo'yicha o'zgartirib bo'lmas monitoring jurnali.
8. **Liderlar jadvali**:
   - Umumiy va oylik reyting monitoringi.
9. **Sozlamalar**:
   - Tizim parametrlari, API holati va xavfsizlik nazorati.

---

### C. Kassir Paneli

- Kassir — bugungi kunga biriktirilgan xodim. U xodimning 4 ta standart oynasiga ega.
- Unga qo'shimcha ravishda quyidagi 2 ta maxsus modul ochiladi:
  1. **"Kassadan pul qabul qilish" oynasi**:
     - Kassir boshqa xodimlarning hisobot tafsilotlarini ko'rmaydi.
     - Faqat xodimni tanlaydi va undan qabul qilingan naqd pulning **So'mda** va **AQSH Dollarida** miqdorini kiritadi.
     - Dollar kursi kassir oynasida alohida ko'rsatilmaydi yoki tahrirlanmaydi — tizimdagi amaldagi kurs bo'yicha jami ekvivalent summa avtomatik hisoblanadi.
     - Kiritilgan ma'lumot Rahbar panelidagi "Kassa taqqoslash" bo'limiga avtomatik yuboriladi va xodimning Telegramiga rasmiy elektron chek jo'natiladi.
  2. **"Sim-karta tarqatish" oynasi**:
     - Kassir ham xodimlarga sim-karta tarqata oladi.
     - Maydonlar: **Operator turi** (`Uzmobile`, `Beeline`, `Ucell`, `Mobiuz`, `Perfectum`), `Boshlang'ich seriya raqami` (18 xonali, faqat raqam), `Tugash seriya raqami` (18 xonali, faqat raqam), `Xodimni tanlash` (Dropdown).
     - Tarqatilgan sim-kartalar umumiy bazada va Rahbar qidiruv modulida "Kassir [F.I.Sh] tomonidan berildi" deb qayd etiladi.

---

### D. Telegram Bot Ish Oqimi
1. `/start` buyrug'i:
   - Yangi foydalanuvchi bosganda bot uning Telegram ID raqamini aniqlab jo'natadi.
   - Xodim ushbu IDni rahbarga beradi va rahbar uni tizimga qo'shadi.
2. 2FA OTP kodi:
   - Web ilovaga kirish paytida tizim avtomatik 6 xonali kod yaratib xodimning shaxsiy lichkasiga jo'natadi (Amal qilish muddati: 1 daqiqa).
3. Karta so'rovlarini guruhga yetkazish va statusni boshqarish.

---

## 5. 🗄️ Ma'lumotlar Bazasi Sxemasi (PostgreSQL)

```sql
-- Foydalanuvchilar (Xodimlar, Kassir, Rahbar)
users (
  id SERIAL PRIMARY KEY,
  telegram_id BIGINT UNIQUE NOT NULL,
  full_name VARCHAR(150) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'EMPLOYEE', -- 'EMPLOYEE', 'CASHIER', 'ADMIN'
  password_hash VARCHAR(255) NOT NULL,
  debt_amount NUMERIC(15, 2) NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Karta to'ldirish so'rovlari
card_topups (
  id SERIAL PRIMARY KEY,
  transaction_number INT NOT NULL, -- #123
  employee_id INT REFERENCES users(id),
  card_number VARCHAR(19) NOT NULL, -- '9860 1701 4567 1267'
  card_holder VARCHAR(150) NOT NULL,
  amount NUMERIC(15, 2) NOT NULL,
  surcharge_amount NUMERIC(15, 2) NOT NULL, -- amount * 1.03
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED'
  telegram_message_id BIGINT,
  approved_by_telegram_id BIGINT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Xodimga berilgan summalar
given_amounts (
  id SERIAL PRIMARY KEY,
  employee_id INT REFERENCES users(id),
  amount NUMERIC(15, 2) NOT NULL,
  comment TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED'
  approved_by INT REFERENCES users(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Kunlik hisobotlar
daily_reports (
  id SERIAL PRIMARY KEY,
  employee_id INT REFERENCES users(id),
  report_date DATE NOT NULL,
  paynet NUMERIC(15, 2) NOT NULL DEFAULT 0,
  card_amount NUMERIC(15, 2) NOT NULL DEFAULT 0, -- Tasdiqlangan karta so'rovlaridan avtomatik
  leviy NUMERIC(15, 2) NOT NULL DEFAULT 0,
  debt_snapshot NUMERIC(15, 2) NOT NULL DEFAULT 0, -- Rahbar belgilagan qarz
  debt_paid NUMERIC(15, 2) NOT NULL DEFAULT 0, -- Qarz uchun to'langan qism
  sim_cards_count INT NOT NULL DEFAULT 0,
  kunlik NUMERIC(15, 2) NOT NULL DEFAULT 0,
  terminal NUMERIC(15, 2) NOT NULL DEFAULT 0,
  given_amount NUMERIC(15, 2) NOT NULL DEFAULT 0, -- Tasdiqlangan berilgan summadan avtomatik
  skidka NUMERIC(15, 2) NOT NULL DEFAULT 0,
  xarajat NUMERIC(15, 2) NOT NULL DEFAULT 0,
  total_inflow NUMERIC(15, 2) NOT NULL DEFAULT 0,
  total_outflow NUMERIC(15, 2) NOT NULL DEFAULT 0,
  net_amount NUMERIC(15, 2) NOT NULL DEFAULT 0,
  comment TEXT,
  status VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'APPROVED', 'REJECTED'
  reviewed_by INT REFERENCES users(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Kassir qabul qilgan summalar
cashier_handovers (
  id SERIAL PRIMARY KEY,
  cashier_id INT REFERENCES users(id),
  employee_id INT REFERENCES users(id),
  handover_date DATE NOT NULL,
  amount NUMERIC(15, 2) NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Sim-kartalar hisobi va tarqatish
sim_cards (
  id SERIAL PRIMARY KEY,
  serial_number VARCHAR(18) UNIQUE NOT NULL, -- 18 xonali noyob seriya raqami (faqat raqam)
  operator_type VARCHAR(30) NOT NULL DEFAULT 'Uzmobile', -- 'Uzmobile', 'Beeline', 'Ucell', 'Mobiuz', 'Perfectum'
  employee_id INT REFERENCES users(id),       -- Biriktirilgan xodim
  distributed_by INT REFERENCES users(id),    -- Kim tarqatgan (Bosh Rahbar yoki Kassir)
  status VARCHAR(20) NOT NULL DEFAULT 'GIVEN', -- 'GIVEN' (Xodimda), 'SOLD' (Hisobotda sotilgan)
  distributed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  sold_at TIMESTAMP WITH TIME ZONE
);

-- Audit loglar
audit_logs (
  id SERIAL PRIMARY KEY,
  entity_type VARCHAR(50) NOT NULL,
  entity_id INT NOT NULL,
  action VARCHAR(50) NOT NULL,
  actor_id INT,
  actor_telegram_id BIGINT,
  details JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 6. 🔄 Foydalanuvchi Talablari Asosida Kiritilgan O'zgartirishlar Rejasi (Action Plan & Changelog)

Loyiha davomida foydalanuvchi tomonidan berilgan barcha fikr-mulohazalar (feedback) asosida quyidagi reja bandlari qat'iy standart sifatida belgilandi va dasturga to'liq kiritildi:

| № | Reja Bandi / Qoida | Oldingi Holat (Muammo) | Kiritilgan Aniq Yechim & Natija |
|---|---|---|---|
| **1** | **Rollarning Qat'iy Ajratilishi** | Rahbar tizimga kirganida xodimning shakllari (`Karta to'ldirish`, `Berilgan summa`) ko'rinib chalkashlik keltirgan. | Bosh Rahbar va Xodim interfeyslari to'liq mustaqil qilindi. Rahbarda faqat 8 ta boshqaruv paneli mavjud, u to'g'ridan-to'g'ri `Kunlik hisobotlar` bo'limiga kiradi. Xodim formasini ko'rmaydi. |
| **2** | **Interfeysni Tozalash (Clean UI)** | Formalarda o'quv/o'rgatuvchi qavsli yozuvlar (`(qo'lda kiritiladi)`, `(avtomatik)`, `(faqat harflar)`), dev sinov xabarlari bor edi. | Barcha qavsli tushuntirishlar, `card-desc` paragraflari va ortiqcha matnlar butunlay olib tashlandi. Interfeys professional va toza korporativ uslubga keltirildi. |
| **3** | **2FA va Dev Kodlarni Tozalash** | Kirish oynasida "localhost dev kod" va "2FA" kabi texnik/sinov matnlari ko'rinib turgan edi. | Barcha dev yozuvlari olib tashlandi. 6 xonali tasdiqlash kodi faqat rasmiy Telegram bot orqali xodimning shaxsiy lichkasiga xavfsiz jo'natiladi. |
| **4** | **Plandagi Misollarni Dasturdan Chiqarish** | Rejadagi `Aliyev Vali`, `Rustamov Bobur`, shartli karta raqamlari haqiqiy tizimga aralashmasligi kerak edi. | Barcha namunaviy ismlar va sun'iy ma'lumotlar olib tashlandi. Maydonlarda faqat toza formatlar (`0000 0000 0000 0000`, `0`) ishlatiladi. |
| **5** | **Kassir (`Cashier`) Vazifasi** | `cashier` so'zining noaniqligi va uning vazifasi. | `cashier` — bu o'zbek tilida `Kassir`. U bugungi kunga biriktirilgan xodim bo'lib, o'z amaliyotlaridan tashqari qo'shimcha "Kassadan pul qabul qilish" oynasi orqali boshqa xodimlardan naqd pulni qabul qiladi. |
| **6** | **To'liq O'zbek Tili Standarti** | Inglizcha atamalar (`ADMIN`, `CASHIER`, `EMPLOYEE`, `APPROVED`, `REJECTED`, `PENDING`) mavjud edi. | Barcha atamalar va bildirishnomalar sof o'zbek tiliga o'tkazildi: `Bosh Rahbar`, `Kassir`, `Xodim`, `Tasdiqlandi ✅`, `Rad etildi ❌`, `Kutilmoqda ⏳`. |
| **7** | **Hisobot O'chganda Qiymatlarni Qaytarish (Rollback)** | Qayta topshirilganda oraliq summalar hisobdan adashmasligi kerak edi. | Agar tasdiqlanmagan (`Kutilmoqda`) hisobot ustidan yangisi yuborilsa, eski hisobotdagi "Qarz uchun" kabi barcha hisoblar bekor bo'lib, qarz dastlabki holiga qaytadi va yangi hisobot toza qabul qilinadi. |
| **8** | **Haqiqiy Telegram Integratsiyasi** | Standart test tokenlari mavjud edi. | Berilgan rasmiy bot tokeni (`8932019841:...`), Rahbar ID (`8686341550`) va Guruh ID (`-5381348358`) to'liq ulandi va ishga tushirildi. |
| **9** | **Sim-karta Tarqatish va Seriya Qidiruvi** | Sim-kartalar soni faqat hisobotda ko'rsatilgan, seriyalari va kimga berilganligi tizimda yuritilmagan. | Kassir va Rahbar uchun 18 xonali raqamli seriyalarni diapazon ("...dan ...gacha") ko'rinishida xodimga tarqatish moduli qo'shildi. Rahbar uchun seriya raqami yozilganda xodim, sana va tarqatuvchini bir zumda topib beruvchi qidiruv paneli joriy qilindi. |
| **10** | **Toshkent Vaqti (UTC+5) Standarti** | Ma'lumotlar bazasidagi UTC vaqtlar sababli operatsiyalar vaqti 5 soat orqada ko'rinayotgan edi. | Barcha sanalar va vaqtlar Toshkent vaqti (+5 soat) bo'yicha hisoblanadigan qilib `DD.MM.YYYY HH:mm` formatiga o'tkazildi. |
| **11** | **Xodim Qo'shish va Qarz Belgilashni Ajratish** | Xodim qo'shish formasida qarz kiritish aralashib ketgan va qarz sababi kiritilmas edi. | Yangi xodim qo'shish (faqat Telegram ID, F.I.SH) va Qarz belgilash (xodim tanlash, qarz summasi va sababi) 2 ta mustaqil modulga ajratildi. Qarzdorlik 0 so'm holatida ham to'g'ri ko'rsatilishi ta'minlandi. |
| **12** | **Kalendar Bo'yicha Saralash, Hisobot Tafsilotlari & Dollar Kursi** | Hisobotlarni sana bo'yicha saralash, ularning ichki qismlarini to'liq ko'rish hamda dollar kursini belgilash imkoniyati yo'q edi. | 1) Hisobotlar uchun kalendar tanlash, "Bugun" va "Barcha sanalar" filtrlari kiritildi. 2) Hisobotlarning Kirim (Paynet, Karta, Leviy), Chiqim (Kunlik, Terminal, Berildi, Xarajat) tarkibi va `👁️ Batafsil` to'liq 2 ustunli ko'rish modali yaratildi. 3) Tepa o'ng burchakka doimiy Dollar kursi nishoni (`1$ = 12 000 so'm`) o'rnatildi: Rahbar uni belgilashi/tahrirlashi, barcha xodimlar esa ko'rib turishi ta'minlandi. |
| **13** | **Kassa Qabul Qilishda So'm va Dollar hamda Telegram Chek** | Kassir faqat yagona umumiy summa kiritar, so'm va dollar ajratilmas, Rahbarda ko'rinmas va xodimga kassa topshirish cheki bormas edi. | 1) Kassir kassa qabul qilishda So'm (`amount_uzs`) va Dollar (`amount_usd`) maydonlarini mustaqil kiritadi, real-vaqtda ekvivalent hisoblanadi. 2) Rahbarning "Kassa taqqoslash" panelida va topshirilgan summalar tarixida `So'mda` va `Dollarda` aniq ko'rsatiladi. 3) Kassir qabul qilishi bilan xodimning shaxsiy Telegramiga rasmiy elektron chek (summalar, kurs, kassir va vaqt) bot orqali avtomatik jo'natiladi. |
| **14** | **Sim-karta Telegram Xabari va Rahbar/Kassir Rollari Chegarasi** | Sim-karta berilganda xodimga xabar bormas, Rahbar kassir amaliyotlarini bajarish uchun qulay rejimga ega emas edi. | 1) Sim-karta xodimga biriktirilganda xodimning Telegramiga nechta sim-karta berilgani, qaysi seriyadan qaysi seriyagacha (18 xonali diapazon), operator turi va tarqatuvchi ko'rsatilgan xabar boradi. 2) Rahbar uchun "💼 Kassir rejimi" qo'shildi: Rahbar kassir amallarini qila oladi, lekin aslo xodim bo'la olmaydi (xodim shakllari unga yashiriladi). 3) Rahbar xodimlar ro'yxatidan istalgan xodimni `💼 Kassir qilish` yoki qaytadan `👤 Xodim qilish` (bo'shatish) imkoniyatiga ega bo'ldi. |
| **15** | **Qarzdorlik va Qarz To'lovining Kirimga Ta'siri** | Xodimning umumiy qarzdorligi kirimga qo'shilib hisoblanayotgan edi (masalan, Paynet 1 000 000 + Qarz 50 000 = 1 050 000 bo'lib qolgan edi). | 1) Qarzdorlik kirimga qo'shilishi butunlay to'xtatildi. 2) Faqat "Qarz uchun to'lov"ga summa kiritilsa kirimga qo'shiladi (`total_inflow = paynet + card + leviy + debt_paid`). 3) Qarz uchun to'lov kiritilganda "Qarzdorlik" maydonida real-vaqtda qarz kamayib (`qarzdorlik - qarz uchun to'lov`) borishi ta'minlandi va hisobot tasdiqlanganda qarzdan chegiriladi. |
| **16** | **Takroriy Karta To'lovida "Bugun bu kartaga to'lov qilindi" Ogohlantirishi** | Karta so'rovi tasdiqlanib yoki bir kunda 2 va undan ortiq so'rov yuborilganda, UTC va Toshkent (+5) vaqt nomutanosibligi sababli Telegram guruhida `⚠️ Bu kartaga bugun to'lov qilindi!` xabari chiqmayotgan edi. | 1) Karta takroriyligini aniqlash `DATE(created_at, '+5 hours') = DATE('now', '+5 hours')` va probellarsiz karta raqami bo'yicha to'g'rilandi. 2) 2-va undan keyingi so'rovlarda Telegram guruhiga `⚠️ DIQQAT: Bu kartaga bugun to'lov qilindi! 🔄` ogohlantirish xabari to'liq chiqishi ta'minlandi. 3) Web CRM da xodimga ogohlantirish xabari aks ettirildi. |
| **17** | **Sim-karta Tarqatish Tarixini "dan - gacha" Qilib 1 ta Qatorda Ko'rsatish** | 100 ta sim-karta tarqatilganda "Oxirgi tarqatilganlar" jadvalida 100 ta alohida qator chiqib jadvalni to'ldirib yuborayotgan edi. | Har bir tarqatish partiyasi `sim_distributions` jadvali orqali 1 ta ixcham qatorda `boshlang'ich seriya dan tugash seriya gacha (X dona)` ko'rinishida chiqarilishi ta'minlandi. |
| **18** | **Hisobot Tasdiqlanganda Sim-karta Balansida "Sotilgan" Hisoblanishi** | Xodimning kunlik hisoboti tasdiqlanganda, undagi sotilgan sim-kartalar soni "Xodimlar sim-karta balansi" jadvalidagi "Sotilgan" ustuniga hisoblanmayotgan va zaxiradan chegirilmayotgan edi. | Hisobot tasdiqlanganda (`APPROVED`) xodim sotgan sim-kartalar soni avtomatik ravishda `Sotilgan` ustuniga qo'shilishi, `Qo'lidagi (Xodimda)` zaxirasidan chegirilishi hamda bazadagi `sim_cards` holati `SOLD` ga o'tkazilishi ta'minlandi. |
| **19** | **Kassa Qabul Qilish Tarixi (Rahbar/Kassir O'zaro Ko'rinishi) va Xodimning Ro'yxatdan O'chishi** | Kassir qabul qilgan summa Rahbarda, Rahbar qabul qilgani Kassirda ko'rinmas, hamda summa topshirgan xodim tanlash ro'yxatida qolib ketayotgan edi. | 1) Kassir ham, Rahbar ham bugungi qabul qilingan barcha summalarni bir-birining tarixida to'liq ko'ra oladigan qilindi (`Qabul qildi` ustunida aniq ko'rsatiladi). 2) Bugun kassa topshirgan xodim o'sha kun uchun tanlash ro'yxatidan (`Xodimni tanlang`) avtomatik ravishda o'chib borishi ta'minlandi. |
| **20** | **Tizimga Kirishda 1 Minutda 1 Marta Urinish va Qaytadan Urinish Cooldown Qoidasi** | Kirish oynasida "Qaytadan urinish" bosilganda 60 soniya kutmasdan darhol qayta urinish mumkin edi. | 1) OTP oynasidagi "Qaytadan urinish" tugmasi 60 soniyalik hisoblagich davomida faolsizlantirildi (`⏳ Qaytadan urinish (42s)`), vaqt tugagachgina faollashadi. 2) Backendda (`/api/auth/login`) 60 soniyalik rate limiting o'rnatildi, muddat tugamasdan urinsa HTTP 429 xatosi va qolgan soniyalar ko'rsatiladi. |
| **21** | **Mobil, Planshet va Kompyuter Uchun To'liq Responsiv Interfeys** | Kichik ekranli qurilmalarda (telefon va planshetlar) navigatsiya va formalar sig'may qolishi yoki noqulay bo'lishi mumkin edi. | 1) Mobil (< 768px, < 480px), planshet (769px-1024px) va kompyuter (> 1024px) uchun to'liq moslashuvchan CSS tizimi joriy etildi. 2) Tablar barmoq bilan silliq suriladigan (swipe) zamonaviy mobil lentaga o'tkazildi. 3) Navbar 2 pog'onali ixcham holatga keltirildi. 4) Formalar vertikal 1 ustunga o'tib, tugmalar va maydonlar sensorli ekranga (min 44px) moslandi. 5) Karta va OTP raqamlari har qanday ekranda chiroyli sig'ishi uchun dinamik `clamp()` bilan ta'minlandi. |
| **22** | **Yagona Kassir Standarti va Oldingi Kassirning Avtomatik Xodimga Aylanishi** | Yangi kassir tayinlanganda oldingi kassirning holati noaniq qolishi yoki bir vaqtda bir nechta kassir paydo bo'lish xavfi bor edi. | 1) Tizimda Rahbar tayinlagan kassir har doim qat'iy **faqat 1 ta** bo'lishi ta'minlandi. 2) Rahbar boshqa xodimni kassir qilsa, oldingi barcha kassirlar avtomatik ravishda oddiy xodim (`role = 'EMPLOYEE'`) holatiga o'tkaziladi. 3) Tarix va audit jurnaliga oldingi kassir `DISMISSED` va yangi kassir `APPOINTED` bo'lib to'liq yoziladi. |
| **23** | **Tepadagi Menyularni Chap Tomondagi Responsiv Ochiluvchi Menyuga (Sidebar Drawer) O'tkazish** | Tepadagi gorizontal menyu ko'p joy olib, mobil va planshetlarda ekranni to'sib turgan edi. | 1) Navbarga chap tomonda `[ ☰ Menyu ]` tugmasi o'rnatildi. 2) Bosilganda chapdan silliq ochiluvchi (drawer) responsiv yon menyu yaratildi. 3) Foydalanuvchi roli (Rahbar / Kassir / Xodim) bo'yicha barcha modullar chiroyli vertikal menyu ko'rinishida chiqarildi. |
| **24** | **[☰ Menyu] Tugmasining Faqat Kichik Ekranlarda (Telefon va Planshetlarda) Chiqish Qoidasi** | Katta kompyuter ekranlarida ham `[ ☰ Menyu ]` tugmasi va tepadagi gorizontal tablar bir vaqtda chiqib turgan edi. | 1) Katta ekranlarda (> 1024px) `[ ☰ Menyu ]` tugmasi yashirildi (`display: none`), gorizontal tablar o'z tabiiy holida ko'rinadigan qilindi. 2) Faqat ekranga xalaqit beradigan kichik qurilmalarda (telefonlar va kichik planshetlar, <= 1024px) gorizontal menyu yashirilib, o'rniga `[ ☰ Menyu ]` tugmasi chiqishi va chap yon panel orqali boshqarilishi ta'minlandi. |
| **25** | **Barcha Interfeys Elementlarining O'ziga Xos Responsiv Standarti** | Faqat umumiy gridlar mavjud bo'lib, jadvallar surilganda qaysi xodimligi yo'qolib qolar, uzun 16-18 xonali raqamlar va kassa bannerlari kichik telefonlarda noqulay bo'lar edi. | 1) Jadvallarda birinchi ustun (`sticky left: 0`) mustahkamlandi va maxsus teginish scrollbari o'rnatildi. 2) 16 va 18 xonali kiritish maydonlari (karta, OTP, sim-seriya) `clamp()` bilan moslandi. 3) Kassa hisob-kitob va ekvivalent bannerlari 2 pog'onali mobil kartochka holatiga keltirildi. 4) Reyting filtrlari 50/50 segmentli qulay tugmalarga aylantirildi. 5) Sensorli ekranlar uchun bosish animatsiyalari va iOS zoom xavfsizligi to'liq ta'minlandi. |
| **26** | **Kassir, Qarz va Chiqishni Menyu Ichiga O'tkazish & Kiritish Maydonlari Orasini Qisqartirish** | Mobil ekranda navbar 4 qatorga bo'linib juda ko'p joy egallab qolgan, formadagi kiritish maydonlari orasi esa katta bo'lib ekranga sig'mayotgan edi. | 1) Mobilda `[ 💼 Kassir ]`, `Qarz: ...` va `Chiqish 🚪` tugmalari navbardan yashirilib, to'liq `[ ☰ Menyu ]` (drawer) ichiga o'tkazildi. Mobil navbar bitta toza va ingichka qatorga aylandi. 2) Formalardagi barcha kiritish maydonlari orasidagi bo'shliqlar 50% dan ortiqqa ixchamlashtirilib (`gap: 0.42rem`, `margin-bottom: 0 !important`), butun forma bir qarashda ekranga sig'adigan holatga keltirildi. |
| **27** | **Bosh Rahbar Takrorlanishini Bartaraf Etish & Rahbar Amallarini Menyuga Yashirish** | Navbarda "Bosh Rahbar" so'zi 2 marta ("Bosh Rahbar 👑 Bosh Rahbar") chiqayotgan, hamda "Kassir rejimi" tugmasi kichik ekranlarda ham navbarda qolib ekranni to'sib turgan edi. | 1) Admin ismi "Bosh Rahbar" bo'lganda ortiqcha takrorlanish to'xtatilib, faqat yagona "👑 Bosh Rahbar" nishoni qoldirildi. 2) Responsive ekranlarda (`<= 1024px`) "Kassir rejimi", "Bosh Rahbar", "Qarz" va "Chiqish" tugmalari navbardan to'liq yashirilib, faqat `[ ☰ Menyu ]` (drawer) ichida ko'rinishi va boshqarilishi ta'minlandi. 3) Natijada mobil navbar bitta qatorda faqat logo va dollar kursi bilan toza holatga keltirildi. |
| **28** | **Bosh Rahbarning Daxlsizligi (Hech Qachon Bo'shatilmaslik Qoidasi)** | "Xodimlar boshqaruvi" jadvalida Bosh Rahbar qatorida ham "Bo'shatish" tugmasi chiqib turgan edi. | 1) Bosh Rahbar (`role = 'ADMIN'`) qatoridan "Bo'shatish" tugmasi butunlay olib tashlandi va o'rniga `🛡️ Daxlsiz` nishoni o'rnatildi. 2) Frontendda xavfsizlik tekshiruvi o'rnatilib, adminni bo'shatishga urinishlar darhol bloklanadi. 3) Backendda (`/api/admin/users/{user_id}/toggle-active`) Bosh Rahbarni faolsizlantirish qat'iy taqiqlanib, HTTP 403 Forbidden himoyasi ("Bosh Rahbar daxlsiz! Uni tizimdan hech kim bo'shata olmaydi va chiqara olmaydi!") o'rnatildi. |
| **29** | **Reaktiv va Hisob-kitob Bloklarini Ixchamlashtirish (Zero Wasted Space)** | Kassa ekvivalenti, Sim-karta sotuvi, Kunlik oraliq hisob va Karta reaktiv (+3%) bloklari haddan tashqari baland bo'lib, o'ng tomonida katta bo'sh joylar bilan ekranni egallab turgan edi. | 1) Kassa ekvivalent bloki (`equivalent-summary-box`) chapda formula, o'ngda yakuniy summa bilan 44px ixcham balandlikka keltirildi. 2) Kunlik hisobotdagi Sim-karta bloki (`sim-karta-compact-box`) gorizontal 2 tomonlama (chapda sarlavha, o'ngda raqam kiritish) qatorga aylantirildi. 3) Kunlik hisobotdagi umumiy hisob banneri (`calc-summary-banner`) 2 qatorli balansli ko'rinishga keltirilib bo'shliqlar yo'qotildi. 4) Karta to'ldirishdagi reaktiv blok (`reactive-box`) chapda ustama/so'zlar, o'ngda emoji bilan bir qatorli ixcham ko'rinishga o'tkazildi. |
| **30** | **3% Ustamani 1 000 So'mda Yaxlitlash, Min 30 000 So'm & Emojilar Rekordi (100M)** | 3% ustama oddiy yaxlitlanar (50 000 da 51 500 chiqardi), 1mln/5mln rekord deb atalar va 30 000 dan kam summa ham kiritilishi mumkin edi. | 1) 3% ustama har doim yuqoriga 1 000 so'mga yaxlitlanadigan qilindi (`Math.ceil((amount * 1.03) / 1000) * 1000`, masalan: 50 000 -> 52 000 so'm). 2) Karta to'ldirish uchun eng kam summa qat'iy 30 000 so'm qilib belgilandi (Frontend va Backend 400). 3) Reaktiv emojilar va sarlavhalar summalarga to'liq moslashtirildi: `Rekord darajadagi summa! 🤑 💥` faqat summa 100 000 000 so'mga (100 million) yetganda chiqadi. |
| **31** | **Tungi (Dark mode) va Kunduzgi (Day mode) Rejim Qo'shish & Responsiv Menyu Moslashuvi** | Tizim faqat qoramtir (Dark) rejimda ishlagan, kunduzgi yorug'likda foydalanish uchun yorqin Day mode mavjud emas edi. | 1) To'liq yuqori sifatli va kontrastli Kunduzgi (Day) rejim yaratildi (toza oq kartalar, `#0f172a` qora-to'q matnlar, silliq soyalar va `0.25s` silliq o'tishlar). 2) Katta ekranlarda (> 1024px) sozlash tugmasi yuqori o'ng burchakka (`#nav-user-area`) joylashtirildi. 3) Responsiv kichik ekranlarda (<= 1024px) ushbu tugma navbardan yashirilib, to'liq `[ ☰ Menyu ]` (drawer) ichiga o'tkazildi. 4) Foydalanuvchi tanlovi `localStorage` orqali saqlanib, qayta kirganda eslab qolinadi. |
| **32** | **Faqatgina Rahbar Uchun Savdo Monitoringi va Diagrammalar Moduli** | Rahbarda umumiy topshirilayotgan summalar, sotilayotgan sim-kartalar va to'ldirilayotgan kartalarning vaqt bo'yicha o'sishi yoki pasayishini ko'rsatuvchi interaktiv vizual diagramma yo'q edi. | 1) Faqat Rahbar uchun `/api/admin/analytics/monitoring` backend tahlil endpointi yaratildi (o'sish/pasayish foizlari va kunlik ketma-ketlik bilan). 2) 4 ta asosiy KPI kartochkasi (jami summa, sim-karta, karta to'ldirish, sof kassa va ularning % trend nishonlari) qo'yildi. 3) Ko'p tarmoqli asosiy dinamika diagrammasi, kunbay o'sish/pasayish bar charti hamda operatorlar taqsimoti doiraviy diagrammasi integratsiya qilindi. 4) Oxirgi 7 kun, 30 kun, joriy oy va barcha davr filtrlari hamda to'liq kunlik tahlil jadvali bilan ta'minlandi. |
| **33** | **Tailwind CSS CRM Stili hamda Tungi va Kun Rejimi Mukammalligi (Tailwind UI Slate & Indigo)** | CRM sayti oddiy CSS ko'rinishida bo'lib, zamonaviy Tailwind UI CRM standartlariga to'liq javob bermas va kunduzgi rejimda ba'zi nishonlar hamda jadvallarning kontrasti yaxshilashni talab qilar edi. | 1) Tailwind CSS v3 (CDN) integratsiya qilindi va `darkMode: 'class'` bilan ulandi. 2) Tungi rejim Tailwind Slate 950/900/800 va Indigo ranglariga, Kunduzgi rejim esa Slate 50/White/Slate 200 hamda yuqori kontrastli korporativ ranglariga o'tkazildi. 3) Barcha nishonlar (`badge`) zamonaviy `rounded-full` pill chip ko'rinishiga, tablar segmented control pill uslubiga, kartalar `rounded-2xl` formatiga keltirildi. 4) Jadvallar va sticky birinchi ustunlar har ikki rejimda mukammal va bir-biriga xalaqit bermaydigan qilib ishlandi. 5) Savdo monitoringi grafikalari (Chart.js) ham Tungi va Kunduzgi mavzuga mos ravishda reaktiv qayta ranglanishi ta'minlandi. |
| **34** | **To'liq Haqiqiy Tailwind UI CRM Dizayniga O'tkazish & Kesh Muammosini Hal Qilish** | Foydalanuvchida eski qalin neon tablar, inline `style="..."` dagi qalin ramkalar ko'rinib qolgan va brauzer 304 kesh tufayli yangi stillarni ko'rsatmayotgan edi. | 1) `applyTheme` funksiyasida `documentElement` ga `dark` klassi qo'shilishi to'liq to'g'rilandi. 2) HTML dagi barcha inline stillar tozalab tashlandi. 3) Tablar to'liq Tailwind UI segmented control nav formatiga o'tkazildi (faol tab `bg-indigo-600 text-white font-semibold shadow-sm`, nofaollar esa `text-slate-400 hover:text-white`). 4) Kesh qat'iy yangilanishi uchun `style.css?v=300` va `app.js?v=300` ga oshirildi. 5) Kalendar filtri va boshqaruv panellari Tailwind UI minimalist ko'rinishiga keltirildi. |
| **35** | **100% Haqiqiy Tailwind CSS Utility Klasslari va Toza Tailwind UI Dizayni** | Saytda hali ham eski vanilla CSS qoidalari (`radial-gradient`, `border-left: 4px solid`, eski `.brand-icon`, JS inline `style.background`) saqlanib qolgan va sof Tailwind standartiga mos emas edi. | 1) HTML elementlariga (Navbar, Brand, Tablar, KPI kartochkalari, Diagrammalar, Jadvallar) to'g'ridan-to'g'ri haqiqiy Tailwind CSS utility klasslari (`bg-slate-900`, `border-slate-800`, `rounded-2xl`, `grid`, `flex items-center` va h.k.) o'rnatildi. 2) `style.css`dagi eskirgan radial neon gradientlar va 4px qalin yon ramkalar butunlay olib tashlanib, haqiqiy Tailwind UI Flat Stats Card uslubiga o'tkazildi. 3) JS dagi inline rang o'rnatishlar tozalandi va kesh versiyasi `?v=500` ga yangilandi. |
| **36** | **https://ant.design/ (Ant Design 5.x) Korporativ Dizayn Tizimiga To'laqonli O'tkazish** | Foydalanuvchi butun tizimni jahon miqyosidagi rasmiy Ant Design korporativ uslubiga to'laqonli o'tkazishni talab qildi. | 1) Ant Design 5.x dizayn tokenlari tizimi to'liq joriy etildi: Ant Blue `#1677ff` asosiy rang, layout foni `#f5f5f5` (kun) va `#141414` (tun), kartalar `#ffffff` va `#1f1f1f`, chegaralar `#f0f0f0` va `#303030`. 2) Ant Design Line Tabs (`ant-tabs-nav` 2px ko'k tagchiziqli indikator bilan) o'rnatildi. 3) Barcha tugmalar Ant Design `ant-btn` standartiga (`#1677ff`, 32px balandlik, 6px radius, `0 2px 0 rgba(5,145,255,0.1)`) keltirildi. 4) Nishonlar Ant Design `ant-tag` formatiga (4px radius, 12px shrift, 20px balandlik), maydonlar `ant-input` ga, jadvallar `ant-table` ga to'laqonli o'tkazildi. 5) Kesh versiyasi `?v=600` ga oshirildi. |
| **37** | **Zamonaviy Executive SaaS CRM Dizayn Tizimi (Linear & Stripe Dashboard Benchmark)** | Kunduzgi rejimda navbar va kartalarda qora fondagi ziddiyatli bloklar qolgan, tablar qo'pol kataklar ko'rinishida, diagramma X o'qidagi sanalar esa 45 gradusda zich shtrix-kodga aylanib ketgan edi. | 1) Internetdagi eng yetakchi SaaS mahsulotlari (Linear, Stripe, Supabase, shadcn/ui) tahlil qilinib, "Calm, High-Density Executive CRM" dizayn tizimi tanlandi va tatbiq etildi. 2) HTML dagi hardcoded `bg-[#1f1f1f]` tozalab tashlandi; kunduzgi rejim toza oq (`#ffffff`) va Slate 50 (`#f8fafc`), tungi rejim esa chuqur Midnight Slate (`#090d16` va `#0f172a`) bilan 100% uyg'unlashdi. 3) Tablar zamonaviy Linear segmented control uslubiga o'tkazildi. 4) Chart.js diagrammasida `maxTicksLimit: 7`, `maxRotation: 0` va `autoSkip: true` o'rnatilib, sana barcode muammosi to'liq hal qilindi. 5) 4 ta KPI kartochkasi 3px gradient indikator, tabular-nums va pastel pill nishonlar bilan boyitildi. 6) Kesh versiyasi `?v=700` ga yangilandi. |
| **38** | **Kunduzgi (Day Mode) Rejimni Mukammallashtirish & Jadvaldagi Ustunlar To'silishini Bartaraf Etish** | Kunduzgi rejimda jadvallarda `Sana` ustuni `Xodim` va `Kirim` ustunlarini yopib qo'ygan, `20 dona` sim va `Batafsil` tugmasi oq fonda deyarli ko'rinmaydigan rangda, tablar esa 2 qatorga chalkash bo'lib tushib qolgan edi. | 1) Jadvallardan `position: sticky; left: 0` butunlay olib tashlandi, barcha 9 ta ustun bir tekisda gorizontal joylashib, hech qanday ustun bir-birini to'smaydigan qilindi. 2) Oq fonda o'qilishi qiyin bo'lgan inline qoramtir ranglar (`#c7d2fe`, `#34d399`, `#f87171`) o'rniga maxsus semantik CSS klasslari (`val-inflow`, `val-outflow`, `val-net`, `val-sub`, `val-debt-paid`, `badge-sim`, `btn-details`, `rep-modal-*`) joriy etildi va kunduzgi rejimda to'liq yuqori kontrast (AAA daraja) ta'minlandi. 3) Tablar `nowrap` va yashirin silliq gorizontal siljish bilan bitta chiroyli lentaga aylantirildi. 4) Navbardagi barcha nishonlar (dollar kursi, kassir rejimi, bosh rahbar, mavzu tugmasi, chiqish) 32px bir xil balandlik va yagona uyg'un uslubga keltirildi. 5) Brauzer yangilanishi uchun kesh versiyasi `?v=802` ga oshirildi. |
| **39** | **Tungi va Kunduzgi Rejimda Maydonlar va Matnlar Rangini Invert Qilish** | Foydalanuvchi talabi: Tungi rejimda kiritish maydonlari oq, kiritilgan matnlar qora rangda; Kunduzgi rejimda esa kiritish maydonlari qora, kiritilgan matnlar oq rangda bo'lishi belgilandi. | 1) **Tungi rejim**: Barcha kiritish maydonlari (`form-input`, `select`, `textarea`, `date-picker-wrap`, `otp-code-input`, `card-number-input`) oq fonda (`background: #ffffff !important`), ma'lumotlar esa to'q qora rangda (`color: #0f172a !important`) qilindi. Kalendar piktogrammasi qora rangga o'tkazildi. 2) **Kunduzgi rejim**: Barcha kiritish maydonlari qora fonda (`background: #0f172a !important`), ma'lumotlar esa toza oq rangda (`color: #ffffff !important`) qilindi. Kalendar piktogrammasi oq rangga o'tkazildi (`filter: invert(1)`). 3) Readonly, select option va placeholder elementlari har ikki rejim uchun to'liq moslashtirildi. 4) Kesh versiyasi `?v=803` ga yangilandi. |
| **40** | **So'rov Yuborish Tugmalarida Reaktiv Hover Pop-out & Glow Effektini Joriy Etish** | Barcha forma yuborish va harakat tugmalari hover bo'lganda tekis va noaniq turgan, alohida ajralib chiqish animatsiyasi yo'q edi. | 1) Barcha so'rov yuborish tugmalari (`form button[type="submit"]`, `.btn-primary`, `.btn-success`, `.btn-danger`, `searchSimCard`, `handleAppointCashierSubmit`) uchun 40px korporativ balandlik va `cubic-bezier(0.34, 1.56, 0.64, 1)` silliq animatsiyasi o'rnatildi. 2) Sichqoncha ustiga borganda (hover) tugma `-3px` ko'tarilib (`translateY(-3px) scale(1.015)`), o'z rangiga mos chuqur nurli soya (`box-shadow: 0 12px 24px -4px ...`) bilan sirt ustida yaqqol ajralib chiqadigan bo'ldi. 3) Bosilganda tabiiy bosilish effekti (`translateY(0.5px) scale(0.985)`) berildi. 4) Kesh versiyasi `?v=804` ga yangilandi. |
| **41** | **Tepadagi Barcha Modullar (Tablar) Uchun Reaktiv Hover Pop-out & Glow Effektini Joriy Etish** | Tepadagi modullar (tablar) hover bo'lganda sirt bilan bir xil bo'lib, ajralib chiqmayotgan edi. | 1) Tepadagi barcha modul tugmalari (`.tab-btn`) uchun `cubic-bezier(0.34, 1.56, 0.64, 1)` elastik animatsiyasi o'rnatildi. 2) Tungi rejimda hover bo'lganda tugma `2.5px` yuqoriga ko'tarilib (`translateY(-2.5px) scale(1.025)`), Indigo neon chegarasi (`rgba(99, 102, 241, 0.6)`), shaffof yorug' fon (`rgba(99, 102, 241, 0.22)`), oppoq matn va atrofga taraluvchi ambient soya (`box-shadow: 0 8px 18px -2px ...`) bilan ajralib chiqadi. 3) Kunduzgi rejimda esa hover bo'lganda oppoq qavariq karta bo'lib ko'tariladi va to'q binafsha matn (`#4338ca`) bilan aniq ajraladi. 4) Kesh versiyasi `?v=805` ga yangilandi. |
| **42** | **Modullar (Tablar) Konteynerdan Chiqib Ketishi va Qirqilishini Butunlay Bartaraf Etish** | Tepadagi 10 ta modul nomlari haddan tashqari uzun bo'lgani va yashirin `overflow-x: auto; scrollbar-width: none; flex-wrap: nowrap;` tufayli oxirgi 4 ta modul (Kassir, Sim-karta, Reyting, Audit) konteynerning o'ng chetiga kirib ketib, ko'rinmay qolgan edi. | 1) Modullar nomlari ixcham, standart korporativ nomlarga keltirildi (`Hisobotlar`, `Savdo monitoringi`, `Berilgan summalar`, `Karta so'rovlari`, `Kassa taqqoslash`, `Xodimlar & Qarz`, `Kassir & Tarix`, `Sim-kartalar`, `Reyting & KPI`, `Audit loglar`). 2) Asosiy konteyner kengligi `max-w-[1440px]` ga yetkazildi va tugmalar paddingi (`0.42rem 0.72rem`) optimallashtirildi. Shu tufayli barcha 10 ta modul bitta chiziqda to'liq sig'adigan bo'ldi. 3) Kichikroq ekranlarda modullar qirqilib yoki konteynerga kirib yo'qolib ketmasligi uchun `flex-wrap: wrap !important` berildi — barcha 10 ta modul doimo 100% ko'rinib, to'liq bosiladigan holatga keltirildi. 4) Kesh versiyasi `?v=806` ga yangilandi. |
| **43** | **Alohida Chiroyli Kalendar Oynasi (Date Range Modal) va Hisobotlarni ...dan ...gacha Sana Bo'yicha Saralash** | Brauzerning xunuk va ruscha standart `<input type="date">` oynasi ochilar, faqat 1 ta kunni tanlash mumkin bo'lib, sana oralig'i (...dan ...gacha) bo'yicha hisobotlarni saralash imkoni yo'q edi. | 1) Backendda `/api/reports/all` endpointiga `start_date` va `end_date` parametrlari qo'shildi (`BETWEEN ? AND ?` orqali oraliqni saralaydi). 2) Frontendda brauzerning standart popup o'rniga zamonaviy alohida ochiluvchi **Date Range Picker Modali** yaratildi. 3) 6 ta tezkor davr tugmasi (`Bugun`, `Kecha`, `7 kun`, `30 kun`, `Shu oy`, `Barchasi`) va O'zbek tilidagi chiroyli interaktiv kalendar vidjeti (Dsh-Ysh, oylarni almashtirish, oraliqni ko'k gradientda belgilash) o'rnatildi. 4) Asosiy sahifada tanlangan davr (`📅 01.10.2026 — 25.10.2026 ▾`) interaktiv tugma sifatida aks etadi. 5) Kesh versiyalari `style.css?v=807` va `app.js?v=301` ga oshirildi. |
| **44** | **Zero-Trust Xavfsizlik: OTP Maxfiyligi & Vebdagi Ko'rsatma (Faqat Telegram Akkaunt Egasi Uchun)** | Tizimga kirishda begona shaxslar kirib ketishining oldini olish, OTP kodlarini hech qachon vebda ko'rsatmaslik va Telegram botdan xabar kelmasa vebda aniq yo'riqnoma berish talab qilindi. | 1) Kod hech qachon vebda ko'rsatilmaydi yoki API orqali oshkor qilinmaydi (`dev_otp` va har qanday backdoorlar butunlay yo'q qilindi). 2) Tizimga tasdiqlash kodi orqali kirishdan yagona maqsad — faqat shaxsiy Telegram akkauntining haqiqiy egasi kira olishini 100% kafolatlash. 3) Agar botdan xabar kelmasa yoki botga start berilmagan bo'lsa, web modalining o'zida to'liq va tushunarli ko'rsatma (botga kirish, /start bosish, blokdan chiqarish) hamda botga to'g'ridan-to'g'ri o'tuvchi havola (`@xodim_reyting_bot ↗`) taqdim etildi. 4) Kesh versiyasi `app.js?v=305` ga yangilandi. |
| **45** | **Tarix Bo'limlarida Har 5 Tadan Keyin To'lib Qolganda Avtomatik Scroll & Yopishqoq Sarlavha** | Foydalanuvchi ma'lumotlar qo'shgani sari tarix jadvali pastga qarab haddan tashqari cho'zilib ketar, butun sahifani egallab noqulaylik tug'dirar edi. | 1) Barcha tarixiy jadvallar konteyneriga (`table-scroll-5`) 5 ta qatordan oshganda avtomatik vertikal scroll (`max-height: 290px`, mobilda `255px`, `overflow-y: auto`) standarti o'rnatildi. 2) 5 tagacha bo'lgan yozuvlar tabiiy balandlikda ko'rinadi, 5 tadan oshganda konteyner to'lib, qolgan yozuvlar ichki silliq skroll orqali ko'riladi. 3) Jadval sarlavhalari (`thead th`) yopishqoq (`position: sticky; top: 0`) qilindi, natijada pastga aylantirilganda ham ustun nomlari ko'rinib turadi. 4) Tungi va Kunduzgi rejimlar uchun zamonaviy 6px yumaloq skrollbar joriy etildi. 5) Kesh versiyalari `style.css?v=808` va `app.js?v=306` ga yangilandi. |
| **46** | **Izohlar Maydoniga Ham Raqam, Ham Harflar (Alfanumerik Matn) Kiritish Standarti** | Avval izoh maydonlariga raqam kiritilganda xatolik berilar yoki faqat harflar qoldirilar edi, natijada sanalar, raqamli cheklar, xarajat kodi yoki smena raqamlarini izohda yozish imkoni yo'q edi. | 1) Backendda (`app/routes/given.py` va `app/routes/reports.py`) `validate_comment` funksiyasidagi raqamlarni taqiqlovchi cheklov (`re.search(r"\d", ...)`) butunlay bekor qilindi. 2) Frontendda (`static/js/app.js`) real-vaqtda kiritilayotgan raqamlarni tozalab tashlovchi filterlar olib tashlandi. 3) Endilikda barcha izoh maydonlariga (`Berilgan summa`, `Kunlik hisobot`, `Qarz sababi`) ham harflar, ham raqamlar, probel va belgilarni erkin kiritish mumkin (500 belgiga qadar). 4) Kesh versiyasi `app.js?v=308` ga yangilandi. |
| **47** | **Bosh Rahbarning Boshqaruvchi Maqomi & Xodim Amallarini Qat'iy Taqiqlovchi RBAC Himoyasi** | Avtomatlashtirilgan testda Bosh Rahbar tokeni orqali xodim funksiyalari (karta to'ldirish, berilgan summa, hisobot) yuborilib, jadvalda xodim ustunida "Bosh Rahbar" yozilib qolgan edi. Bosh Rahbar xodim emas, balki boshqaruvchi (ADMIN). | 1) Backendda (`app/routes/cards.py`, `app/routes/given.py`, `app/routes/reports.py`) xodimlik amallariga qat'iy tekshiruv qo'yildi: Bosh Rahbar (`role = 'ADMIN'`) xodim so'rovini yuborishga urinsa, darhol `HTTP 403 Forbidden` bilan bloklanadi. 2) Bazadan Bosh Rahbar nomidan tushib qolgan barcha soxta test yozuvlari tozalab tashlandi. 3) E2E test to'liq 2 ta alohida rolga ajratildi: Xodim (`Doniyor operator`) so'rovlarni yuboradi, Bosh Rahbar esa faqat ularni ko'rib chiqib tasdiqlaydi. |
| **48** | **Xodim Kunlik Hisobot Topshirganda Tafsilotlarni Telegram Lichkasiga Botdan Yuborish** | Xodim web panel orqali kunlik hisobotini topshirgach, uning nusxasi yoki qanday raqamlar bilan topshirilgani o'zida saqlanib qolmas edi. | 1) `app/bot.py` da `send_report_summary_to_telegram` funksiyasi yaratildi: Xodim hisobot topshirgan zahoti uning shaxsiy Telegram lichkasiga kirim (paynet, karta, leviy), chiqim (kunlik, terminal, berilgan summa, skidka, xarajat), sim-kartalar soni, qarz to'lovi, sof topshiriladigan summa va izoh chiroyli chek shaklida bot orqali yuboriladi. 2) Shuningdek, Rahbar hisobotni tasdiqlaganda yoki rad etganda ham xodimga avtomatik Telegram bildirishnomasi boradi (`send_report_status_to_telegram`). 3) Xabar yuborish asinxron fonda bajarilib, web API tezligiga zarracha ta'sir qilmaydi. |
| **49** | **Xodim Karta So'rovlari Tarixida "Rad etish" Tugmasi & Guruhda Statusni Qulflash** | Xodim adashib yuborgan yoki bekor qilmoqchi bo'lgan karta so'rovini o'zi rad eta olmas, guruhda esa xabar kutilmoqda bo'lib qolib ketar edi. | 1) Backendda `POST /api/cards/{topup_id}/reject` endpointi yaratildi: Xodim o'zining kutilayotgan (`PENDING`) so'rovini rad etishi mumkin, tasdiqlangan so'rovni esa rad etib bo'lmaydi. 2) Xodim rad etgan zahoti Telegram guruhidagi xabar matni `❌ Rad etildi (Xodim o'zi bekor qildi)` ga yangilanadi, barcha inline tugmalar butunlay olib tashlanadi va guruh adminlari tomonidan statusni qayta o'zgartirish mutlaqo taqiqlanadi (ogohlantirish oynasi bilan bloklanadi). 3) Frontend tarix jadvaliga "Amal" ustuni va `❌ Rad etish` tugmasi qo'shildi. |
| **50** | **3 Soat Davomida Harakatsizlikda Tizimga Qayta Kirish (Inactivity Timeout)** | Foydalanuvchi tizimda amal bajarmay tark etganda sessiya ochiq qolib xavfsizlik xavfi tug'dirishi mumkin edi. | 1) Xavfsizlik yuzasidan 3 soatlik (`INACTIVITY_TIMEOUT_MS = 10 800 000 ms`) harakatsizlik hisoblagichi o'rnatildi. 2) Foydalanuvchi harakatlari (sichqoncha, klaviatura, scroll, teginish) avtomatik qayd etib boriladi. 3) 3 soat davomida hech qanday amal bajarilmasa, xavfsizlik xabari bilan tokenlar tozalanadi va foydalanuvchi tizimga qayta kirishga yo'naltiriladi. |
| **51** | **Kichik Ekranli Qurilmalarda Dollar Kursi Modalining Responsiv Markazlashuvi** | Mobilda va kichik ekranlarda Dollar kursi modali ochilganda `align-items: flex-end` sababli pastga tushib ketayotgan va ekrandan qirqilayotgan edi. | 1) `#usd-rate-modal.modal-overlay` qat'iy markazlashtirildi (`align-items: center !important; justify-content: center !important`). 2) Kichik smartfonlar uchun `width: min(94vw, 400px)` va qulay ichki padding bilan to'liq responsiv holatga keltirildi. 3) Input shrift o'lchami dinamik `clamp()` bilan moslandi va modaldan tashqariga bosilganda yopilishi ta'minlandi. |
| **52** | **PWA (Progressive Web App) — Android va iPhone Uchun O'rnatiluvchi Mobil CRM Ilovasi** | Foydalanuvchilar har gal brauzer orqali kirish o'rniga, tizimni Android va iPhone telefonlariga ilova (App) kabi o'rnatib olish imkoniyatiga ega bo'lishni xohladi. | 1) `manifest.json` yaratildi (`standalone` rejim, `#090d16` mavzu rangi, 192x192, 512x512 va SVG piktogrammalar). 2) `sw.js` (Service Worker) o'rnatildi: barcha statik resurslar keshlanadi, biroq barcha `/api/` so'rovlari tarmoqqa to'g'ridan-to'g'ri o'tadi — bu backend va Supabase'ga zarracha ortiqcha yuklama bermaydi, aksincha server resursini tejaydi. 3) `vercel.json` va FastAPI (`app/main.py`) da `/sw.js` va `/manifest.json` root darajasida `Service-Worker-Allowed: /` bilan ulandi. 4) Navbarda va menyuda "Ilovani o'rnatish" tugmasi, Android uchun native o'rnatish, iOS (Safari) uchun esa qulay yo'riqnoma modali tatbiq etildi. |
| **53** | **Karta So'rovi Rad Etilganda Telegram Guruhidagi Karta Raqamini Nusxalanmaydigan Qilish** | Karta so'rovi rad etilganda yoki xodim tomonidan bekor qilinganda ham karta raqami `<code>` teglari ichida qolib, guruh adminlari adashib ustiga bosganda raqam nusxalanib to'lov qilib yuborish xavfi bor edi. | 1) Karta so'rovi xodim yoki admin tomonidan rad etilganda (`REJECTED`) Telegram guruh xabaridagi `<code>` teglari olib tashlandi va karta raqami oddiy matn (`plain text`) ko'rinishiga o'tkazildi. 2) Endilikda rad etilgan karta raqami ustiga Telegramda bosilganda u nusxalanmaydi. 3) Web CRM da ham rad etilgan kartalar tarixida nusxalash tugmasi olib tashlandi. 4) Kesh versiyasi `app.js?v=333` ga yangilandi. |
| **54** | **Render Uyqu Rejimi (Cold-Start) Kechikishini Bartaraf Etish & Doimiy 24/7 Uyg'oqlik** | Render.com bepul tarifi 15 daqiqa harakatsizlikdan so'ng uxlagani uchun, ancha vaqt kirmagan xodim qayta kirganida server 30-50s kechikib uyg'onar, OTP kod darhol kelmay qayta urinish talab qilinar edi. | 1) `.github/workflows/keep_alive.yml` yaratildi: Har 12 daqiqada `/health` endpointiga avtomatik ping yuborilib, Render serveri 24/7 uxlamaydigan qilindi. 2) Frontendda (`static/js/app.js`) sahifa ochilishi bilanoq `prewarmBackend()` orqali serverni fonda uyg'otish ulandi. 3) Kirish tugmasiga `⏳ Tekshirilmoqda...` va server sovuq uyg'onayotganda foydalanuvchiga 3-soniyadan keyin tushunarli holat ko'rsatuvchi indikator o'rnatildi. 4) Backendda `send_otp_to_telegram` tezkorligi 2.5s gacha optimallashtirildi. 5) Kesh versiyasi `app.js?v=334` ga yangilandi. |


---

## 7. 🚀 Joriy Tizim Holati va Sinov Ko'rsatmalari (Testing & Live Status)

1. **Mahalliy Server**:
   - Manzil: `http://127.0.0.1:8000` (FastAPI backend va toza interfeysli Single Page Web ilova).
2. **Bosh Rahbar Sifatida Sinash**:
   - **Telegram ID**: `8686341550`
   - **Boshlang'ich Parol**: `8686341550`
   - Tizim 6 xonali OTP kodini to'g'ridan-to'g'ri Telegram botingizga jo'natadi.
   - Tizimga kirilganda avtomatik tarzda Bosh Rahbar paneli (9 ta boshqaruv moduli) ochiladi.
   - "Sim-karta boshqaruvi va Qidiruv" modulidan 18 xonali seriya bo'yicha qidirish yoki yangi sim-kartalarni xodimlarga tarqatish mumkin.
3. **Kassir va Xodimlarni Sinash**:
   - Rahbar panelidagi "Xodimlar boshqaruvi" bo'limidan yangi xodim qo'shiladi.
   - "Kassir tayinlash" bo'limidan tanlangan xodim Kassir etib belgilanadi.
   - Belgilangan kassir login qilganda unga "Kassadan pul qabul qilish" va "Sim-karta tarqatish" maxsus modullari taqdim etiladi.
