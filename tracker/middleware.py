from django.utils import translation


class UserLanguageMiddleware:
    """Activate the selected UI language for Django's built-in form messages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = request.user.language if request.user.is_authenticated else request.session.get('language', 'ru')
        if language not in ('ru', 'en'):
            language = 'ru'
        translation.activate(language)
        request.LANGUAGE_CODE = language
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()
        return response
