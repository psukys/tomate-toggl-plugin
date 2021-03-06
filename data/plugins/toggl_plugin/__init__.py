"""Tomate time tracker Toggl integration plugin."""
from __future__ import unicode_literals

import logging
import urllib
import json
import datetime
from locale import gettext as _
import requests
import gi
from gi.repository import Gtk
import tomate.plugin
from tomate.constant import State
from tomate.event import Events, on
from tomate.graph import graph
from tomate.utils import suppress_errors
from tomate.constant import Task
from .TogglAPI import TogglAPI
from .TogglGUI import TogglGUI

gi.require_version('Gtk', '3.0')

CONFIG_SECTION_NAME = 'toggl_plugin'
CONFIG_API_OPTION_NAME = 'api_token'
CONFIG_ENTRY_FETCH_LENGTH = 'entry_fetch_length'
COMMANDS = [
    CONFIG_API_OPTION_NAME,
    CONFIG_ENTRY_FETCH_LENGTH
]


class PreferenceDialog:
    """Gtk Dialog for preferences."""

    def __init__(self, config):
        """
        Set up internals and build up GUI.

        Args:
            config: Tomate config instance
        """
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
        label.set_markup('<a href="https://toggl.com/app/profile">{0}</a>'.format(_('API key')))
        grid.attach(label, 0, 1, 1, 1)

        self.api_entry = Gtk.Entry(editable=True, sensitive=True)
        grid.attach(self.api_entry, 0, 2, 1, 1)

        self.check_button = Gtk.Button(label=_('Check'))
        self.check_button.connect('clicked', self.check_api_token_button_clicked)
        grid.attach(self.check_button, 0, 3, 1, 1)

        self.check_label = Gtk.Label('')
        grid.attach(self.check_label, 0, 4, 1, 1)

        self.entry_length_label = Gtk.Label(_('Days back to fetch time entry descriptions'))
        grid.attach(self.entry_length_label, 0, 5, 1, 1)
        entry_length_adjustment = Gtk.Adjustment(7, 0, 31, 1, 1, 1)

        self.entry_length_hscale = Gtk.HScale(adjustment=entry_length_adjustment)
        self.entry_length_hscale.set_digits(0)
        grid.attach(self.entry_length_hscale, 0, 6, 1, 1)

        self.widget.get_content_area().add(grid)

    def run(self):
        """Runner function used by Tomate's plugin system when calling the preferences window."""
        self.read_config()
        self.widget.show_all()
        return self.widget

    def on_dialog_response(self, widget, response):
        """
        Hooks for dialog response signal.

        Args:
            widget: current preferences dialog object
            response: Gtk Response object
        """
        if response == Gtk.ResponseType.CLOSE or response == Gtk.ResponseType.DELETE_EVENT:
            widget.hide()
            return

        if response == Gtk.ResponseType.APPLY:
            # Save time entry retrieval length
            self.config.set(CONFIG_SECTION_NAME,
                            CONFIG_ENTRY_FETCH_LENGTH, str(int(self.entry_length_hscale.get_value())))

            if not self.checked:
                self.checked = self.verify_api_token(self.api_entry.get_text())

            if self.checked:
                self.config.set(CONFIG_SECTION_NAME,
                                CONFIG_API_OPTION_NAME, self.togglAPI.token)
                widget.hide()
            else:
                self.check_label.set_text(_('Token invalid'))

    def read_config(self):
        """Read config for relevant saved values."""
        self.logger.debug('action=readConfig')

        command = self.config.get(CONFIG_SECTION_NAME, CONFIG_API_OPTION_NAME)
        if command is not None:
            self.api_entry.set_text(command)

        command = self.config.get(CONFIG_SECTION_NAME, CONFIG_ENTRY_FETCH_LENGTH)
        if command is not None:
            self.entry_length_hscale.set_value(int(command))

    def verify_api_token(self, token):
        """
        Verify Toggl API token.

        Args:
            token:  Toggl API token string
        Returns: None if API token invalid or profile's email.
        """
        return self.togglAPI.check_token(token)

    def check_api_token_button_clicked(self, button):
        """
        Hooks for "Check API" button.

        Args:
            button: clicked button object
        """
        token = self.api_entry.get_text()
        self.checked = self.verify_api_token(token)

        if self.checked:
            self.check_label.set_text(self.checked)
        else:
            self.check_label.set_text(_('Token invalid'))


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

            self.togglAPI.stop_entry(self.togglAPI.curr_entry_id)
            self.toggl_activity_started = False

    @suppress_errors
    @on(Events.Session, [State.finished])
    def on_session_finished(self, *args, **kwargs):
        token = self.config.get(CONFIG_SECTION_NAME, CONFIG_API_OPTION_NAME)

        self.togglAPI.stop_entry(self.togglAPI.curr_entry_id)

    def settings_window(self):
        return self.preference_window.run()
