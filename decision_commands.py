"""Explicit commands for the decision companion; all state goes through control."""
import json
import re
from system_one import tr

HELP = 'I can find shortcuts, bookmark or hide them, toggle features, change settings and filters, select shortcut sets, and open app panels. Try “show themes shortcut” or “enable filters”.'
AMBIGUOUS = 'Several shortcuts match. Use an exact shortcut name.'
EMPTY = 'No matching shortcut was found.'

# These are parser aliases, not UI text or persistent identities.
FEATURES = {'filters':'layouts', 'layouts':'layouts', 'bookmarks':'bookmarks', 'favorites':'bookmarks',
            'hidden shortcuts':'hidden', 'keyboard explorer':'keyboard', 'mouse gestures':'inputs',
            'controllers':'inputs', 'shortcut editor':'manage', 'keyboard guide':'guide', 'guide':'guide',
            'target window':'target', 'live filter':'live', 'appearance':'appearance', 'chat':'agent',
            'agent chat':'agent', 'recent searches':'history', 'search history':'history', 'all features':'all'}
PANELS = {'activity log':'activity', 'operations':'activity','settings':'settings', 'preferences':'settings', 'features':'features', 'shortcut editor':'shortcuts',
          'shortcut sets':'sets', 'sources':'sets', 'about':'about', 'details':'details', 'guide':'guide',
          'inputs':'inputs', 'chat':'chat'}
BOOLEAN_SETTINGS = {'compact mode':'compact', 'compact layout':'compact', 'compact view':'compact',
    'app icons':'app_icons', 'application icons':'app_icons', 'action icons':'action_icons',
    'tooltips':'shortcut_tooltips', 'shortcut tooltips':'shortcut_tooltips', 'system typography':'system_typography',
    'keyboard snippets':'chat_snippets', 'keyboard illustrations':'chat_snippets', 'vignette':'chat_vignette',
    'guide side preview':'guide_preview_side', 'remember search':'remember_search',
    'persistent memory':'chat_memory_enabled', 'token tracking':'chat_token_usage', 'token usage':'chat_token_usage'}


def clean(prompt):
    value = ' '.join(prompt.casefold().strip().rstrip('.!').split())
    value = re.sub(r'^(?:please |can you |could you |would you )+', '', value)
    return re.sub(r',? please$', '', value).strip()


