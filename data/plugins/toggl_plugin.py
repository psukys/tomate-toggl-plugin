"""
Tomate time tracker Toggl integration plugin.
"""
from __future__ import unicode_literals
import tomate.plugin
from tomate.constant import State
from tomate.event import Events, on
from tomate.graph import graph
from tomate.utils import suppress_errors
from tomate.constant import Task
from gi.repository import Gtk
import logging
import requests
import urllib
import json
import datetime
from locale import gettext as _

import gi

gi.require_version('Gtk', '3.0')

CONFIG_SECTION_NAME = 'toggl_plugin'
CONFIG_API_OPTION_NAME = 'api_token'
COMMANDS = [
    CONFIG_API_OPTION_NAME
]


class TogglAPI:
    """
    Class that partly covers Toggl API.

    API source: https://github.com/toggl/toggl_api_docs
    Args:
        api_url: Toggl API base url
    """

    api_url = 'https://www.toggl.com/api/v8'

    def __init__(self, token=None):
        """
        Initialize variables as they're checked later.

        token: Toggl API token
        curr_wid: current workspace ID
        curr_entry_id: current time entry ID
        logger: logging instance
        """
        self.logger = logging.getLogger('TogglAPI')
        self.token = None
        self.curr_wid = None
        self.curr_entry_id = None
        self.check_token(token)

    def request_get(self, path: str):
        """
        GET response from API on given path.

        Args:
            path: request path that is appended to api_url
        Returns:
            requests Response object
        """
        return requests.get(self.api_url + path,
                            auth=requests.auth.HTTPBasicAuth(self.token, 'api_token'))

    def request_post(self, path: str, data: dict):
        """
        POST and get response from API on given path and data.

        Args:
            path: request path that is appended to api_url
            data: data to be sent via POST requests
        Returns:
            requests Response object
        """
        return requests.post(self.api_url + path,
                             json=data,
                             auth=requests.auth.HTTPBasicAuth(self.token, 'api_token'))

    def request_put(self, path: str):
        """
        PUT and get response from API on given path.

        Args:
            path: request path that is appended to api_url
        Returns:
            requests Response object
        """
        return requests.put(path,
                            auth=requests.auth.HTTPBasicAuth(self.token, 'api_token'))

    def check_token(self, token: str):
        """
        Check for Toggl API token validity.

        Args:
            token: API token to be checked
        Returns:
            None if not valid, user email if valid
        """

        old_token = self.token
        self.token = token

        response = self.request_get('/me')
        if response.status_code == 200:
            data = json.loads(response.text)
            return data['data']['email']
        else:
            self.token = old_token
            self.logger.error('Token check failed:\n{0}'.format(response.text))

    def get_workspaces(self):
        """
        Get Toggl workspaces.

        Returns:
            list of user's workspaces

        """
        if self.token:
            response = self.request_get('/workspaces')
            if response.status_code == 200:
                data = json.loads(response.text)
                return data
            else:
                self.logger.error('Error while retrieving workspaces: {0}'.format(response.text()))
        else:
            self.logger.error('No token set')

    def get_entries(self, wid):
        """
        Get time entries from Toggl for specified workspace.

        Args:
            wid: user's workspace ID from which the time entries are fetched
        Returns:
            List of existing time entry names
        """
        # last week's entries
        # TODO: Make time range a variable (maybe fetched from settings)
        if self.token:
            # Build timestamps
            def fake_utcoffset(d):
                # TODO: not be so lazy
                dot_idx = d.index('.')
                d = d[:dot_idx]
                d += '+00:00'
                return d

            end_date = urllib.parse.quote_plus(
                fake_utcoffset(datetime.datetime.today().isoformat()))
            start_date = datetime.datetime.today() - datetime.timedelta(days=7)
            start_date = urllib.parse.quote_plus(
                fake_utcoffset(start_date.isoformat()))
            response = self.request_get('/time_entries?start_date={0}&end_date={1}'.format(start_date, end_date))
            # filter with workspace id given
            data = json.loads(response.text)
            self.logger.debug('Got {0} time entries'.format(len(data)))
            fil_entries = list(filter(lambda x: x['wid'] == wid, data))
            self.logger.debug('Filtered to {0} time entries that match WID'.format(len(fil_entries)))

            # filter unique names
            entries = []
            names = []
            for fe in fil_entries:
                if fe['description'] not in names:
                    names.append(fe['description'])
                    entries.append(fe)
            return entries
        else:
            self.logger.error('No token set')

    def start_entry(self, wid, description):
        """
        Start time entry at Toggl.

        Args:
            wid: workspace's ID
            description: description (apparently can be interpreted as title) of time entry
        Returns:
            True if entry started, else None
        """
        if self.token:
            json_data = {
                'time_entry': {
                    'wid': wid,
                    'description': description,
                    'created_with': 'tomate-toggl-plugin'}}

            response = self.request_post('/time_entries/start', json_data)
            if response.status_code == 200:
                data = json.loads(response.text)
                self.curr_entry_id = data['data']['id']
                self.curr_wid = data['data']['wid']
                self.logger.info('Started {0} entry as ID {1}'.format(
                    description, self.curr_entry_id))
                return True
            else:
                self.logger.error('Failed to start entry: {0}'.format(response.text))
        else:
            self.logger.error('No token set')

    def stop_entry(self, entry_id):
        """
        Stop time entry at Toggl.

        Args:
            entry_id: ID of the time entry
        Returns:
            True if stopped, else None
        """
        if self.token:
            r = requests.put('{0}/time_entries/{1}/stop'.format(self.api_url, entry_id),
                             auth=requests.auth.HTTPBasicAuth(self.token, 'api_token'))
            if r.status_code == 200:
                self.logger.info('{0} entry stopped'.format(entry_id))
                self.curr_entry_id = None
                self.curr_wid = None
                return True
            else:
                self.logger.error(
                    'Failed to stop entry {1}: \n{0}'.format(r.text, r.url))
        else:
            self.logger.error('No token set')


