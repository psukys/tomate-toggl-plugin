from __future__ import unicode_literals

import logging
import requests
import urllib
import json
import datetime
from locale import gettext as _

import gi

gi.require_version('Gtk', '3.0')

from gi.repository import Gtk

import tomate.plugin
from tomate.constant import State
from tomate.event import Events, on
from tomate.graph import graph
from tomate.utils import suppress_errors

logger = logging.getLogger(__name__)
CONFIG_SECTION_NAME = 'toggl_plugin'
CONFIG_API_OPTION_NAME = 'api_token'
COMMANDS = [
    CONFIG_API_OPTION_NAME
]


def parse_command(command):
    if command is not None:
        return command.strip()


class TogglAPI:
    api_url = 'https://www.toggl.com/api/v8'
    def __init__(self):
        self.token = None

    def check_token(self, token):
        r = requests.get(self.api_url + '/me', auth=requests.auth.HTTPBasicAuth(token, 'api_token'))
        if r.status_code == 200:
            data = json.loads(r.text)
            self.token = token
            return data['data']['email']

    def get_workspaces(self):
        if self.token:
            r = requests.get(self.api_url + '/workspaces', auth=requests.auth.HTTPBasicAuth(self.token, 'api_token'))
            if r.status_code == 200:
                data = json.loads(r.text)
                return data
            else:
                logger.error('Error while retrieving workspaces: {0}'.format(r.text()))
        else:
            logger.error('No token set')

    def get_entries(self, wid):
        # last week's entries
        if self.token:
            # Build timestamps
            def fake_utcoffset(d):
                # TODO: not be so lazy
                dot_idx = d.index('.')
                d = d[:dot_idx]
                d += '+00:00'
                return d

            end_date = urllib.parse.quote_plus(fake_utcoffset(datetime.datetime.today().isoformat()))
            start_date = datetime.datetime.today() - datetime.timedelta(days=7)
            start_date = urllib.parse.quote_plus(fake_utcoffset(start_date.isoformat()))
            r = requests.get(self.api_url + '/time_entries?start_date={0}&end_date={1}'.format(start_date, end_date), auth=requests.auth.HTTPBasicAuth(self.token, 'api_token'))
            # filter with workspace id given
            data = json.loads(r.text)
            logger.debug('Got {0} time entries'.format(len(data)))
            fil_entries = list(filter(lambda x: x['wid'] == wid, data))
            logger.debug('Filtered to {0} time entries that match WID'.format(len(fil_entries)))
            # filter unique names
            entries = []
            names = []
            for fe in fil_entries:
                if fe['description'] not in names:
                    names.append(fe['description'])
                    entries.append(fe)
            return entries
        else:
            logger.error('No token set')

togglAPI = TogglAPI()

class TogglGUI:
    def __init__(self):
        self.widget = Gtk.Dialog(
            _('Toggl'),
            None,
            modal=True,
            resizable=True,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            buttons=(Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY)
        )
        self.widget.connect('response', self.on_dialog_response)
        self.widget.set_size_request(350, 300)

        grid = Gtk.Grid(
            column_spacing=6,
            margin_bottom=12,
            margin_left=12,
            margin_right=12,
            margin_top=12,
            row_spacing=6,
        )
        workspace_cb = Gtk.ComboBox()
        workspace_store = Gtk.ListStore(str, int)
        workspace_renderer = Gtk.CellRendererText()
        workspace_cb.pack_start(workspace_renderer, 0)
        workspace_cb.add_attribute(workspace_renderer, 'text', 0)
        workspace_cb.connect('changed', self.on_ws_change)
        grid.attach(workspace_cb, 0, 0, 1, 1)

        self.entry_store = Gtk.ListStore(str)

        entry_cb = Gtk.ComboBox.new_with_model_and_entry(self.entry_store)
        entry_cb.set_entry_text_column(0)
        grid.attach(entry_cb, 0, 1, 1, 1)
        workspaces = togglAPI.get_workspaces()
        logger.debug('Got {0} workspaces'.format(len(workspaces)))

        for workspace in workspaces:
            workspace_store.append([workspace['name'], workspace['id']])

        workspace_cb.set_model(workspace_store)

        # After
        self.widget.add_action_widget(grid, 0)

    def on_ws_change(self, combo):
        tree_iter = combo.get_active_iter()
        if tree_iter:
            model = combo.get_model()
            name, wid = model[tree_iter][:2]
            logger.info('Selected workspace {0} ({1})'.format(name, wid))
            # fill entry cb
            entries = togglAPI.get_entries(wid)
            self.entry_store.clear()
            for e in entries:
                logger.info('Adding {0}'.format(e['description']))
                self.entry_store.append([e['description']])

    def on_entry_change(self, entry):
        logger.info(entry.get_text() + ' chosen')

    def on_dialog_response(self, widget, resposne):
        self.widget.hide()

    def run(self):
        self.widget.show_all()
        return self.widget