def plan(prompt):
    """Return one complete, bounded operation; questions/negations never match."""
    text = clean(prompt)
    if re.search(r"\b(?:not|don't|dont|never|without)\b", text): return None
    if text in ('undo','undo last operation','undo the last operation','undo last change','undo that','redo','redo last operation','redo the last operation','redo that'):
        return {'operation':'activity','arguments':{'action':'redo' if text.startswith('redo') else 'undo'}}
    if re.fullmatch(r'(?:show|what is|explain)(?: me)? (?:the )?(?:activity log |log )?retention(?: policy)?',text):
        return {'operation':'activity','arguments':{'action':'policy'}}
    if re.search(r'\b(?:activity log|log|operations)\b',text) and re.search(r'\b(?:store|keep|retain|make|set)\b',text) and re.search(r'\b(?:indefinitely|forever|unlimited|uncap)\b',text):
        return {'operation':'activity','arguments':{'action':'retention','max_operations':0,'max_age_days':0}}
    retention=re.fullmatch(r'(?:keep|store|retain)(?: the)?(?: last)? (\d+) operations(?: in (?:the )?(?:activity )?log)?',text)
    if not retention:retention=re.fullmatch(r'(?:set|change)(?: the)?(?: activity)? log (?:limit|capacity)(?: to)? (\d+)(?: operations)?',text)
    if retention:return {'operation':'activity','arguments':{'action':'retention','max_operations':int(retention[1])}}
    age=re.fullmatch(r'(?:keep|store|retain)(?: activity log| operations| activity)? for (\d+) days',text)
    if age:return {'operation':'activity','arguments':{'action':'retention','max_age_days':int(age[1])}}
    if re.search(r'\boperations\b',text) and re.match(r'^(?:show|list|get)\b',text):
        count=re.search(r'last (\d+|ten|twenty|fifty|hundred)',text)
        words={'ten':10,'twenty':20,'fifty':50,'hundred':100}
        value=count[1] if count else '10'
        args={'limit':words[value] if value in words else int(value)}
        date=re.search(r'\b(yesterday|today|\d{4}-\d{2}-\d{2})\b',text)
        if date:args['date']=date[1]
        return {'operation':'activity','arguments':args}
    toggle = re.fullmatch(r'(enable|disable|turn on|turn off|show|hide) (.+)', text)
    if toggle:
        verb, target = toggle.groups();enabled = verb in ('enable', 'turn on', 'show')
        if target == 'filters' and verb in ('show', 'hide', 'enable', 'turn on'):
            return {'operation':'view','arguments':{'show_filters':enabled}}
        if target in FEATURES and verb not in ('show', 'hide'):
            return {'operation':'features','arguments':{'name':FEATURES[target],'enabled':enabled}}
        if target in BOOLEAN_SETTINGS and verb not in ('show', 'hide'):
            return {'operation':'settings','arguments':{'key':BOOLEAN_SETTINGS[target],'value':enabled}}
    opening = re.fullmatch(r'(?:open|show) (.+)', text)
    if opening and opening[1] in PANELS:
        return {'operation':'open','arguments':{'surface':PANELS[opening[1]]}}
    reading = re.fullmatch(r'(?:list|show|what are|which are) (?:the )?(?:available |enabled )?(features|settings|sources|shortcut sets)', text)
    if reading:
        return {'operation':{'shortcut sets':'sources'}.get(reading[1],reading[1])}
    theme = re.fullmatch(r'(?:set|switch|change)(?: the)?(?: app)?(?: color)? theme(?: to)? (dark|light|system)(?: mode)?',text)
    if not theme: theme = re.fullmatch(r'(?:use|switch to|enable) (dark|light|system)(?: theme| mode)',text)
    if theme:return {'operation':'settings','arguments':{'key':'theme','value':theme[1]}}
    font = re.fullmatch(r'(?:set|change)(?: the)? (?:font|text|label) size(?: to)? (\d+)', text)
    if font and 9 <= int(font[1]) <= 28:
        return {'operation':'settings','arguments':{'key':'font_size','value':int(font[1])}}
    if text in ('clear search','clear the search','reset search'):
        return {'operation':'view','arguments':{'search':''}}
    view = {'show hidden shortcuts':{'visibility':'hidden'}, 'show visible shortcuts':{'visibility':'visible'},
            'show all shortcuts':{'visibility':'all','favorites_only':False,'search':''},
            'show bookmarks':{'favorites_only':True}, 'show favorites':{'favorites_only':True},
            'show keyboard':{'layout':'keyboard'}, 'show keyboard layout':{'layout':'keyboard'},
            'show list':{'layout':'list'}, 'use list layout':{'layout':'list'},
            'use keyboard layout':{'layout':'keyboard'}, 'ungroup shortcuts':{'flat_list':True},
            'group shortcuts':{'flat_list':False}}
    if text in view:return {'operation':'view','arguments':view[text]}
    modifiers = re.fullmatch(r'(?:filter by|show shortcuts with) ((?:(?:super|win|ctrl|control|alt|shift)[ +]*)+)', text)
    if modifiers:
        values = [{'win':'SUPER','control':'CTRL'}.get(v,v.upper()) for v in re.findall(r'super|win|ctrl|control|alt|shift',modifiers[1])]
        return {'operation':'view','arguments':{'modifiers':list(dict.fromkeys(values))}}
    return None


def keyboard_requested(prompt):
    return bool(re.search(r'\b(?:on (?:the |a )?keyboard|keyboard (?:preview|diagram)|illustrate|visuali[sz]e)\b', clean(prompt)))