class TogglGUI(Gtk.Dialog):
    """Class for Toggl Gtk GUI interface."""

    def __init__(self, togglAPI: TogglAPI):
        """
        Init how the dialog should look like.

        Args:
            togglAPI: Toggl API interaction object
        """
        self.logger = logging.getLogger('TogglGUI')
        self.wid = None
        self.togglAPI = togglAPI

        Gtk.Dialog.__init__(
            self,
            _('Toggl'),
            None,
            modal=True,
            resizable=True,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            buttons=(Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY)
        )

        grid = Gtk.Grid(
            column_spacing=6,
            margin_bottom=12,
            margin_left=12,
            margin_right=12,
            margin_top=12,
            row_spacing=6,
        )

        # Workspace combobox
        workspace_cb = Gtk.ComboBox()
        workspace_store = Gtk.ListStore(str, int)
        workspace_renderer = Gtk.CellRendererText()
        workspace_cb.pack_start(workspace_renderer, 0)
        workspace_cb.add_attribute(workspace_renderer, 'text', 0)
        workspace_cb.connect('changed', self.on_ws_change)

        workspaces = self.togglAPI.get_workspaces()
        self.logger.debug('Got {0} workspaces'.format(len(workspaces)))

        for workspace in workspaces:
            workspace_store.append([workspace['name'], workspace['id']])

        workspace_cb.set_model(workspace_store)
        grid.attach(workspace_cb, 0, 0, 1, 1)

        self.entry_store = Gtk.ListStore(str)
        entry_cb = Gtk.ComboBox.new_with_model_and_entry(self.entry_store)
        entry_cb.set_entry_text_column(0)
        entry_cb.connect('changed', self.on_entry_change)
        grid.attach(entry_cb, 0, 1, 1, 1)

        # After
        self.add_action_widget(grid, 0)
        self.show_all()

    def on_ws_change(self, combo):
        """
        Signal hook for workspace change.

        Args:
            combo: combobox object
        """
        tree_iter = combo.get_active_iter()
        if tree_iter:
            model = combo.get_model()
            name, self.wid = model[tree_iter][:2]
            self.logger.debug('Selected workspace {0} ({1})'.format(name, self.wid))
            # fill entry cb
            entries = self.togglAPI.get_entries(self.wid)
            self.entry_store.clear()
            for entry in entries:
                self.logger.debug('Adding {0}'.format(entry['description']))
                self.entry_store.append([entry['description']])

    def on_entry_change(self, entry):
        """
        Signal hook for chosen entry.

        Args:
            entry: text entry object
        """
        item = entry.get_child()
        self.entry = item.get_text()
        self.logger.debug(self.entry + ' chosen')


