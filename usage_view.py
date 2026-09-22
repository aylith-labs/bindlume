"""Omarchy-like usage presentation, scoped to Bindlume's own saved turns."""
from collections import defaultdict
from datetime import datetime, timedelta
from gi.repository import Gtk, Pango
from localization import text as tr


def count(value):
    return max(0, value) if isinstance(value, int) and not isinstance(value, bool) else 0


def compact(value):
    for size,suffix in ((10**9,'B'),(10**6,'M'),(10**3,'K')):
        if value>=size: return f'{value/size:.1f}'.rstrip('0').rstrip('.')+suffix
    return str(value)


def summarize(sessions, provider, today=None):
    today = today or datetime.now().astimezone().date()
    days = {(today-timedelta(days=i)).isoformat():0 for i in range(6,-1,-1)}
    models = defaultdict(int); undated = 0; total = 0
    for session in sessions:
        turns = session.get('turn_usage') or [session.get('usage_total') or session.get('usage',{})]
        for turn in turns:
            if turn.get('provider',session.get('provider')) != provider: continue
            amount = count(turn.get('input_tokens'))+count(turn.get('output_tokens'))
            total += amount
            models[turn.get('model') or tr('Model not reported')] += amount
            try: day = datetime.fromisoformat(turn.get('created_at','').replace('Z','+00:00')).astimezone().date().isoformat()
            except (ValueError,TypeError): undated += amount; continue
            if day in days: days[day] += amount
    return dict(days=days, models=dict(sorted(models.items(),key=lambda kv:kv[1],reverse=True)), total=total, undated=undated)


def relative_time(value, now=None):
    try:
        stamp=datetime.fromisoformat(value.replace('Z','+00:00')).astimezone()
        seconds=max(0,((now or datetime.now().astimezone())-stamp).total_seconds())
    except (ValueError,TypeError,AttributeError):return str(value or '—')
    if seconds<60:return tr('Just now')
    if seconds<3600:return tr('{count} min ago').format(count=int(seconds//60))
    if seconds<86400:return tr('{count} h ago').format(count=int(seconds//3600))
    return tr('{count} d ago').format(count=int(seconds//86400))


def token_details(session):
    usage=session.get('usage_total') or session.get('usage') or {}
    names=[('input_tokens','Input tokens'),('cached_input_tokens','Cached input tokens'),
           ('cache_write_input_tokens','Cache write tokens'),('output_tokens','Output tokens'),
           ('reasoning_output_tokens','Reasoning tokens')]
    return [(title,f'{count(usage[key]):,}') for key,title in names if key in usage and (count(usage[key]) or key in ('input_tokens','output_tokens'))]


def label(text, heading=False):
    widget = Gtk.Label(label=text,xalign=0,wrap=True,max_width_chars=42)
    widget.add_css_class('heading' if heading else 'dim-label')
    return widget


def bar(body, title, amount, ratio):
    row = Gtk.Box(spacing=12)
    name = Gtk.Label(label=title,xalign=0,width_chars=8,max_width_chars=18,ellipsize=Pango.EllipsizeMode.END)
    name._translation_skip = True
    row.append(name)
    progress = Gtk.ProgressBar(fraction=max(0,min(1,ratio)),hexpand=True,valign=Gtk.Align.CENTER)
    progress.add_css_class('usage-meter');row.append(progress)
    row.append(Gtk.Label(label=amount,xalign=1,width_chars=9))
    body.append(row)


def provider_summary(provider, quota):
    from chat import PROVIDERS
    parts=[PROVIDERS.get(provider,provider)]
    if quota.get('tier'): parts.append(quota['tier'].upper())
    for window in quota.get('windows',[]):
        parts.append(tr('{name}: {percent}% left').format(name=tr(window['name']),percent=f"{window['remaining_percent']:g}"))
    if not quota.get('windows'):parts.append(tr('Quota unavailable'))
    return ' · '.join(parts)


def populate(body, providers, quotas, sessions, enabled):
    from chat import PROVIDERS
    for provider in providers:
        data = quotas.get(provider,{})
        title = PROVIDERS.get(provider,provider)
        if data.get('tier'): title += ' · '+data['tier'].upper()
        body.append(label(title,True))
        body.append(label(tr('Account limits')))
        for item in data.get('windows',[]):
            used = 100-item['remaining_percent']
            bar(body,tr(item['name']),tr('{percent}% used').format(percent=f'{used:g}'),used/100)
            if item.get('resets_at'):
                try:
                    reset=datetime.fromisoformat(item['resets_at'].replace('Z','+00:00')).astimezone()
                    body.append(label(tr('Resets {time}').format(time=reset.strftime('%a %H:%M'))))
                except (ValueError,TypeError): pass
        if not data.get('windows'): body.append(label(tr('Quota unavailable')))
        if enabled:
            stats=summarize(sessions,provider)
            body.append(Gtk.Separator())
            body.append(label(tr('Bindlume tokens by day'),True))
            peak=max(stats['days'].values(),default=0) or 1
            today=datetime.now().astimezone().date().isoformat()
            for day,value in stats['days'].items():
                title=tr('Today') if day==today else tr(datetime.fromisoformat(day).strftime('%a'))
                bar(body,title,compact(value),value/peak)
            body.append(label(tr('Bindlume tokens by model'),True))
            peak=max(stats['models'].values(),default=0) or 1
            for model,value in stats['models'].items():
                if value: bar(body,model,compact(value),value/peak)
            if not stats['total']: body.append(label(tr('No reported Bindlume usage yet.')))
            if stats['undated']: body.append(label(tr('Older tokens without a date: {count}').format(count=compact(stats['undated']))))
            body.append(label(tr('Saved Bindlume conversations only. Input includes cached tokens; cached tokens are not counted twice.')))
        else:
            body.append(label(tr('Enable token usage in AI companion settings to show Bindlume charts.')))
        body.append(Gtk.Separator())
