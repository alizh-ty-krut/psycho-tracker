from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Invitation, MoodComment, MoodEntry, RequestComment, RequestItem, Session, SleepComment, SleepEntry, TelegramConnection, TelegramLinkCode, User


@admin.register(User)
class SiteUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (('Profile', {'fields': ('role', 'language')}),)
    list_display = ('username', 'first_name', 'last_name', 'role', 'is_active')


admin.site.register((Invitation, RequestItem, RequestComment, MoodEntry, MoodComment, SleepEntry, SleepComment, TelegramLinkCode, TelegramConnection, Session))
