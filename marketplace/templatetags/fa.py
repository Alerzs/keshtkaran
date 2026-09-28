from django import template

register = template.Library()

_FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


@register.filter
def fa_digits(value):
    if value is None:
        return ''
    return str(value).translate(_FA_DIGITS)


@register.filter
def toman(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return value
    if number == 0:
        return 'توافقی'
    formatted = f'{number:,}'.replace(',', '٬')
    return fa_digits(formatted) + ' تومان'
