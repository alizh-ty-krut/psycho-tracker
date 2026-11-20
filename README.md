# Point of Support

Point of Support is a self-hosted website for one psychologist and their clients. It includes private requests, wellbeing and sleep diaries, comments, sessions, and Telegram reminders.

The website and Telegram bot run on **your own computer**. The computer must stay on and connected to the internet whenever clients need the site or reminders.

## Start the website on your computer

Python 3.10 or later is required.

1. Open PowerShell (Windows) or Terminal (macOS/Linux) in the project folder.
2. Create a Python environment:

   ```sh
   python -m venv .venv
   ```

3. Activate it:
   - Windows PowerShell: `.venv\Scripts\Activate.ps1`
   - macOS/Linux: `source .venv/bin/activate`
4. Install the website software and make the database:

   ```sh
   python -m pip install -r requirements.txt
   python manage.py migrate
   ```

5. Start the website for your own computer:

   ```sh
   python manage.py runserver
   ```

6. Open `http://127.0.0.1:8000/` and create the psychologist account.

`runserver` is for trying the site on your own computer only. Do not expose port 8000 to the internet.

## Let clients reach it over the internet

The website stays on your computer; no VPS or cloud database is used. To make it reachable from outside your home or office, you need:

- A computer that stays on and connected.
- A domain name (usually paid).
- A public internet address from your internet provider. Some providers use CGNAT, which prevents incoming connections; ask your provider whether they can give you a public IP.
- A change to your router settings to forward web traffic to your computer.
- HTTPS, so passwords and login cookies are protected while travelling over the internet.

These router steps differ by model. Reserve a fixed local address for your computer in the router. Then forward **ports 80 and 443** to that computer. Do not forward port 8000. In your domain settings, point an `A` record to your public IP. If your IP changes, update the record or use a dynamic DNS service.

### Windows setup for internet access

Keep the project folder and database on the Windows computer that will host the site. In PowerShell, from the project folder, install a production web server and prepare static files:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install waitress
python manage.py collectstatic --noinput
```

Create a strong Django secret key:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copy the result. In the same PowerShell window, set these values (replace the example domain and secret):

```powershell
$env:DJANGO_SECRET_KEY = "paste-your-secret-here"
$env:DJANGO_DEBUG = "0"
$env:DJANGO_ALLOWED_HOSTS = "support.example.com"
$env:DJANGO_CSRF_TRUSTED_ORIGINS = "https://support.example.com"
$env:DJANGO_SECURE_COOKIES = "1"
$env:DJANGO_SECURE_SSL_REDIRECT = "1"
$env:DJANGO_SECURE_PROXY_SSL_HEADER = "1"
```

Install [Caddy](https://caddyserver.com/docs/install) on the same computer. Create or edit its `Caddyfile` and use your real domain and project path:

```caddyfile
support.example.com {
    handle_path /static/* {
        root * C:/path/to/psycho-tracker/staticfiles
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:8000
    }
}
```

Start the website in one PowerShell window:

```powershell
.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:8000 config.wsgi:application
```

Start Caddy in another PowerShell window:

```powershell
caddy run --config Caddyfile
```

After the domain points to your public IP and router ports 80 and 443 are forwarded, open `https://support.example.com`. Leave both windows open. After restarting the computer, start both again. Caddy obtains and renews the HTTPS certificate automatically.

On macOS or Linux, use Gunicorn instead of Waitress:

```sh
python -m pip install gunicorn
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 127.0.0.1:8000
```

Caddy can run on those systems too. The router, domain, and HTTPS requirements are the same.

## Telegram reminders

Create a bot with [@BotFather](https://t.me/BotFather). Keep its token private. In the PowerShell window used for the site, set the token and username:

```powershell
$env:TELEGRAM_BOT_TOKEN = "paste-your-bot-token-here"
$env:TELEGRAM_BOT_USERNAME = "your_bot_name"
```

Open another PowerShell window, go to the project folder, activate `.venv`, set the same `TELEGRAM_BOT_TOKEN`, then run:

```powershell
python manage.py run_telegram_bot
```

Keep that window open too. The psychologist adds sessions on each client's page. A client creates a one-time Telegram code in their account and sends it to the bot. The bot needs to stay running to link accounts and send reminders.

## Privacy

Diary entries, requests, comments, account names, session information, and Telegram chat IDs are stored in the local SQLite database without application-level encryption. Keep the computer and `db.sqlite3` private, use a strong computer login password, and protect backups. HTTPS protects traffic when clients connect from the internet, but it does not encrypt the database file.

## Backups

The site does not make backups automatically. Stop the website before copying `db.sqlite3`, or use a backup method that safely copies a live SQLite database. Store backups somewhere separate and protect them. Backups made before old entries were encrypted still contain readable text.

## If clients cannot open the site

- Check that the website and Caddy windows are still running.
- Check that the domain points to your current public IP.
- Check router forwarding and the computer's firewall for ports 80 and 443.
- Ask your internet provider whether your connection uses CGNAT. If it does, direct incoming connections will not work unless the provider offers a public IP.
- Do not solve this by opening port 8000 or by leaving Django's debug mode on.
