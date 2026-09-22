"""Optional full-height chat sidebar with keyboard-first conversation history."""
import threading
from gi.repository import Gtk, Gdk, Gio, GLib, Pango
from agent_quota import read_quotas, choose_agent
from chat import SessionStore, AgentRun, PROVIDERS, available_agents
from shortcut_data import action_tooltip
import localization
from localization import text as tr


class ChatPanel(Gtk.Box):
    def __init__(self, app, root):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                         margin_top=12, margin_bottom=12, margin_start=14, margin_end=12,
                         width_request=340, hexpand=True, vexpand=True)
        self.app, self.store = app, SessionStore(root/'chats')
        self.session = None
        self.run = None
        self.choosing = False
        self.pending = []
        self.selection_ticket = 0
        self.quotas = {}
        self.history_window = None
        self.add_css_class('chat-panel')
        header = Gtk.Box(spacing=6)
        self.title = Gtk.Label(label='Ask an agent', xalign=0, hexpand=True,
                               ellipsize=Pango.EllipsizeMode.END, width_chars=8)
        self.title.add_css_class('heading')
        self.title.set_has_tooltip(True)
        def title_tooltip(widget, _x, _y, _keyboard, tooltip):
            if not widget.get_layout().is_ellipsized(): return False
            tooltip.set_text(widget.get_text())
            return True
        self.title.connect('query-tooltip', title_tooltip)
        header.append(self.title)
        for icon, hint, callback in [('list-add-symbolic','New conversation',self.new),
                                     ('document-open-recent-symbolic','Conversation history (Ctrl+Shift+H)',self.history),
                                     ('emblem-system-symbolic','AI companion settings',lambda *_: __import__('companion').show(app,self)),
                                     ('window-close-symbolic','Close chat (Esc)',lambda *_: app.show_chat(False))]:
            button = Gtk.Button(icon_name=icon)
            button.add_css_class('flat')
            action_tooltip(button, hint)
            button.connect('clicked', callback)
            header.append(button)
        self.append(header)
        controls = Gtk.Box(spacing=8)
        self.agents = available_agents(self.app.preferences)
        self.agent_choices = ['auto'] + self.agents
        self.agent = Gtk.DropDown.new_from_strings(['Automatic'] + [PROVIDERS[key] for key in self.agents])
        preferred = app.preferences.get('agent_provider', 'auto')
        self.agent.set_selected(self.agent_choices.index(preferred) if preferred in self.agent_choices else 0)
        self.agent.set_hexpand(True)
        self.agent.connect('notify::selected', self.agent_changed)
        controls.append(self.agent)
        usage = Gtk.MenuButton(label='Usage')
        usage_popover = Gtk.Popover()
        usage.set_popover(usage_popover)
        self.usage_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        usage_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
            max_content_height=420, propagate_natural_height=True, min_content_width=300, max_content_width=420)
        self.usage_scroll = usage_scroll
        self.usage_popover = usage_popover
        usage_scroll.set_child(self.usage_body); usage_popover.set_child(usage_scroll)
        usage_popover.connect('notify::visible', lambda w,*_: self.quota_ready(getattr(self,'quotas',{})) if w.get_visible() else None)
        controls.append(usage)
        self.copy_menu = Gio.Menu()
        self.copy_button = Gtk.MenuButton(label='Copy', menu_model=self.copy_menu)
        controls.append(self.copy_button)
        group = Gio.SimpleActionGroup()
        for key in ('transcript','id','path','agent-id','resume'):
            action = Gio.SimpleAction.new(key, None)
            action.connect('activate', lambda _,value,kind=key: self.copy(kind))
            group.add_action(action)
        self.insert_action_group('chat-copy', group)
        self.append(controls)
        self.model_label = Gtk.Label(xalign=0, wrap=True)
        self.model_label.add_css_class('dim-label')
        self.append(self.model_label)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.messages = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.scroll.set_child(self.messages)
        self.append(self.scroll)
        self.status = Gtk.Label(xalign=0, wrap=True)
        self.status.add_css_class('dim-label')
        self.append(self.status)
        self.activity = Gtk.Box(spacing=8)
        self.spinner = Gtk.Spinner()
        self.activity.append(self.spinner)
        self.activity_label = Gtk.Label(label='Working…', xalign=0, hexpand=True)
        self.activity.append(self.activity_label)
        self.activity.set_visible(False)
        self.append(self.activity)
        self.queue_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.append(self.queue_box)
        composer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.input = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=10, bottom_margin=10,
                                  left_margin=10, right_margin=10, height_request=76, accepts_tab=False)
        self.input.get_buffer().set_enable_undo(True)
        self.input.set_tooltip_text('Ask about shortcuts and settings. Enter sends; Shift+Enter adds a line.')
        field = Gtk.ScrolledWindow(min_content_height=76, max_content_height=150, propagate_natural_height=True,
                                   hscrollbar_policy=Gtk.PolicyType.NEVER)
        field.add_css_class('chat-input')
        field.set_child(self.input)
        self.input_overlay = Gtk.Overlay()
        self.input_overlay.set_child(field)
        self.input_placeholder = Gtk.Label(label=tr('Ask about shortcuts or change the app…'),
            xalign=0, wrap=True, can_target=False, halign=Gtk.Align.START, valign=Gtk.Align.START,
            margin_start=11, margin_top=11, margin_end=11)
        self.input_placeholder.add_css_class('dim-label')
        self.input_overlay.add_overlay(self.input_placeholder)
        composer.append(self.input_overlay)
        buttons = Gtk.Box(spacing=8)
        label = Gtk.Label(label='Enter to send · Shift+Enter for a new line', xalign=0, hexpand=True, wrap=True)
        label.add_css_class('dim-label')
        composer.append(label)
        buttons.set_halign(Gtk.Align.END)
        self.stop_button = Gtk.Button(icon_name='media-playback-stop-symbolic', tooltip_text='Stop response', visible=False)
        self.stop_button.connect('clicked', self.stop)
        buttons.append(self.stop_button)
        self.send_button = Gtk.Button(label='Send')
        self.send_button.add_css_class('chat-send')
        self.send_button.connect('clicked', self.send)
        self.input.get_buffer().connect('changed', self.input_changed)
        buttons.append(self.send_button)
        composer.append(buttons)
        self.append(composer)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.input_key)
        self.input.add_controller(keys)
        self.render()
        self.input_changed()
        self.refresh_quota()

    def input_changed(self, *_):
        buffer = self.input.get_buffer()
        value = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)
        self.input_placeholder.set_visible(not value)
        self.send_button.set_sensitive(bool(value.strip()) and bool(self.agents) and self.input.get_sensitive())

    def agent_changed(self, *_):
        if (not self.agents or self.run or self.choosing or getattr(self, '_updating_agents', False)
                or self.agent.get_selected() >= len(self.agent_choices)):return
        selection=self.agent_choices[self.agent.get_selected()]
        if self.session:
            self.session['selection']=selection
            self.store.save(self.session)
        else:
            self.app.preferences['agent_provider']=selection
            self.app.save_ui_state()

    def input_key(self, _, key, code, state):
        modifiers=state & Gtk.accelerator_get_default_mod_mask()
        if modifiers == Gdk.ModifierType.CONTROL_MASK and key in (Gdk.KEY_u, Gdk.KEY_k):
            buffer=self.input.get_buffer()
            buffer.begin_user_action()
            try:
                if buffer.get_has_selection():buffer.delete_selection(True,True)
                else:
                    cursor=buffer.get_iter_at_mark(buffer.get_insert())
                    boundary=cursor.copy()
                    if key == Gdk.KEY_u:
                        boundary.set_line_offset(0)
                        buffer.delete(boundary,cursor)
                    else:
                        if boundary.ends_line():boundary.forward_char()
                        else:boundary.forward_to_line_end()
                        buffer.delete(cursor,boundary)
            finally:buffer.end_user_action()
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and not state & Gdk.ModifierType.SHIFT_MASK:
            self.send()
            return True
        return False

    def clear(self, box):
        while child := box.get_first_child(): box.remove(child)

    def bubble(self, role, text):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        box.add_css_class('chat-message')
        box.add_css_class('chat-'+role)
        if role == 'user': box.set_margin_start(24)
        title = Gtk.Label(label={'user':'You','assistant':PROVIDERS.get(self.session['provider'],'Agent') if self.session else 'Agent','notice':'Notice'}[role], xalign=0)
        title.add_css_class('heading')
        box.append(title)
        from rich_content import MarkdownView
        label = MarkdownView(text, snippets=self.app.preferences.get('chat_snippets',False), vignette=self.app.preferences.get('chat_vignette',True)) if role == 'assistant' else Gtk.Label(label=text, xalign=0, selectable=True, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=45)
        label._translation_skip = True
        label.set_hexpand(True)
        box.append(label)
        self.messages.append(box)
        return label

    def render(self):
        self.clear(self.messages)
        from companion import runtime
        provider = self.session['provider'] if self.session else self.agent_choices[self.agent.get_selected()]
        data = runtime(provider, self.session)
        self.model_label.set_text(tr('Model: {model}' if data['reported'] else 'Configured model: {model}').format(model=data['model']))
        self.model_label.set_visible(provider != 'auto')
        self.title._translation_skip = self.session is not None
        self.title.set_text(self.session['title'] if self.session else 'Ask an agent')
        self.agent.set_sensitive(bool(self.agents) and not (self.run or self.choosing))
        self.copy_button.set_visible(self.session is not None)
        self.copy_menu.remove_all()
        if self.session:
            for label, key in [('Conversation content','transcript'),('Session ID','id'),('Session file path','path'),
                               ('Agent session ID','agent-id'),('Continue in a terminal','resume')]:
                if key in self.store.copy_values(self.session): self.copy_menu.append(tr(label), 'chat-copy.'+key)
            for message in self.session['messages']: self.bubble(message['role'], message['content'])
            if self.app.preferences.get('chat_token_usage'):
                from companion import tokens
                usage = self.session.get('usage_total', self.session.get('usage',{}))
                note = Gtk.Label(label=(tr('Session tokens: {count}').format(count=f'{tokens(self.session):,}') if usage else tr('Token usage unavailable')), xalign=0)
                note.add_css_class('dim-label'); self.messages.append(note)
        else:
            past = self.store.list()
            if past:
                label = Gtk.Label(label='Continue a conversation', xalign=0)
                label.add_css_class('heading')
                self.messages.append(label)
                for session in past[:8]: self.messages.append(self.history_row(session))
            else:
                self.messages.append(Gtk.Label(label='What would you like to do?', xalign=0, wrap=True))
                for text in ('Find a shortcut for taking a screenshot', 'Help me remember useful shortcuts',
                             'Show me which features are enabled', 'Make the app simpler'):
                    button = Gtk.Button(label=text, halign=Gtk.Align.FILL)
                    button.get_child().set_wrap(True)
                    button.get_child().set_max_width_chars(34)
                    button.get_child().set_xalign(0)
                    button.add_css_class('suggestion')
                    button.connect('clicked', lambda _,prompt=text: self.suggest(tr(prompt)))
                    self.messages.append(button)
        if not self.agents:
            self.status.set_text(tr('Choose an installed agent or configure a connection in AI companion settings.'))
        elif not self.run:
            self.status.set_text(tr('Uses the configured model connection.' if provider.startswith('api_') else 'Uses your installed agent and its signed-in account.') if not self.session else '')
        available = bool(self.agents) and (not self.session or self.session['provider'] in self.agents)
        if not available and self.session:
            self.status.set_text(PROVIDERS[self.session['provider']]+' is unavailable. Install it to continue, or copy this conversation to another agent.')
        self.input.set_sensitive(available)
        self.send_button.set_sensitive(available)
        localization.translate_tree(self)
        self.update_busy()

    def suggest(self, prompt):
        self.input.get_buffer().set_text(prompt)
        self.input.grab_focus()

    def new(self, *_):
        if self.run or self.choosing:
            self.status.set_text('Stop the current response before starting a new conversation.')
            return
        self.session = None
        self.pending = []
        preferred = self.app.preferences.get('agent_provider', 'auto')
        self.agents = available_agents(self.app.preferences)
        self.agent_choices = ['auto'] + self.agents
        self._updating_agents = True
        self.agent.set_model(Gtk.StringList.new(['Automatic'] + [PROVIDERS[key] for key in self.agents]))
        self.agent.set_selected(self.agent_choices.index(preferred) if preferred in self.agent_choices else 0)
        self._updating_agents = False
        self.input.get_buffer().set_text('')
        self.render()
        self.input.grab_focus()

    def open(self, identity):
        if self.run or self.choosing:
            self.status.set_text('Stop the current response before switching conversations.')
            return
        self.session = self.store.load(identity)
        self.pending = list(self.session.get('queued_messages', []))
        if self.session['provider'] in self.agents:
            self.agent.set_selected(self.agent_choices.index(self.session.get('selection', self.session['provider'])))
        else: self.agent.set_selected(Gtk.INVALID_LIST_POSITION)
        self.input.get_buffer().set_text('')
        self.render()
        if self.history_window: self.history_window.close()
        self.input.grab_focus()
        self.to_bottom()

    def metadata(self, session):
        from usage_view import relative_time, token_details
        lines = [('Agent', PROVIDERS[session['provider']]), ('Started', relative_time(session['created_at'])),
                 ('Updated', relative_time(session['updated_at'])), ('Messages', session.get('message_count',0)),
                 ('Status',session['status']), ('Session ID',session['id'])]
        if session.get('model'): lines.append(('Model',session['model']))
        if session.get('provider_session_id'): lines.append(('Agent session ID',session['provider_session_id']))
        lines.extend(token_details(session))
        return lines

    def history_row(self, session):
        row = Gtk.Box(spacing=4)
        button = Gtk.Button(hexpand=True)
        label = Gtk.Label(label=session['title'], xalign=0, ellipsize=Pango.EllipsizeMode.END, width_chars=1)
        label._translation_skip = True
        button.set_child(label)
        button.add_css_class('flat')
        button.connect('clicked', lambda *_: self.open(session['id']))
        button.set_has_tooltip(True)
        def tooltip(_widget,x,y,keyboard,tip):
            grid = Gtk.Grid(column_spacing=16,row_spacing=8,margin_top=12,margin_bottom=12,margin_start=12,margin_end=12)
            for index,(title,value) in enumerate(self.metadata(session)):
                name = Gtk.Label(label=tr(title),xalign=0,valign=Gtk.Align.START)
                name.add_css_class('dim-label')
                grid.attach(name,0,index,1,1)
                grid.attach(Gtk.Label(label=str(value),xalign=0,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,max_width_chars=36),1,index,1,1)
            tip.set_custom(grid)
            return True
        button.connect('query-tooltip', tooltip)
        row.append(button)
        rename = Gtk.Button(icon_name='document-edit-symbolic')
        rename.add_css_class('flat')
        rename.set_tooltip_text('Rename conversation')
        rename.connect('clicked', lambda *_: self.rename(session, row, button, label, rename))
        row.append(rename)
        return row

    def rename(self, session, row, button, label, rename):
        entry = Gtk.Entry(text=session['title'], max_length=160, hexpand=True, width_chars=1)
        entry._translation_skip = True
        apply_button = Gtk.Button(icon_name='object-select-symbolic')
        cancel_button = Gtk.Button(icon_name='window-close-symbolic')
        for control, title in ((apply_button, 'Apply'), (cancel_button, 'Cancel')):
            control.add_css_class('flat')
            control.set_tooltip_text(tr(title))
        button.set_visible(False)
        rename.set_visible(False)
        row.prepend(entry)
        row.append(apply_button)
        row.append(cancel_button)
        row.rename_entry = entry
        row.rename_apply = apply_button
        row.rename_cancel = cancel_button

        def finish(save):
            title = entry.get_text().strip()
            if save and not title:
                return
            if save:
                self.store.rename(session, title)
                label.set_text(session['title'])
                if self.session and self.session['id'] == session['id']:
                    self.session['title'] = session['title']
                    self.session['title_edited'] = True
                    self.title.set_text(session['title'])
            button.set_visible(True)
            rename.set_visible(True)
            for widget in (entry, apply_button, cancel_button):
                row.remove(widget)
            row.rename_entry = None
            rename.grab_focus()

        apply_button.connect('clicked', lambda *_: finish(True))
        cancel_button.connect('clicked', lambda *_: finish(False))
        entry.connect('activate', lambda *_: finish(True))
        entry.connect('changed', lambda *_: apply_button.set_sensitive(bool(entry.get_text().strip())))
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        def key_pressed(_controller, key, _code, _state):
            if key == Gdk.KEY_Escape:
                finish(False)
                return True
            return False
        keys.connect('key-pressed', key_pressed)
        entry.add_controller(keys)
        row.rename_keys = keys
        entry.grab_focus()
        entry.select_region(0, -1)

    def history(self, *_):
        if self.history_window:
            self.history_window.present()
            self.history_window.search.grab_focus()
            return
        window = Gtk.Window(application=self.app, transient_for=self.app.window, modal=True,
                            title='Conversation history', default_width=480, default_height=520)
        self.history_window = window
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10,margin_top=18,margin_bottom=18,margin_start=18,margin_end=18)
        header = Gtk.Box(spacing=8)
        header.append(Gtk.Label(label='Conversations',xalign=0,hexpand=True))
        close = Gtk.Button(icon_name='window-close-symbolic')
        close.connect('clicked',lambda *_:window.close())
        header.append(close)
        body.append(header)
        search = Gtk.SearchEntry(placeholder_text='Search conversations…')
        window.search = search
        body.append(search)
        rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
        scroll = Gtk.ScrolledWindow(vexpand=True,hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(rows)
        body.append(scroll)
        def fill(*_):
            self.clear(rows)
            found = [session for session in self.store.list() if search.get_text().casefold() in session['title'].casefold()]
            window.matches = found
            for session in found: rows.append(self.history_row(session))
            if not found: rows.append(Gtk.Label(label='No conversations found.' if search.get_text() else 'Your conversations will appear here.',wrap=True))
        window.fill = fill
        search.connect('search-changed',fill)
        search.connect('activate',lambda *_:self.open(window.matches[0]['id']) if window.matches else None)
        window.set_child(body)
        window.connect('close-request',lambda *_:setattr(self,'history_window',None) or False)
        fill()
        window.set_focus(search)
        window.present()
        search.grab_focus()

    def copy(self, kind):
        if self.session:
            self.get_clipboard().set(self.store.copy_values(self.session)[kind])
            self.status.set_text('Copied.')

    def to_bottom(self):
        def scroll():
            adjustment = self.scroll.get_vadjustment()
            adjustment.set_value(max(0,adjustment.get_upper()-adjustment.get_page_size()))
            return False
        GLib.idle_add(scroll)

    def refresh_quota(self, force=False):
        def worker():
            try: quotas = read_quotas(self.agents, self.store.root.parent, force)
            except Exception: quotas = {}
            GLib.idle_add(self.quota_ready, quotas)
        threading.Thread(target=worker, daemon=True).start()

    def quota_ready(self, quotas):
        self.quotas = quotas
        self.clear(self.usage_body)
        from usage_view import populate, provider_summary
        providers = self.agents
        selected = getattr(self, 'usage_provider', None)
        current = self.session.get('provider') if self.session else self.agent_choices[self.agent.get_selected()]
        if selected not in providers: selected = current if current in providers else next(iter(providers), None)
        self.usage_provider = selected
        if providers:
            picker = Gtk.DropDown.new_from_strings([provider_summary(p, quotas.get(p, {})) for p in providers])
            picker.set_selected(providers.index(selected))
            picker.set_tooltip_text(tr('Choose a harness to inspect usage'))
            # Wrap the option summaries rather than imposing their full natural width.
            def factory():
                result = Gtk.SignalListItemFactory()
                def setup(_factory, item):
                    item.set_child(Gtk.Label(xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, max_width_chars=38))
                def bind(_factory, item):
                    item.get_child().set_text(item.get_item().get_string())
                    item.get_child()._translation_skip = True
                result.connect('setup',setup);result.connect('bind',bind)
                return result
            picker.set_factory(factory());picker.set_list_factory(factory())
            self.usage_picker = picker
            self.usage_body.append(picker)
            details = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.usage_body.append(details)
            def show_selected(*_):
                self.usage_provider = providers[picker.get_selected()]
                self.clear(details)
                populate(details, [self.usage_provider], quotas, self.store.list(), self.app.preferences.get('chat_token_usage',False))
                import localization
                localization.translate_tree(details)
            picker.connect('notify::selected',show_selected)
            show_selected()
        else:
            self.usage_body.append(Gtk.Label(label=tr('Quota unavailable')))
        surface = self.app.window.get_surface()
        if surface:
            monitor = self.app.window.get_display().get_monitor_at_surface(surface)
            if monitor:self.usage_scroll.set_max_content_height(max(100,min(420,monitor.get_geometry().height-120)))
        refresh = Gtk.Button(label='Refresh usage')
        refresh.connect('clicked',lambda *_:self.refresh_quota(True))
        self.usage_body.append(refresh)
        import localization
        localization.translate_tree(self.usage_body)
        return False

    def stop(self, *_):
        if self.choosing:
            self.selection_ticket += 1
            self.choosing = False
            self.send_button.set_label('Send')
            self.input.set_sensitive(True)
            self.status.set_text('Stopped.')
            self.update_busy()
            return
        if self.run:
            self.run.stop()
            self.status.set_text('Stopping…')
            return

    def update_busy(self):
        busy = bool(self.run or self.choosing)
        self.agent.set_sensitive(bool(self.agents) and not busy)
        self.activity.set_visible(busy)
        self.spinner.set_spinning(busy)
        self.stop_button.set_visible(busy)
        self.send_button.set_label(tr('Queue message' if busy else 'Send'))
        self.input_changed()
        self.clear(self.queue_box)
        for index, prompt in enumerate(self.pending):
            row = Gtk.Box(spacing=6)
            label = Gtk.Label(label=prompt, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, max_width_chars=35)
            label._translation_skip = True
            row.append(label)
            remove = Gtk.Button(icon_name='window-close-symbolic', tooltip_text=tr('Remove queued message'))
            remove.add_css_class('flat')
            remove.connect('clicked', lambda _, i=index: self.remove_queued(i))
            row.append(remove)
            row.add_css_class('chat-queued')
            self.queue_box.append(row)
        if self.pending and not busy:
            resume = Gtk.Button(label=tr('Send queued messages'))
            resume.connect('clicked', lambda *_: self.send_next())
            self.queue_box.append(resume)

    def save_queue(self):
        if self.session:
            self.session['queued_messages'] = list(self.pending)
            self.store.save(self.session)

    def remove_queued(self, index):
        self.pending.pop(index)
        self.save_queue()
        self.update_busy()

    def send_next(self):
        if not self.pending or self.run or self.choosing: return
        prompt = self.pending.pop(0)
        self.save_queue()
        self.dispatch(prompt)

    def send(self, *_):
        buffer = self.input.get_buffer()
        prompt = buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True).strip()
        if not prompt or not self.agents: return
        buffer.set_text('')
        if self.run or self.choosing or self.pending:
            self.pending.append(prompt)
            self.save_queue()
            self.update_busy()
            if not self.run and not self.choosing: self.send_next()
            return
        self.dispatch(prompt)

    def dispatch(self, prompt):
        selection = self.session.get('selection',self.session['provider']) if self.session else self.agent_choices[self.agent.get_selected()]
        if selection != 'auto':
            self.begin_send(prompt,selection,selection)
            return
        self.choosing = True
        self.selection_ticket += 1
        ticket = self.selection_ticket
        self.update_busy()
        self.activity_label.set_text(tr('Checking available quota…'))
        def worker():
            try:
                quotas = getattr(self, 'quotas', {})
                if not quotas:
                    from agent_quota import cached_quotas
                    quotas = cached_quotas(self.store.root.parent)
                provider, reason = choose_agent(self.agents,quotas)
                GLib.idle_add(selected,provider,quotas,'')
            except Exception as error: GLib.idle_add(selected,None,{},str(error))
        def selected(provider,quotas,error):
            if ticket != self.selection_ticket: return False
            self.choosing = False
            self.update_busy()
            self.quota_ready(quotas)
            if error:
                self.pending.insert(0, prompt)
                self.save_queue()
                self.update_busy()
                self.status.set_text(error)
            elif self.app.feature_enabled('agent'): self.begin_send(prompt,provider,'auto')
            return False
        threading.Thread(target=worker,daemon=True).start()

    def begin_send(self, prompt, provider, selection):
        if not self.session:
            self.session = self.store.create(provider,prompt)
            self.session['selection'] = selection
        elif self.session['provider'] != provider:
            self.session.setdefault('agent_history',[]).append(dict(provider=self.session['provider'],
                session_id=self.session.get('provider_session_id')))
            self.session['provider'] = provider
            self.session['provider_session_id'] = None
            # A fresh provider receives the portable transcript on its first turn.
        self.session['selection'] = selection
        self.save_queue()
        self.render()
        self.bubble('user',prompt)
        self.reply = self.bubble('assistant','')
        self.agent.set_sensitive(False)
        self.status.set_text('')
        self.activity_label.set_text(tr('Working…'))
        self.session['companion_preferences'] = dict(self.app.preferences)
        self.run = AgentRun(self.store,self.session,lambda kind,value:GLib.idle_add(self.event,kind,value))
        self.update_busy()
        threading.Thread(target=self.run.run,args=(prompt,),daemon=True).start()
        self.to_bottom()

    def event(self, kind, value):
        if kind == 'reply':
            self._pending_reply = value
            if not getattr(self, '_reply_timer', None):
                self._reply_timer = GLib.timeout_add(50, self.flush_reply)
        elif kind == 'activity': self.activity_label.set_text(tr(value))
        elif kind == 'done':
            if getattr(self, '_reply_timer', None):
                GLib.source_remove(self._reply_timer)
                self._reply_timer = None
            self._pending_reply = None
            self.session = value
            self.run = None
            self.send_button.set_label('Send')
            self.render()
            self.to_bottom()
            if self.get_mapped(): self.input.grab_focus()
            if self.session.get('status') == 'ready': self.send_next()
        return False

    def flush_reply(self):
        self._reply_timer = None
        value = getattr(self, '_pending_reply', None)
        self._pending_reply = None
        if value is not None and self.run:
            self.reply.set_text(value)
            self.to_bottom()
        return False
