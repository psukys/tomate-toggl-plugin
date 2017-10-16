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
from .TogglAPI import TogglAPI
from .TogglGUI import TogglGUI
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
        grid.attach(self.check_label, 0, 4, 1, 1)
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
            print('setting clabel to {0}'.format(self.checked))
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
