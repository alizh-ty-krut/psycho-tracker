import hashlib
import json
import secrets
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import PasswordChangeView
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import ClientSignupForm, CommentForm, MoodForm, RequestForm, SessionForm, SleepForm, TherapistSignupForm, UsernameForm
from .models import Invitation, MoodComment, MoodEntry, RequestComment, RequestItem, Session, SleepComment, SleepEntry, TelegramConnection, TelegramLinkCode, User
from .translations import STRINGS


def localize_form(form, language):
    labels = {
        'first_name': 'First name', 'last_name': 'Last name', 'username': 'Username', 'password1': 'Password',
        'password2': 'Password confirmation', 'invitation_code': 'Invitation code', 'content': 'Request',
        'priority': 'Priority', 'date': 'Date', 'feeling': 'Feeling', 'cause': 'Cause', 'intensity': 'Intensity (1–10)',
        'helpful_action': 'What could help', 'notes': 'Notes', 'bedtime': 'Bedtime', 'wake_time': 'Wake time',
        'quality': 'Sleep quality (1–10)', 'wellbeing': 'Wellbeing', 'last_coffee': 'Last coffee',
        'old_password': 'Old password', 'new_password1': 'New password', 'new_password2': 'New password confirmation',
        'starts_at': 'Session date and time', 'duration_minutes': 'Duration in minutes', 'location_or_link': 'Location or meeting link',
    }
    translations = STRINGS.get(language, STRINGS['ru'])
    for name, field in form.fields.items():
        field.label = translations.get(labels.get(name, field.label), labels.get(name, field.label))
    if 'location_or_link' in form.fields:
        form.fields['location_or_link'].widget.attrs['placeholder'] = translations.get('Room, address, or meeting link', 'Room, address, or meeting link')
    return form