class PreferenceDialog:
    rows = 0

    def __init__(self, config):
        self.config = config

        self.widget = Gtk.Dialog(
            _('Preferences'),
            None,
            modal=True,
            resizable=False,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            buttons=(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
        )
        self.widget.connect('response', self.on_dialog_response)
        self.widget.set_size_request(350, 300)

        grid = Gtk.Grid(
            column_spacing=6,
            margin_bottom=12,
            margin_left=12,
            margin_right=12,
            margin_top=12,
            row_spacing=6,
        )

        self.add_section(grid)
        self.add_api_controls(grid, CONFIG_API_OPTION_NAME)

        self.widget.get_content_area().add(grid)

    def add_section(self, grid):
        label = Gtk.Label('<b>{0}</b>'.format(_('Setup Toggl')),
                          halign=Gtk.Align.START,
                          margin_left=6,
                          use_markup=True)
        grid.attach(label, 0, self.rows, 1, 1)
        self.rows += 1

    def run(self):
        self.read_config()
        self.widget.show_all()
        return self.widget

    def on_dialog_response(self, widget, response):
        for command_name in COMMANDS:
            entry = getattr(self, command_name + '_entry')
            command = parse_command(entry.get_text())

            if command:
                logger.debug('action=setConfig option=%s value=%s', command_name, command)
                self.config.set(CONFIG_SECTION_NAME, command_name, command)

        widget.hide()

    def read_config(self):
        logger.debug('action=readConfig')

        for command_name in COMMANDS:
            command = self.config.get(CONFIG_SECTION_NAME, command_name)
            entry = getattr(self, command_name + '_entry')

            if command is not None:
                entry.set_text(command)

    def add_api_controls(self, grid, command_name):
        label = Gtk.Label('',
                          hexpand=True,
                          halign=Gtk.Align.CENTER)
        label.set_markup('<a href="https://toggl.com/app/profile">API key</a>')
        grid.attach(label, 0, self.rows, 1, 1)

        self.rows += 1
        entry = Gtk.Entry(editable=True, sensitive=True)
        grid.attach(entry, 0, self.rows, 1, 1)
        setattr(self, command_name + '_entry', entry)

        self.rows += 1
        button = Gtk.Button(label='Check')
        button.connect('clicked', self.check_api_token_button_clicked)
        grid.attach(button, 0, self.rows, 1, 1)
        setattr(self, command_name + '_button', button)

        self.rows += 1
        self.check_label = Gtk.Label('')
        grid.attach(self.check_label, 0, self.rows, 1, 1)
        setattr(self, command_name + '_clabel', self.check_label)

    def check_api_token_button_clicked(self, button):
        entry = getattr(self, CONFIG_API_OPTION_NAME + '_entry')
        token = entry.get_text()
        checked = togglAPI.check_token(token)
        clabel = getattr(self, CONFIG_API_OPTION_NAME + '_clabel')
        if checked:
            clabel.set_text(checked)
        else:
            clabel.set_text('Token invalid')

    def reset_option(self, entry, command_name):
        if entry.get_text():
            logger.debug('action=resetCommandConfig command=%s needed=true', command_name)
            self.config.remove(CONFIG_SECTION_NAME, command_name)
            entry.set_text('')
        else:
            logger.debug('action=resetCommandConfig command=%s needed=false', command_name)


class TogglPlugin(tomate.plugin.Plugin):
    has_settings = True

    @suppress_errors
    def activate(self):
        super(TogglPlugin, self).activate()

    @suppress_errors
    def deactivate(self):
        super(TogglPlugin, self).deactivate()

    @suppress_errors
    def is_activated(self):
        super(TogglPlugin, self).is_activated()

    @suppress_errors
    def __init__(self):
        super(TogglPlugin, self).__init__()
        self.config = graph.get('tomate.config')
        self.preference_window = PreferenceDialog(self.config)

    @suppress_errors
    @on(Events.Session, [State.started])
    def on_session_started(self, *args, **kwargs):
        token = self.config.get(CONFIG_SECTION_NAME, CONFIG_API_OPTION_NAME)
        togglAPI.check_token(token)

        toggl_window = TogglGUI()
        toggl_window.run()

    @suppress_errors
    @on(Events.Session, [State.stopped])
    def on_session_stopped(self, *args, **kwargs):
        pass

    @suppress_errors
    @on(Events.Session, [State.finished])
    def on_session_finished(self, *args, **kwargs):
        pass

    def settings_window(self):
        return self.preference_window.run()