class PreferenceDialog:
    """
    Gtk Dialog for preferences.
    """
    rows = 0

    def __init__(self, config):
        self.checked = None
        self.config = config
        self.logger = logging.getLogger('TogglPreferences')
        self.togglAPI = TogglAPI(token=self.config.get(CONFIG_SECTION_NAME, CONFIG_API_OPTION_NAME))

        self.widget = Gtk.Dialog(
            _('Preferences'),
            None,
            modal=True,
            resizable=False,
            window_position=Gtk.WindowPosition.CENTER_ON_PARENT,
            buttons=(Gtk.STOCK_APPLY, Gtk.ResponseType.APPLY,
                     Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
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

        label = Gtk.Label('<b>{0}</b>'.format(_('Setup Toggl')),
                          halign=Gtk.Align.START,
                          margin_left=6,
                          use_markup=True)
        grid.attach(label, 0, 0, 1, 1)

        label = Gtk.Label('',
                          hexpand=True,
                          halign=Gtk.Align.CENTER)
        label.set_markup('<a href="https://toggl.com/app/profile">API key</a>')
        grid.attach(label, 0, 1, 1, 1)

        entry = Gtk.Entry(editable=True, sensitive=True)
        grid.attach(entry, 0, 2, 1, 1)
        setattr(self, CONFIG_API_OPTION_NAME + '_entry', entry)

        button = Gtk.Button(label='Check')
        button.connect('clicked', self.check_api_token_button_clicked)
        grid.attach(button, 0, 3, 1, 1)
        setattr(self, CONFIG_API_OPTION_NAME + '_button', button)

        self.check_label = Gtk.Label('')
        grid.attach(self.check_label, 0, 3, 1, 1)
        setattr(self, CONFIG_API_OPTION_NAME + '_clabel', self.check_label)

        self.widget.get_content_area().add(grid)

    def run(self):
        """
        Function used by Tomate's plugin system when calling the preferences window.
        """
        self.read_config()
        self.widget.show_all()
        return self.widget

    def on_dialog_response(self, widget, response):
        """
        Hook for dialog response signal.

        Args:
            widget: current preferences dialog object
            response: Gtk Response object
        """
        if response == Gtk.ResponseType.CLOSE or response == Gtk.ResponseType.DELETE_EVENT:
            widget.hide()
            return

        if response == Gtk.ResponseType.APPLY:
            if self.checked:
                self.config.set(CONFIG_SECTION_NAME,
                                CONFIG_API_OPTION_NAME, self.togglAPI.token)
                widget.hide()
            else:
                # Not a nice way to reuse, but still...
                self.check_api_token_button_clicked(None)

    def read_config(self):
        self.logger.debug('action=readConfig')

        for command_name in COMMANDS:
            command = self.config.get(CONFIG_SECTION_NAME, command_name)
            entry = getattr(self, command_name + '_entry')

            if command is not None:
                entry.set_text(command)

    def check_api_token_button_clicked(self, button):
        entry = getattr(self, CONFIG_API_OPTION_NAME + '_entry')
        token = entry.get_text()
        self.checked = self.togglAPI.check_token(token)
        clabel = getattr(self, CONFIG_API_OPTION_NAME + '_clabel')
        if self.checked:
            clabel.set_text(self.checked)
        else:
            clabel.set_text('Token invalid')


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
        self.togglAPI = TogglAPI(token=self.config.get(CONFIG_SECTION_NAME, CONFIG_API_OPTION_NAME))
        self.preference_window = PreferenceDialog(self.config)
        self.toggl_activity_started = False

    @suppress_errors
    @on(Events.Session, [State.started])
    def on_session_started(self, *args, **kwargs):
        if kwargs['task'] is not Task.pomodoro:
            return  # Only apply Toggl for working sessions
        token = self.config.get(CONFIG_SECTION_NAME, CONFIG_API_OPTION_NAME)
        self.togglAPI.check_token(token)

        toggl_window = TogglGUI(self.togglAPI)
        response = toggl_window.run()
        toggl_window.hide()
        if response == Gtk.ResponseType.APPLY:
            self.togglAPI.start_entry(wid=toggl_window.wid,
                                      description=toggl_window.entry)
            self.toggl_activity_started = True

    @suppress_errors
    @on(Events.Session, [State.stopped])
    def on_session_stopped(self, *args, **kwargs):
        if self.toggl_activity_started:
            token = self.config.get(
                CONFIG_SECTION_NAME, CONFIG_API_OPTION_NAME)
            self.togglAPI.check_token(token)

            self.togglAPI.stop_entry(self.togglAPI.curr_entry_id)
            self.toggl_activity_started = False

    @suppress_errors
    @on(Events.Session, [State.finished])
    def on_session_finished(self, *args, **kwargs):
        token = self.config.get(CONFIG_SECTION_NAME, CONFIG_API_OPTION_NAME)
        self.togglAPI.check_token(token)

        self.togglAPI.stop_entry(self.togglAPI.curr_entry_id)

    def settings_window(self):
        return self.preference_window.run()
