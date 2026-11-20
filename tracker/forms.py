from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import MoodEntry, RequestItem, Session, SleepEntry

User = get_user_model()


class TherapistSignupForm(UserCreationForm):
    first_name = forms.CharField(max_length=150, required=True)
    last_name = forms.CharField(max_length=150, required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name')


class ClientSignupForm(TherapistSignupForm):
    invitation_code = forms.CharField(max_length=40)

    class Meta(TherapistSignupForm.Meta):
        fields = ('invitation_code', 'username', 'first_name', 'last_name')


class RequestForm(forms.ModelForm):
    priority = forms.IntegerField(min_value=1, required=False)

    class Meta:
        model = RequestItem
        fields = ('content',)
        widgets = {'content': forms.Textarea(attrs={'rows': 4})}


class MoodForm(forms.ModelForm):
    date = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    feeling = forms.CharField(max_length=160, required=True)
    cause = forms.CharField(required=True, widget=forms.Textarea(attrs={'rows': 3}))
    intensity = forms.IntegerField(min_value=1, max_value=10, validators=[MinValueValidator(1), MaxValueValidator(10)])
    class Meta:
        model = MoodEntry
        fields = ('date', 'feeling', 'cause', 'intensity', 'helpful_action', 'notes')
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}), 'cause': forms.Textarea(attrs={'rows': 3}), 'helpful_action': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 2})}


class SleepForm(forms.ModelForm):
    date = forms.DateField(required=True, widget=forms.DateInput(attrs={'type': 'date'}))
    bedtime = forms.TimeField(required=True, widget=forms.TimeInput(attrs={'type': 'time'}))
    wake_time = forms.TimeField(required=True, widget=forms.TimeInput(attrs={'type': 'time'}))
    quality = forms.IntegerField(min_value=1, max_value=10, validators=[MinValueValidator(1), MaxValueValidator(10)])
    wellbeing = forms.CharField(required=True, widget=forms.Textarea(attrs={'rows': 2}))
    class Meta:
        model = SleepEntry
        fields = ('date', 'bedtime', 'wake_time', 'quality', 'wellbeing', 'last_coffee', 'notes')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}), 'bedtime': forms.TimeInput(attrs={'type': 'time'}),
            'wake_time': forms.TimeInput(attrs={'type': 'time'}), 'last_coffee': forms.TimeInput(attrs={'type': 'time'}),
            'wellbeing': forms.Textarea(attrs={'rows': 2}), 'notes': forms.Textarea(attrs={'rows': 2}),
        }


class SessionForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = ('starts_at', 'duration_minutes', 'location_or_link')
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'location_or_link': forms.TextInput(attrs={'placeholder': 'Room, address, or meeting link'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['starts_at'].input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S']
        self.fields['duration_minutes'].min_value = 1
        self.fields['duration_minutes'].max_value = 480


class CommentForm(forms.Form):
    content = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), max_length=5000)


class InvitationForm(forms.Form):
    pass


class UsernameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('username',)