def role_required(role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.role != role:
                return redirect('home')
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


def home(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return redirect('therapist_dashboard' if request.user.role == User.Role.THERAPIST else 'client_dashboard')


def therapist_signup(request):
    if User.objects.filter(role=User.Role.THERAPIST).exists():
        return render(request, 'tracker/message.html', {'title': 'Therapist setup', 'message': 'This site already has a psychologist account.'})
    form = TherapistSignupForm(request.POST or None)
    localize_form(form, request.session.get('language', 'ru'))
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            if User.objects.filter(role=User.Role.THERAPIST).exists():
                return render(request, 'tracker/message.html', {'title': 'Therapist setup', 'message': 'This site already has a psychologist account.'})
            user = form.save(commit=False)
            user.role = User.Role.THERAPIST
            user.language = request.session.get('language', 'ru')
            user.save()
        login(request, user)
        return redirect('therapist_dashboard')
    return render(request, 'tracker/signup.html', {'form': form, 'title': 'Create therapist account', 'therapist': True})


def client_signup(request):
    form = ClientSignupForm(request.POST or None)
    localize_form(form, request.session.get('language', 'ru'))
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['invitation_code'].strip()
        digest = hashlib.sha256(code.encode()).hexdigest()
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().filter(code_hash=digest, used_at__isnull=True, expires_at__gt=timezone.now()).first()
            if not invitation:
                language = request.session.get('language', 'ru')
                form.add_error('invitation_code', STRINGS.get(language, STRINGS['ru'])['Invitation code is invalid, expired, or already used.'])
            else:
                user = form.save(commit=False)
                user.role = User.Role.CLIENT
                user.language = request.session.get('language', 'ru')
                user.save()
                invitation.used_at = timezone.now()
                invitation.save(update_fields=['used_at'])
                login(request, user)
                return redirect('client_dashboard')
    return render(request, 'tracker/signup.html', {'form': form, 'title': 'Register with code'})


@role_required(User.Role.THERAPIST)
def therapist_dashboard(request):
    clients = User.objects.filter(role=User.Role.CLIENT).order_by('last_name', 'first_name', 'username')
    return render(request, 'tracker/therapist_dashboard.html', {'clients': clients, 'invitations': Invitation.objects.filter(created_by=request.user, used_at__isnull=True, expires_at__gt=timezone.now()).order_by('-created_at')})


@role_required(User.Role.THERAPIST)
def create_invitation(request):
    if request.method != 'POST':
        return redirect('therapist_dashboard')
    code = secrets.token_urlsafe(12)
    Invitation.objects.create(code_hash=hashlib.sha256(code.encode()).hexdigest(), created_by=request.user, expires_at=timezone.now() + timedelta(hours=12))
    return render(request, 'tracker/invitation_created.html', {'code': code})


@role_required(User.Role.CLIENT)
def client_dashboard(request):
    return render(request, 'tracker/client_dashboard.html', {
        'requests': RequestItem.objects.filter(client=request.user, is_closed=False),
        'mood_count': MoodEntry.objects.filter(client=request.user).count(),
        'sleep_count': SleepEntry.objects.filter(client=request.user).count(),
        'sessions': Session.objects.filter(client=request.user, starts_at__gte=timezone.now()),
        'telegram_connected': hasattr(request.user, 'telegram_connection'),
    })


@role_required(User.Role.THERAPIST)
def therapist_client(request, client_id):
    client = get_object_or_404(User, pk=client_id, role=User.Role.CLIENT)
    requests = list(RequestItem.objects.filter(client=client, is_closed=False))
    closed_requests = list(RequestItem.objects.filter(client=client, is_closed=True).order_by('-created_at'))
    mood_entries = list(MoodEntry.objects.filter(client=client))
    sleep_entries = list(SleepEntry.objects.filter(client=client))
    add_legacy_data(requests, 'request')
    add_legacy_data(closed_requests, 'request')
    add_legacy_data(mood_entries, 'mood')
    add_legacy_data(sleep_entries, 'sleep')
    for entry in requests + closed_requests:
        if hasattr(entry, 'therapist_comment'):
            entry.therapist_comment.legacy_e2ee = json.dumps({'content': entry.therapist_comment.content}, ensure_ascii=False) if not entry.therapist_comment.encrypted_payload else ''
    for entry in mood_entries + sleep_entries:
        if hasattr(entry, 'therapist_comment'):
            entry.therapist_comment.legacy_e2ee = json.dumps({'content': entry.therapist_comment.content}, ensure_ascii=False) if not entry.therapist_comment.encrypted_payload else ''
    return render(request, 'tracker/therapist_client.html', {
        'client': client,
        'requests': requests,
        'closed_requests': closed_requests,
        'mood_entries': mood_entries,
        'sleep_entries': sleep_entries,
        'sessions': Session.objects.filter(client=client, starts_at__gte=timezone.now()),
        'comment_form': CommentForm(),
    })


@role_required(User.Role.CLIENT)
def request_list(request):
    requests = list(RequestItem.objects.filter(client=request.user, is_closed=False))
    closed_requests = list(RequestItem.objects.filter(client=request.user, is_closed=True).order_by('-created_at'))
    add_legacy_data(requests, 'request')
    add_legacy_data(closed_requests, 'request')
    return render(request, 'tracker/requests.html', {
        'requests': requests,
        'closed_requests': closed_requests,
    })


@role_required(User.Role.CLIENT)
def request_edit(request, request_id=None):
    entry = get_object_or_404(RequestItem, pk=request_id, client=request.user, is_closed=False) if request_id else None
    if request.method == 'POST':
        payload = request.POST.get('encrypted_payload', '')
        if not payload.startswith('e2e1:'):
            raise Http404
        desired = request.POST.get('priority')
        try:
            desired = int(desired) if desired else None
        except ValueError:
            desired = None
        with transaction.atomic():
            active = RequestItem.objects.filter(client=request.user, is_closed=False)
            if entry:
                active.exclude(pk=entry.pk).filter(priority__gt=entry.priority).update(priority=F('priority') - 1)
                RequestItem.objects.filter(pk=entry.pk).update(priority=None)
                count = active.exclude(pk=entry.pk).count()
            else:
                count = active.count()
            target = max(1, min(desired or count + 1, count + 1))
            active.filter(priority__gte=target).update(priority=F('priority') + 1)
            saved = entry or RequestItem(client=request.user)
            saved.content = ''
            saved.encrypted_payload = payload
            saved.priority = target
            saved.is_closed = False
            saved.save()
            normalize_priorities(request.user)
        return redirect('request_list')
    form = RequestForm(instance=entry, initial={'priority': entry.priority if entry else None})
    localize_form(form, request.user.language)
    return render(request, 'tracker/form.html', {'form': form, 'title': 'Edit' if entry else 'Add request', 'back_url': 'request_list', 'e2ee': True, 'e2ee_client_id': request.user.pk, 'encrypted_payload': entry.encrypted_payload if entry else ''})


def normalize_priorities(client):
    items = list(RequestItem.objects.filter(client=client, is_closed=False).order_by('priority', 'created_at', 'id'))
    for number, item in enumerate(items, 1):
        if item.priority != number:
            item.priority = number
    RequestItem.objects.bulk_update(items, ['priority'])


@role_required(User.Role.CLIENT)
@require_POST
def request_close(request, request_id):
    entry = get_object_or_404(RequestItem, pk=request_id, client=request.user, is_closed=False)
    with transaction.atomic():
        RequestItem.objects.filter(client=request.user, is_closed=False, priority__gt=entry.priority).update(priority=F('priority') - 1)
        entry.is_closed = True
        entry.priority = None
        entry.save(update_fields=['is_closed', 'priority'])
        normalize_priorities(request.user)
    return redirect('request_list')


@role_required(User.Role.CLIENT)
@require_POST
def request_delete(request, request_id):
    entry = get_object_or_404(RequestItem, pk=request_id, client=request.user)
    old_priority = entry.priority
    was_open = not entry.is_closed
    entry.delete()
    if was_open and old_priority:
        RequestItem.objects.filter(client=request.user, is_closed=False, priority__gt=old_priority).update(priority=F('priority') - 1)
        normalize_priorities(request.user)
    return redirect('request_list')


def diary_view(request, kind):
    model, form_class, template, context_name = (MoodEntry, MoodForm, 'tracker/mood_diary.html', 'mood_entries') if kind == 'mood' else (SleepEntry, SleepForm, 'tracker/sleep_diary.html', 'sleep_entries')
    entries = list(model.objects.filter(client=request.user))
    add_legacy_data(entries, kind)
    for entry in entries:
        if hasattr(entry, 'therapist_comment'):
            entry.therapist_comment.legacy_e2ee = json.dumps({'content': entry.therapist_comment.content}, ensure_ascii=False) if not entry.therapist_comment.encrypted_payload else ''
    return render(request, template, {'entries': entries, context_name: entries, 'form': localize_form(form_class(), request.user.language), 'kind': kind})


@role_required(User.Role.CLIENT)
def mood_diary(request):
    return diary_view(request, 'mood')


@role_required(User.Role.CLIENT)
def sleep_diary(request):
    return diary_view(request, 'sleep')


@role_required(User.Role.CLIENT)
def diary_create(request, kind, entry_id=None):
    model, form_class, route = (MoodEntry, MoodForm, 'mood_diary') if kind == 'mood' else (SleepEntry, SleepForm, 'sleep_diary')
    entry = get_object_or_404(model, pk=entry_id, client=request.user) if entry_id else None
    if request.method == 'POST':
        payload = request.POST.get('encrypted_payload', '')
        if not payload.startswith('e2e1:'):
            raise Http404
        saved = entry or model(client=request.user)
        saved.encrypted_payload = payload
        if kind == 'mood':
            saved.date, saved.feeling, saved.cause, saved.intensity = None, '', '', 0
            saved.helpful_action, saved.notes = '', ''
        else:
            saved.date, saved.bedtime, saved.wake_time, saved.quality = None, None, None, 0
            saved.wellbeing, saved.last_coffee, saved.notes = '', None, ''
        saved.save()
        return redirect(route)
    form = localize_form(form_class(instance=None), request.user.language)
    legacy = legacy_payload(entry, kind) if entry and not entry.encrypted_payload else ''
    return render(request, 'tracker/form.html', {'form': form, 'title': 'Edit' if entry else 'Add entry', 'back_url': route, 'e2ee': True, 'e2ee_client_id': request.user.pk, 'encrypted_payload': entry.encrypted_payload if entry else '', 'legacy_payload': json.dumps(legacy, ensure_ascii=False) if legacy else '', 'e2ee_kind': kind})


@role_required(User.Role.CLIENT)
@require_POST
def diary_delete(request, kind, entry_id):
    model = MoodEntry if kind == 'mood' else SleepEntry
    route = 'mood_diary' if kind == 'mood' else 'sleep_diary'
    get_object_or_404(model, pk=entry_id, client=request.user).delete()
    return redirect(route)


@role_required(User.Role.THERAPIST)
@require_POST
def therapist_comment(request, client_id, kind, entry_id):
    client = get_object_or_404(User, pk=client_id, role=User.Role.CLIENT)
    payload = request.POST.get('encrypted_payload', '')
    if payload.startswith('e2e1:'):
        if kind == 'request':
            entry = get_object_or_404(RequestItem, pk=entry_id, client=client)
            comment, _ = RequestComment.objects.get_or_create(request=entry, defaults={'author': request.user})
        elif kind == 'mood':
            entry = get_object_or_404(MoodEntry, pk=entry_id, client=client)
            comment, _ = MoodComment.objects.get_or_create(entry=entry, defaults={'author': request.user})
        elif kind == 'sleep':
            entry = get_object_or_404(SleepEntry, pk=entry_id, client=client)
            comment, _ = SleepComment.objects.get_or_create(entry=entry, defaults={'author': request.user})
        else:
            raise Http404
        comment.content = ''
        comment.encrypted_payload = payload
        comment.author = request.user
        comment.save()
    return redirect('therapist_client', client_id=client.pk)


@login_required
@require_POST
def e2ee_migrate_legacy(request, client_id, kind, entry_id):
    client = get_object_or_404(User, pk=client_id, role=User.Role.CLIENT)
    if request.user.role == User.Role.CLIENT and request.user.pk != client.pk:
        raise Http404
    if request.user.role not in (User.Role.CLIENT, User.Role.THERAPIST):
        raise Http404
    try:
        payload = json.loads(request.body.decode('utf-8')).get('payload', '')
    except (ValueError, UnicodeDecodeError):
        raise Http404
    if not isinstance(payload, str) or not payload.startswith('e2e1:'):
        raise Http404
    if kind == 'request':
        entry = get_object_or_404(RequestItem, pk=entry_id, client=client)
        entry.content, entry.encrypted_payload = '', payload
        entry.save(update_fields=['content', 'encrypted_payload'])
    elif kind == 'mood':
        entry = get_object_or_404(MoodEntry, pk=entry_id, client=client)
        entry.encrypted_payload = payload
        entry.date, entry.feeling, entry.cause, entry.intensity = None, '', '', 0
        entry.helpful_action, entry.notes = '', ''
        entry.save()
    elif kind == 'sleep':
        entry = get_object_or_404(SleepEntry, pk=entry_id, client=client)
        entry.encrypted_payload = payload
        entry.date, entry.bedtime, entry.wake_time, entry.quality = None, None, None, 0
        entry.wellbeing, entry.last_coffee, entry.notes = '', None, ''
        entry.save()
    elif kind in ('request_comment', 'mood_comment', 'sleep_comment'):
        model = {'request_comment': RequestComment, 'mood_comment': MoodComment, 'sleep_comment': SleepComment}[kind]
        comment = get_object_or_404(model, pk=entry_id)
        owner = comment.request.client if kind == 'request_comment' else comment.entry.client
        if owner.pk != client.pk:
            raise Http404
        comment.content, comment.encrypted_payload = '', payload
        comment.save(update_fields=['content', 'encrypted_payload'])
    else:
        raise Http404
    return JsonResponse({'ok': True})


def language(request):
    if request.method == 'POST':
        chosen = request.POST.get('language', 'ru')
        if chosen in ('ru', 'en'):
            request.session['language'] = chosen
            if request.user.is_authenticated:
                request.user.language = chosen
                request.user.save(update_fields=['language'])
    destination = request.POST.get('next') or 'home'
    if not url_has_allowed_host_and_scheme(destination, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        destination = 'home'
    return redirect(destination)


@login_required
def username_change(request):
    form = localize_form(UsernameForm(request.POST or None, instance=request.user), request.user.language)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, STRINGS.get(request.user.language, STRINGS['ru'])['Saved'])
        return redirect('home')
    return render(request, 'tracker/form.html', {'form': form, 'title': 'Username', 'back_url': 'home'})


class SitePasswordChangeView(PasswordChangeView):
    form_class = PasswordChangeForm
    template_name = 'tracker/form.html'
    success_url = reverse_lazy('home')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Password'
        context['back_url'] = 'home'
        context['form'] = localize_form(context['form'], self.request.user.language)
        return context


def legacy_payload(entry, kind):
    if kind == 'request':
        return {'content': entry.content}
    if kind == 'mood':
        return {'date': entry.date.isoformat() if entry.date else '', 'feeling': entry.feeling, 'cause': entry.cause, 'intensity': entry.intensity, 'helpful_action': entry.helpful_action, 'notes': entry.notes}
    if kind == 'sleep':
        return {'date': entry.date.isoformat() if entry.date else '', 'bedtime': entry.bedtime.strftime('%H:%M') if entry.bedtime else '', 'wake_time': entry.wake_time.strftime('%H:%M') if entry.wake_time else '', 'quality': entry.quality, 'wellbeing': entry.wellbeing, 'last_coffee': entry.last_coffee.strftime('%H:%M') if entry.last_coffee else '', 'notes': entry.notes}
    return {}


def add_legacy_data(entries, kind):
    for entry in entries:
        entry.legacy_e2ee = json.dumps(legacy_payload(entry, kind), ensure_ascii=False) if not entry.encrypted_payload else ''


@role_required(User.Role.CLIENT)
def encryption_keys(request):
    return render(request, 'tracker/encryption_keys.html', {'client_id': request.user.pk})


@role_required(User.Role.CLIENT)
def telegram_link(request):
    code = None
    if request.method == 'POST':
        raw_code = secrets.token_urlsafe(18)
        now = timezone.now()
        TelegramLinkCode.objects.filter(client=request.user, used_at__isnull=True).update(used_at=now)
        TelegramLinkCode.objects.create(
            client=request.user,
            code_hash=hashlib.sha256(raw_code.encode('utf-8')).hexdigest(),
            expires_at=now + timedelta(minutes=15),
        )
        code = raw_code
    return render(request, 'tracker/telegram_link.html', {
        'code': code,
        'connected': TelegramConnection.objects.filter(client=request.user).exists(),
        'bot_username': settings.TELEGRAM_BOT_USERNAME,
    })


@role_required(User.Role.CLIENT)
@require_POST
def telegram_disconnect(request):
    TelegramConnection.objects.filter(client=request.user).delete()
    TelegramLinkCode.objects.filter(client=request.user, used_at__isnull=True).update(used_at=timezone.now())
    return redirect('telegram_link')


@role_required(User.Role.THERAPIST)
def session_edit(request, client_id, session_id=None):
    client = get_object_or_404(User, pk=client_id, role=User.Role.CLIENT)
    session = get_object_or_404(Session, pk=session_id, client=client) if session_id else None
    previous_start = session.starts_at if session else None
    form = localize_form(SessionForm(request.POST or None, instance=session), request.user.language)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.client = client
        if session is None or saved.starts_at != previous_start:
            saved.reminder_sent_at = None
        saved.save()
        return redirect('therapist_client', client_id=client.pk)
    return render(request, 'tracker/form.html', {
        'form': form,
        'title': 'Edit session' if session else 'Add session',
        'back_url': 'therapist_dashboard',
    })


@role_required(User.Role.THERAPIST)
@require_POST
def session_delete(request, client_id, session_id):
    client = get_object_or_404(User, pk=client_id, role=User.Role.CLIENT)
    get_object_or_404(Session, pk=session_id, client=client).delete()
    return redirect('therapist_client', client_id=client.pk)
