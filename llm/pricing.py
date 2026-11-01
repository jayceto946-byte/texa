"""Service-side import cost estimates; prices never belong in the import form."""
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

PRICE_SOURCE = 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'
PRICE_DATE = '2026-11-01'


def import_rates(resolved, *, now=None):
    if (resolved.provider.provider_id == 'deepseek' and urlparse(resolved.endpoint).hostname == 'api.deepseek.com'
            and resolved.model in {'deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-flash-vision-exp'}):
        local = (now or datetime.now(timezone.utc)).astimezone(timezone(timedelta(hours=8)))
        peak = local.weekday() < 5 and (9 <= local.hour < 12 or 14 <= local.hour < 18)
        # Weekday holiday discounts can only lower this conservative estimate.
        factor = 2 if peak else 1
        return dict(input_price=1 * factor, cached_input_price=.02 * factor, output_price=4 * factor,
                    currency='CNY', source=PRICE_SOURCE, checked=PRICE_DATE, period='peak' if peak else 'off_peak')
    return None


def usage_cost(usage, rates):
    if not rates or usage.get('prompt_tokens') is None or usage.get('completion_tokens') is None:
        return None
    cached = usage.get('prompt_cache_hit_tokens', (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0)) or 0
    return ((usage['prompt_tokens'] - cached) * rates['input_price'] + cached * rates['cached_input_price']
            + usage['completion_tokens'] * rates['output_price']) / 1_000_000
