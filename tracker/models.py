from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q


class User(AbstractUser):
    class Role(models.TextChoices):
        THERAPIST = 'therapist', 'Psychologist'
        CLIENT = 'client', 'Client'

    role = models.CharField(max_length=12, choices=Role.choices)
    language = models.CharField(max_length=2, choices=[('ru', 'Русский'), ('en', 'English')], default='ru')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['role'], condition=Q(role='therapist'), name='one_site_therapist')]


class Invitation(models.Model):
    code_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='invitations')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class TelegramLinkCode(models.Model):
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='telegram_link_codes')
    code_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class TelegramConnection(models.Model):
    client = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='telegram_connection')
    chat_id = models.BigIntegerField(unique=True)
    linked_at = models.DateTimeField(auto_now_add=True)


class RequestItem(models.Model):
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='requests')
    content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    priority = models.PositiveIntegerField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ['priority', 'created_at', 'id']


class RequestComment(models.Model):
    request = models.OneToOneField(RequestItem, on_delete=models.CASCADE, related_name='therapist_comment')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class MoodEntry(models.Model):
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mood_entries')
    date = models.DateField(null=True, blank=True)
    feeling = models.CharField(max_length=160, blank=True)
    cause = models.TextField(blank=True)
    intensity = models.PositiveSmallIntegerField(default=0)
    helpful_action = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']


class MoodComment(models.Model):
    entry = models.OneToOneField(MoodEntry, on_delete=models.CASCADE, related_name='therapist_comment')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class SleepEntry(models.Model):
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sleep_entries')
    date = models.DateField(null=True, blank=True)
    bedtime = models.TimeField(null=True, blank=True)
    wake_time = models.TimeField(null=True, blank=True)
    quality = models.PositiveSmallIntegerField(default=0)
    wellbeing = models.TextField(blank=True)
    last_coffee = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']


class SleepComment(models.Model):
    entry = models.OneToOneField(SleepEntry, on_delete=models.CASCADE, related_name='therapist_comment')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class Session(models.Model):
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sessions')
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=50)
    location_or_link = models.CharField(max_length=500, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['starts_at']

    def __str__(self):
        return f'{self.client.username} · {self.starts_at:%Y-%m-%d %H:%M}'
