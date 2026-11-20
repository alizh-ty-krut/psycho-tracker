import hashlib

from django.db import transaction
from django.utils import timezone

from .models import TelegramConnection, TelegramLinkCode


@transaction.atomic
def connect_chat_to_client(raw_code, chat_id):
    code_hash = hashlib.sha256(raw_code.encode('utf-8')).hexdigest()
    link_code = TelegramLinkCode.objects.select_for_update().select_related('client').filter(
        code_hash=code_hash,
        used_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    if link_code is None:
        return None

    current_owner = TelegramConnection.objects.filter(chat_id=chat_id).first()
    if current_owner and current_owner.client_id != link_code.client_id:
        return None

    connection, _ = TelegramConnection.objects.update_or_create(
        client=link_code.client,
        defaults={'chat_id': chat_id},
    )
    link_code.used_at = timezone.now()
    link_code.save(update_fields=['used_at'])
    TelegramLinkCode.objects.filter(client=link_code.client, used_at__isnull=True).update(used_at=timezone.now())
    return link_code.client
