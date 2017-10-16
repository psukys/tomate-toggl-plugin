"""Toggl related GUI instances."""
from .TogglAPI import TogglAPI
import logging
from gi.repository import Gtk
import gi

gi.require_version('Gtk', '3.0')


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
