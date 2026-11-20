def ui_context(request):
    language = getattr(request.user, 'language', None) if request.user.is_authenticated else request.session.get('language', 'ru')
    return {'ui_language': language or 'ru'}
