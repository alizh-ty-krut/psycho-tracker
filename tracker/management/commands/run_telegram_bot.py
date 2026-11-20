import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone

from tracker.models import Session, TelegramConnection
from tracker.telegram_service import connect_chat_to_client
from tracker.translations import STRINGS

logger = logging.getLogger('tracker.telegram')
CODE_PATTERN = re.compile(r'^[A-Za-z0-9_-]{20,32}$')


class TelegramAPIError(Exception):
    def __init__(self, error_code):
        self.error_code = error_code
        super().__init__(f'Telegram API error {error_code}')


def telegram_api(token, method, payload=None, timeout=15):
    url = f'https://api.telegram.org/bot{token}/{method}'
    body = json.dumps(payload or {}).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as error:
        raise TelegramAPIError(error.code) from None
    if not result.get('ok'):
        raise TelegramAPIError(result.get('error_code', 0))
    return result.get('result')


def bot_reply(token, chat_id, text):
    telegram_api(token, 'sendMessage', {'chat_id': chat_id, 'text': text})


def link_reply_text(client):
    language = client.language if client.language in STRINGS else 'ru'
    translations = STRINGS[language]
    return translations['Telegram connected. You will receive session reminders here.']


def handle_message(token, message):
    chat = message.get('chat') or {}
    if chat.get('type') != 'private':
        return

    chat_id = chat.get('id')
    text = (message.get('text') or '').strip()
    if not chat_id or not text:
        return

    command, _, payload = text.partition(' ')
    command = command.split('@', 1)[0].lower()
    if command == '/unlink':
        connection = TelegramConnection.objects.select_related('client').filter(chat_id=chat_id).first()
        if connection:
            language = connection.client.language
            connection.delete()
            bot_reply(token, chat_id, 'Telegram отключён.' if language == 'ru' else 'Telegram has been disconnected.')
        else:
            bot_reply(token, chat_id, 'Этот чат не привязан к аккаунту. / This Telegram chat is not linked.')
        return
    if command in ('/start', '/help') and not payload:
        bot_reply(token, chat_id, STRINGS['ru']['Send the one-time code from your Point of Support account to connect Telegram.'] + '\n\n' + STRINGS['en']['Send the one-time code from your Point of Support account to connect Telegram.'])
        return

    candidate = payload.strip() if command == '/start' else text
    if not CODE_PATTERN.fullmatch(candidate):
        bot_reply(token, chat_id, 'Send a valid one-time code from the app. / Отправьте одноразовый код из приложения.')
        return

    client = connect_chat_to_client(candidate, chat_id)
    if client is None:
        bot_reply(token, chat_id, STRINGS['ru']['Telegram code is invalid or expired. Open your account page to create a new one.'] + '\n\n' + STRINGS['en']['Telegram code is invalid or expired. Open your account page to create a new one.'])
        return
    bot_reply(token, chat_id, link_reply_text(client))


def reminder_text(session):
    client = session.client
    language = client.language if client.language in STRINGS else 'ru'
    words = STRINGS[language]
    starts_at = timezone.localtime(session.starts_at)
    lines = [
        words['Session reminder'],
        words['Your session with your psychologist starts in 3 hours.'],
        f"{words['Date and time']}: {starts_at:%d.%m.%Y %H:%M}",
        f"{session.duration_minutes} {words['minutes']}",
    ]
    if session.location_or_link:
        lines.append(f"{words['Location']}: {session.location_or_link}")
    return '\n'.join(lines)


def send_due_reminders(token):
    now = timezone.now()
    upcoming = Session.objects.filter(
        reminder_sent_at__isnull=True,
        starts_at__gt=now,
        starts_at__lte=now + timedelta(hours=3),
    ).select_related('client')

    for session in upcoming.iterator():
        connection = TelegramConnection.objects.filter(client_id=session.client_id).first()
        if connection is None:
            continue
        try:
            bot_reply(token, connection.chat_id, reminder_text(session))
        except TelegramAPIError as error:
            if error.error_code in (400, 403):
                TelegramConnection.objects.filter(pk=connection.pk).delete()
            else:
                logger.warning('Telegram rejected a reminder (API error %s).', error.error_code)
            continue
        except (urllib.error.URLError, TimeoutError, OSError):
            logger.warning('Could not send a Telegram reminder; it will be retried.')
            continue
        Session.objects.filter(pk=session.pk, reminder_sent_at__isnull=True).update(reminder_sent_at=timezone.now())


class Command(BaseCommand):
    help = 'Run the Point of Support Telegram bot and session reminder worker.'

    def handle(self, *args, **options):
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not token:
            raise CommandError('Set TELEGRAM_BOT_TOKEN before starting the bot.')

        try:
            telegram_api(token, 'deleteWebhook', {'drop_pending_updates': False})
            bot = telegram_api(token, 'getMe')
        except (TelegramAPIError, urllib.error.URLError, TimeoutError, OSError):
            raise CommandError('Telegram Bot API is unavailable or TELEGRAM_BOT_TOKEN is invalid.') from None

        self.stdout.write(self.style.SUCCESS(f"Telegram bot @{bot.get('username', 'unknown')} is running. Press Ctrl+C to stop."))
        offset = None
        while True:
            close_old_connections()
            try:
                payload = {'timeout': 20, 'allowed_updates': ['message']}
                if offset is not None:
                    payload['offset'] = offset
                updates = telegram_api(token, 'getUpdates', payload, timeout=35) or []
                for update in updates:
                    try:
                        message = update.get('message') or {}
                        handle_message(token, message)
                    except (TelegramAPIError, urllib.error.URLError, TimeoutError, OSError):
                        logger.warning('Could not process a Telegram message; skipping this update.')
                    except Exception:
                        logger.exception('Telegram update processing failed.')
                    offset = update['update_id'] + 1
                send_due_reminders(token)
            except TelegramAPIError as error:
                logger.warning('Telegram polling failed (API error %s); retrying.', error.error_code)
                time.sleep(3)
            except (urllib.error.URLError, TimeoutError, OSError):
                logger.warning('Telegram polling is unavailable; retrying.')
                time.sleep(3)
            except KeyboardInterrupt:
                self.stdout.write('Telegram bot stopped.')
                return
