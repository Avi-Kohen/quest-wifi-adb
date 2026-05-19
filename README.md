# Quest WiFi ADB Connector

אפליקציית GUI פשוטה לחיבור מהיר של משקפות Meta Quest לרשת WiFi דרך ADB — בלי לשים את המשקפת על הראש בכל פעם.

## מה האפליקציה עושה?

- מזהה משקפת מחוברת דרך `adb devices`
- מציגה מצב:
  - 🔴 אדום — אין משקפת מחוברת / ADB לא מוכן
  - 🟡 צהוב — המשקפת מחוברת אבל צריך לאשר USB Debugging / Always Allow
  - 🟢 ירוק — המשקפת במצב `device` ומוכנה לשליחה
- מקבלת שם רשת וסיסמה
- מריצה:
  ```bash
  adb shell svc wifi enable
  adb shell cmd wifi connect-network "WIFI NAME" wpa2 "WIFI PASS"
  ```
- משאירה את שם הרשת והסיסמה במסך כדי לחבר מהר את המשקפת הבאה

> ברירת המחדל היא לא לשמור את הסיסמה לקובץ. היא נשארת רק בחלון האפליקציה עד שסוגרים אותה.

## דרישות

1. Python 3.10+
2. Android SDK Platform-Tools / ADB
3. Meta Quest במצב Developer Mode
4. כבל USB שתומך Data, לא רק טעינה
5. אישור USB Debugging בתוך המשקפת, כולל סימון:
   `Always allow from this computer`

## התקנה והרצה ב-Windows

פתח PowerShell או Terminal בתוך תיקיית הפרויקט:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python app.py
```

אם `adb` לא נמצא, הורד Android Platform Tools ושם את התיקייה כך:

```text
quest_wifi_adb/
├─ app.py
├─ platform-tools/
│  ├─ adb.exe
│  ├─ AdbWinApi.dll
│  └─ AdbWinUsbApi.dll
```

ואז הרץ שוב:

```powershell
python app.py
```

## איך משתמשים בשטח?

1. פותחים את האפליקציה.
2. מכניסים SSID וסיסמה.
3. מחברים משקפת עם USB.
4. אם הצבע צהוב — שמים את המשקפת פעם אחת ומאשרים `Always allow`.
5. כשהצבע ירוק — לוחצים `שלח WiFi למשקפת`.
6. מנתקים את המשקפת ומחברים את הבאה.
7. שם הרשת והסיסמה נשארים במסך.

## העלאה ל-GitHub

```bash
git init
git add .
git commit -m "Initial Quest WiFi ADB GUI"
git branch -M main
git remote add origin https://github.com/YOUR_USER/quest-wifi-adb.git
git push -u origin main
```

## בניית EXE בעתיד

אפשר לארוז עם PyInstaller:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --windowed --onefile --name QuestWifiADB app.py
```

אם אתה רוצה שה־EXE ימצא ADB בלי התקנה, שים את `platform-tools` ליד קובץ ה־EXE.
