from django import template
from tracker.translations import STRINGS

register = template.Library()


@register.simple_tag(takes_context=True)
def tr(context, value):
    language = context.get('ui_language', 'ru')
    return STRINGS.get(language, STRINGS['ru']).get(value, value)