def shortcut_terms(prompt):
    words = re.findall(r'[\w]+', clean(prompt))
    stop = set('show find search me the a an for please shortcut shortcuts key keys keyboard hotkey hotkeys binding bindings what which is are how do i can to my bookmark favorite favourite remember hide unhide remove from bookmarks favorites on in using with preview diagram illustrate display draw visualize visually'.split())
    synonyms = {'launch':'open','start':'open','themes':'theme','terminal':'terminal'}
    return [synonyms.get(w, w[:-1] if len(w)>4 and w.endswith('s') else w) for w in words if w not in stop]


def lookup(prompt, request):
    rows = request({'operation':'search','arguments':{'query':''}}, start=False)
    terms = shortcut_terms(prompt)
    if not terms:return []
    ranked=[]
    for row in rows:
        title=row['title'].casefold()
        score=sum(1 for term in terms if term in title or term in row['keys'].casefold())
        if score: ranked.append((score,row))
    ranked.sort(key=lambda pair:-pair[0])
    return [row for score,row in ranked[:12] if score == ranked[0][0]]


def execute(prompt, request, cancelled):
    """None means let the typed settings model handle the remaining request."""
    if cancelled.is_set(): return []
    payload=plan(prompt)
    if payload:
        if cancelled.is_set():return []
        result=request(payload,start=False)
        # Keep large app snapshots out of the reply; report the confirmed changed value.
        if payload['operation']=='settings':
            key=payload['arguments']['key'];result={key:result[key]}
        elif payload['operation']=='view':
            result={k:v for k,v in result.items() if k!='results'}
        return [{'delta':tr('App tool finished')+'\n```json\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n```'}]
    text=clean(prompt)
    # A source is resolved from the running app, never invented by the model.
    source=re.fullmatch(r'(?:use|switch to|select) (.+) (?:source|shortcut set)',text)
    if source:
        sources=request({'operation':'sources'},start=False)
        matches=[r['name'] for r in sources if r['name'].casefold()==source[1]]
        if len(matches)==1 and not cancelled.is_set():
            result=request({'operation':'view','arguments':{'source':matches[0]}},start=False)
            return [{'delta':tr('App tool finished')+'\n```json\n'+json.dumps({k:v for k,v in result.items() if k!='results'},ensure_ascii=False,indent=2)+'\n```'}]
        return [{'delta':tr(HELP)}]
    mark=re.fullmatch(r'(bookmark|favorite|favourite|remember|hide|unhide|unbookmark) (.+?)(?: shortcut)?',text)
    searching=bool(re.match(r'^(?:show|find|search|what|which|how|where)\b',text) and re.search(r'\b(?:shortcuts?|hotkeys?|bindings?)\b',text))
    if mark and mark[1] == 'remember' and 'shortcut' not in text: mark = None
    if mark or searching:
        rows=lookup(mark[2] if mark else prompt,request)
        if cancelled.is_set():return []
        if mark:
            target=mark[2].strip('"\'')
            exact=[r for r in rows if r['title'].casefold()==target]
            matches=exact or rows
            if len(matches)==1:
                row=matches[0];verb=mark[1]
                result=request({'operation':'hide' if verb in ('hide','unhide') else 'bookmark',
                                'arguments':{'id':row['id'],'enabled':verb not in ('unhide','unbookmark')}},start=False)
                return [{'delta':tr('App tool finished')+'\n```json\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n```'}]
            if len(matches)>1:
                return [{'delta':tr(AMBIGUOUS)+'\n```json\n'+json.dumps(matches,ensure_ascii=False,indent=2)+'\n```'}]
        if not rows:return [{'delta':tr(EMPTY), 'handoff': True}]
        parts=[]
        for row in rows:
            parts.append(f"- {row['title']}: `{row['keys']}` ({row['source']})")
            if keyboard_requested(prompt):
                # Alternatives are separate diagrams, never a combined chord.
                for binding in row['keys'].split(' / '):
                    keys=re.findall(r'[^ +]+', binding.upper())
                    parts.append('```keyboard\n'+json.dumps({'keys':keys,'label':row['title']},ensure_ascii=False)+'\n```')
        return [{'delta':'\n'.join(parts)}]
    return None
