# -*- coding: utf-8 -*-
#
# Copyright © Spyder Project Contributors
# Licensed under the terms of the MIT License
# (see spyder/__init__.py for details)

"""
Language server preferences
"""

# Standard library imports
import json
import re

# Third party imports
from qtpy.compat import to_qvariant
from qtpy.QtCore import (Qt, Slot, QAbstractTableModel, QModelIndex)
from qtpy.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                            QDialogButtonBox, QGroupBox, QGridLayout,
                            QHBoxLayout, QLabel, QLineEdit, QPushButton,
                            QSpinBox, QTableView, QTabWidget, QVBoxLayout,
                            QWidget)

# Local imports
from spyder.config.base import _
from spyder.config.main import CONF
from spyder.config.gui import get_font, is_dark_interface
from spyder.plugins.editor.lsp import LSP_LANGUAGES
from spyder.plugins.editor.widgets.codeeditor import CodeEditor
from spyder.preferences.configdialog import GeneralConfigPage
from spyder.utils import icon_manager as ima
from spyder.utils.programs import find_program
from spyder.widgets.helperwidgets import ItemDelegate


LSP_LANGUAGE_NAME = {x.lower(): x for x in LSP_LANGUAGES}
LSP_URL = "https://microsoft.github.io/language-server-protocol"


def iter_servers():
    for option in CONF.options('lsp-server'):
        if option in [l.lower() for l in LSP_LANGUAGES]:
            server = LSPServer(language=option)
            server.load()
            yield server


class LSPServer:
    """Convenience class to store LSP Server configuration values."""

    def __init__(self, language=None, cmd='', host='127.0.0.1',
                 port=2084, args='', external=False,
                 configurations={}):
        self.index = 0
        self.language = language
        if self.language in LSP_LANGUAGE_NAME:
            self.language = LSP_LANGUAGE_NAME[self.language]
        self.cmd = cmd
        self.args = args
        self.configurations = configurations
        self.port = port
        self.host = host
        self.external = external

    def __repr__(self):
        base_str = '[{0}] {1} {2} ({3}:{4})'
        fmt_args = [self.language, self.cmd, self.args,
                    self.host, self.port]
        if self.external:
            base_str = '[{0}] {1}:{2}'
            fmt_args = [self.language, self.host, self.port]
        return base_str.format(*fmt_args)

    def __str__(self):
        return self.__repr__()

    def __unicode__(self):
        return self.__repr__()

    def load(self):
        if self.language is not None:
            state = CONF.get('lsp-server', self.language.lower())
            self.__dict__.update(state)

    def save(self):
        if self.language is not None:
            language = self.language.lower()
            CONF.set('lsp-server', language, self.__dict__)

    def delete(self):
        if self.language is not None:
            language = self.language.lower()
            CONF.remove_option('lsp-server', language)


class LSPServerEditor(QDialog):
    DEFAULT_HOST = '127.0.0.1'
    DEFAULT_PORT = 2084
    DEFAULT_CMD = ''
    DEFAULT_ARGS = ''
    DEFAULT_CONFIGURATION = '{}'
    DEFAULT_EXTERNAL = False
    HOST_REGEX = re.compile(r'^\w+([.]\w+)*$')
    NON_EMPTY_REGEX = re.compile(r'^\S+$')
    JSON_VALID = _('JSON valid')
    JSON_INVALID = _('JSON invalid')

    def __init__(self, parent, language=None, cmd='', host='127.0.0.1',
                 port=2084, args='', external=False, configurations={},
                 **kwargs):
        super(LSPServerEditor, self).__init__(parent)
        self.parent = parent
        self.external = external
        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_ok = bbox.button(QDialogButtonBox.Ok)
        self.button_cancel = bbox.button(QDialogButtonBox.Cancel)
        self.button_ok.setEnabled(False)

        description = _('To create a new configuration, '
                        'you need to select a programming '
                        'language, along with a executable '
                        'name for the server to execute '
                        '(If the instance is local), '
                        'and the host and port. Finally, '
                        'you need to provide the '
                        'arguments that the server accepts. '
                        'The placeholders <tt>{host}</tt> and '
                        '<tt>{port}</tt> refer to the host '
                        'and the port, respectively.')
        server_settings_description = QLabel(description)
        server_settings_description.setWordWrap(True)

        lang_label = QLabel(_('Language:'))
        self.lang_cb = QComboBox(self)
        self.lang_cb.setToolTip(_('Programming language provided '
                                  'by the LSP server'))
        self.lang_cb.addItem(_('Select a language'))
        self.lang_cb.addItems(LSP_LANGUAGES)

        if language is not None:
            idx = LSP_LANGUAGES.index(language)
            self.lang_cb.setCurrentIndex(idx + 1)
            self.button_ok.setEnabled(True)

        host_label = QLabel(_('Host:'))
        self.host_input = QLineEdit(self)
        self.host_input.setToolTip(_('Name of the host that will provide '
                                     'access to the server'))
        self.host_input.setText(host)
        self.host_input.textChanged.connect(lambda x: self.validate())

        port_label = QLabel(_('Port:'))
        self.port_spinner = QSpinBox(self)
        self.port_spinner.setToolTip(_('TCP port number of the server'))
        self.port_spinner.setMinimum(1)
        self.port_spinner.setMaximum(60000)
        self.port_spinner.setValue(port)

        cmd_label = QLabel(_('Command to execute:'))
        self.cmd_input = QLineEdit(self)
        self.cmd_input.setToolTip(_('Command used to start the '
                                    'LSP server locally'))
        self.cmd_input.setText(cmd)

        if not external:
            self.cmd_input.textChanged.connect(lambda x: self.validate())

        args_label = QLabel(_('Server arguments:'))
        self.args_input = QLineEdit(self)
        self.args_input.setToolTip(_('Additional arguments required to '
                                     'start the server'))
        self.args_input.setText(args)

        conf_label = QLabel(_('LSP Server Configurations:'))
        self.conf_input = CodeEditor(None)
        self.conf_input.textChanged.connect(self.validate)
        color_scheme = CONF.get('appearance', 'selected')
        self.conf_input.setup_editor(
            language='JSON',
            color_scheme=color_scheme,
            wrap=False,
            edge_line=True,
            highlight_current_line=True,
            highlight_current_cell=True,
            occurrence_highlighting=True,
            auto_unindent=True,
            font=get_font(),
            filename='config.json')
        self.conf_input.setToolTip(_('Additional LSP server configurations '
                                     'set at runtime. JSON required'))
        conf_text = '{}'
        try:
            conf_text = json.dumps(configurations, indent=4, sort_keys=True)
        except Exception:
            pass
        self.conf_input.set_text(conf_text)
        self.json_label = QLabel(self.JSON_VALID, self)

        self.external_cb = QCheckBox(_('External server'), self)
        self.external_cb.setToolTip(_('Check if the server runs '
                                      'on a remote location'))
        self.external_cb.setChecked(external)
        self.external_cb.stateChanged.connect(self.set_local_options)

        hlayout = QHBoxLayout()
        general_vlayout = QVBoxLayout()
        general_vlayout.addWidget(server_settings_description)

        vlayout = QVBoxLayout()
        lang_layout = QVBoxLayout()
        lang_layout.addWidget(lang_label)
        lang_layout.addWidget(self.lang_cb)

        # layout2 = QHBoxLayout()
        # layout2.addLayout(lang_layout)
        lang_layout.addWidget(self.external_cb)
        vlayout.addLayout(lang_layout)

        host_layout = QVBoxLayout()
        host_layout.addWidget(host_label)
        host_layout.addWidget(self.host_input)

        port_layout = QVBoxLayout()
        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_spinner)

        conn_info_layout = QHBoxLayout()
        conn_info_layout.addLayout(host_layout)
        conn_info_layout.addLayout(port_layout)
        vlayout.addLayout(conn_info_layout)

        cmd_layout = QVBoxLayout()
        cmd_layout.addWidget(cmd_label)
        cmd_layout.addWidget(self.cmd_input)
        vlayout.addLayout(cmd_layout)

        args_layout = QVBoxLayout()
        args_layout.addWidget(args_label)
        args_layout.addWidget(self.args_input)
        vlayout.addLayout(args_layout)

        conf_layout = QVBoxLayout()
        conf_layout.addWidget(conf_label)
        conf_layout.addWidget(self.conf_input)
        conf_layout.addWidget(self.json_label)

        hlayout.addLayout(vlayout)
        hlayout.addLayout(conf_layout)
        general_vlayout.addLayout(hlayout)

        general_vlayout.addWidget(bbox)
        self.setLayout(general_vlayout)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        self.lang_cb.currentIndexChanged.connect(
            self.lang_selection_changed)
        self.form_status(False)
        if language is not None:
            self.form_status(True)
            self.validate()

    @Slot()
    def validate(self):
        host_text = self.host_input.text()
        cmd_text = self.cmd_input.text()
        if not self.HOST_REGEX.match(host_text):
            self.button_ok.setEnabled(False)
            self.host_input.setStyleSheet("QLineEdit{border: 1px solid red;}")
            self.host_input.setToolTip('Hostname must be valid')
            return
        else:
            self.host_input.setStyleSheet(
                "QLineEdit{border: 1px solid green;}")
            self.host_input.setToolTip('Hostname is valid')
            self.button_ok.setEnabled(True)

        if not self.external:
            if not self.NON_EMPTY_REGEX.match(cmd_text):
                self.button_ok.setEnabled(False)
                self.cmd_input.setStyleSheet(
                    "QLineEdit{border: 1px solid red;}")
                self.cmd_input.setToolTip('Command must be non empty')
                return

            if find_program(cmd_text) is None:
                self.button_ok.setEnabled(False)
                self.cmd_input.setStyleSheet(
                    "QLineEdit{border: 1px solid red;}")
                self.cmd_input.setToolTip('Program was not found '
                                          'on your system')
                return
            else:
                self.cmd_input.setStyleSheet(
                    "QLineEdit{border: 1px solid green;}")
                self.cmd_input.setToolTip('Program was found on your system')
                self.button_ok.setEnabled(True)
        try:
            json.loads(self.conf_input.toPlainText())
            try:
                self.json_label.setText(self.JSON_VALID)
            except Exception:
                pass
        except (ValueError, json.decoder.JSONDecodeError):
            try:
                self.json_label.setText(self.JSON_INVALID)
                self.button_ok.setEnabled(False)
            except Exception:
                pass

    def form_status(self, status):
        self.host_input.setEnabled(status)
        self.port_spinner.setEnabled(status)
        self.external_cb.setEnabled(status)
        self.cmd_input.setEnabled(status)
        self.args_input.setEnabled(status)
        self.conf_input.setEnabled(status)
        self.json_label.setVisible(status)

    @Slot()
    def lang_selection_changed(self):
        idx = self.lang_cb.currentIndex()
        if idx == 0:
            self.set_defaults()
            self.form_status(False)
            self.button_ok.setEnabled(False)
        else:
            server = self.parent.get_server_by_lang(LSP_LANGUAGES[idx - 1])
            self.form_status(True)
            if server is not None:
                self.host_input.setText(server.host)
                self.port_spinner.setValue(server.port)
                self.external_cb.setChecked(server.external)
                self.cmd_input.setText(server.cmd)
                self.args_input.setText(server.args)
                self.conf_input.set_text(json.dumps(server.configurations))
                self.json_label.setText(self.JSON_VALID)
                self.button_ok.setEnabled(True)
            else:
                self.set_defaults()

    def set_defaults(self):
        self.cmd_input.setStyleSheet('')
        self.host_input.setStyleSheet('')
        self.host_input.setText(self.DEFAULT_HOST)
        self.port_spinner.setValue(self.DEFAULT_PORT)
        self.external_cb.setChecked(self.DEFAULT_EXTERNAL)
        self.cmd_input.setText(self.DEFAULT_CMD)
        self.args_input.setText(self.DEFAULT_ARGS)
        self.conf_input.set_text(self.DEFAULT_CONFIGURATION)
        self.json_label.setText(self.JSON_VALID)

    @Slot(bool)
    @Slot(int)
    def set_local_options(self, enabled):
        self.external = enabled
        self.cmd_input.setEnabled(True)
        self.args_input.setEnabled(True)
        if enabled:
            self.cmd_input.setEnabled(False)
            self.cmd_input.setStyleSheet('')
            self.args_input.setEnabled(False)
        try:
            self.validate()
        except Exception:
            pass

    def get_options(self):
        language_idx = self.lang_cb.currentIndex()
        language = LSP_LANGUAGES[language_idx - 1]
        host = self.host_input.text()
        port = int(self.port_spinner.value())
        external = self.external_cb.isChecked()
        args = self.args_input.text()
        cmd = self.cmd_input.text()
        configurations = json.loads(self.conf_input.toPlainText())
        server = LSPServer(language=language.lower(), cmd=cmd, args=args,
                           host=host, port=port, external=external,
                           configurations=configurations)
        return server


LANGUAGE, ADDR, CMD = [0, 1, 2]


class LSPServersModel(QAbstractTableModel):
    def __init__(self, parent, text_color=None, text_color_highlight=None):
        QAbstractTableModel.__init__(self)
        self._parent = parent

        self.servers = []
        self.server_map = {}
        # self.scores = []
        self.rich_text = []
        self.normal_text = []
        self.letters = ''
        self.label = QLabel()
        self.widths = []

        # Needed to compensate for the HTMLDelegate color selection unawarness
        palette = parent.palette()
        if text_color is None:
            self.text_color = palette.text().color().name()
        else:
            self.text_color = text_color

        if text_color_highlight is None:
            self.text_color_highlight = \
                palette.highlightedText().color().name()
        else:
            self.text_color_highlight = text_color_highlight

    def sortByName(self):
        """Qt Override."""
        self.servers = sorted(self.servers, key=lambda x: x.language)
        self.reset()

    def flags(self, index):
        """Qt Override."""
        if not index.isValid():
            return Qt.ItemIsEnabled
        return Qt.ItemFlags(QAbstractTableModel.flags(self, index))

    def data(self, index, role=Qt.DisplayRole):
        """Qt Override."""
        row = index.row()
        if not index.isValid() or not (0 <= row < len(self.servers)):
            return to_qvariant()

        server = self.servers[row]
        column = index.column()

        if role == Qt.DisplayRole:
            if column == LANGUAGE:
                return to_qvariant(server.language)
            elif column == ADDR:
                text = '{0}:{1}'.format(server.host, server.port)
                return to_qvariant(text)
            elif column == CMD:
                text = '&nbsp;<tt style="color:{0}">{{0}} {{1}}</tt>'
                text = text.format(self.text_color)
                if server.external:
                    text = '&nbsp;<tt>External server</tt>'
                return to_qvariant(text.format(server.cmd, server.args))
        elif role == Qt.TextAlignmentRole:
            return to_qvariant(int(Qt.AlignHCenter | Qt.AlignVCenter))
        return to_qvariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """Qt Override."""
        if role == Qt.TextAlignmentRole:
            if orientation == Qt.Horizontal:
                return to_qvariant(int(Qt.AlignHCenter | Qt.AlignVCenter))
            return to_qvariant(int(Qt.AlignRight | Qt.AlignVCenter))
        if role != Qt.DisplayRole:
            return to_qvariant()
        if orientation == Qt.Horizontal:
            if section == LANGUAGE:
                return to_qvariant(_("Language"))
            elif section == ADDR:
                return to_qvariant(_("Address"))
            elif section == CMD:
                return to_qvariant(_("Command to execute"))
        return to_qvariant()

    def rowCount(self, index=QModelIndex()):
        """Qt Override."""
        return len(self.servers)

    def columnCount(self, index=QModelIndex()):
        """Qt Override."""
        return 3

    def row(self, row_num):
        """Get row based on model index. Needed for the custom proxy model."""
        return self.servers[row_num]

    def reset(self):
        """"Reset model to take into account new search letters."""
        self.beginResetModel()
        self.endResetModel()


class LSPServerTable(QTableView):
    def __init__(self, parent, text_color=None):
        QTableView.__init__(self, parent)
        self._parent = parent
        self.delete_queue = []
        self.source_model = LSPServersModel(self, text_color=text_color)
        self.setModel(self.source_model)
        self.setItemDelegateForColumn(CMD, ItemDelegate(self))
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSortingEnabled(True)
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.selectionModel().selectionChanged.connect(self.selection)
        self.verticalHeader().hide()

        self.load_servers()

    def focusOutEvent(self, e):
        """Qt Override."""
        # self.source_model.update_active_row()
        # self._parent.delete_btn.setEnabled(False)
        super(LSPServerTable, self).focusOutEvent(e)

    def focusInEvent(self, e):
        """Qt Override."""
        super(LSPServerTable, self).focusInEvent(e)
        self.selectRow(self.currentIndex().row())

    def selection(self, index):
        """Update selected row."""
        self.update()
        self.isActiveWindow()
        self._parent.delete_btn.setEnabled(True)

    def adjust_cells(self):
        """Adjust column size based on contents."""
        self.resizeColumnsToContents()
        fm = self.horizontalHeader().fontMetrics()
        names = [fm.width(s.cmd) for s in self.source_model.servers]
        self.setColumnWidth(CMD, max(names))
        self.horizontalHeader().setStretchLastSection(True)

    def get_server_by_lang(self, lang):
        return self.source_model.server_map.get(lang)

    def load_servers(self):
        servers = list(iter_servers())
        for i, server in enumerate(servers):
            server.index = i
            server.language = LSP_LANGUAGE_NAME[server.language.lower()]
        server_map = {x.language: x for x in servers}
        self.source_model.servers = servers
        self.source_model.server_map = server_map
        self.source_model.reset()
        self.adjust_cells()
        self.sortByColumn(LANGUAGE, Qt.AscendingOrder)

    def save_servers(self):
        for server in self.source_model.servers:
            server.save()
        while len(self.delete_queue) > 0:
            server = self.delete_queue.pop(0)
            server.delete()

    def delete_server(self, idx):
        server = self.source_model.servers.pop(idx)
        self.delete_queue.append(server)
        self.source_model.server_map.pop(server.language)
        self.source_model.reset()
        self.adjust_cells()
        self.sortByColumn(LANGUAGE, Qt.AscendingOrder)

    def show_editor(self, new_server=False):
        server = LSPServer()
        if not new_server:
            idx = self.currentIndex().row()
            server = self.source_model.row(idx)
        dialog = LSPServerEditor(self, **server.__dict__)
        if dialog.exec_():
            server = dialog.get_options()
            self.source_model.server_map[server.language] = server
            self.source_model.servers = list(
                self.source_model.server_map.values())
            self.source_model.reset()
            self.adjust_cells()
            self.sortByColumn(LANGUAGE, Qt.AscendingOrder)
            self._parent.set_modified(True)

    def next_row(self):
        """Move to next row from currently selected row."""
        row = self.currentIndex().row()
        rows = self.source_model.rowCount()
        if row + 1 == rows:
            row = -1
        self.selectRow(row + 1)

    def previous_row(self):
        """Move to previous row from currently selected row."""
        row = self.currentIndex().row()
        rows = self.source_model.rowCount()
        if row == 0:
            row = rows
        self.selectRow(row - 1)

    def keyPressEvent(self, event):
        """Qt Override."""
        key = event.key()
        if key in [Qt.Key_Enter, Qt.Key_Return]:
            self.show_editor()
        elif key in [Qt.Key_Backtab]:
            self.parent().reset_btn.setFocus()
        elif key in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
            super(LSPServerTable, self).keyPressEvent(event)
        elif key in [Qt.Key_Escape]:
            self.finder.keyPressEvent(event)
        else:
            super(LSPServerTable, self).keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Qt Override."""
        self.show_editor()


class LSPManagerConfigPage(GeneralConfigPage):
    """Language Server Protocol manager preferences."""
    CONF_SECTION = 'lsp-server'
    NAME = _('Completion and linting')
    ICON = ima.icon('lspserver')

    def setup_page(self):
        newcb = self.create_checkbox

        # --- Code completion ---
        # Introspection group
        introspection_group = QGroupBox(_("Introspection"))
        completion_box = newcb(_("Enable code completion"), 'code_completion')
        goto_definition_box = newcb(
            _("Go to definitions"),
            'jedi_definition',
            tip=_("If this option is enabled, doing a left mouse click on\n"
                  "an object name while pressing the Ctrl key will go to\n"
                  "that object's definition (if resolved)."))
        follow_imports_box = newcb(_("Follow imports when going to a "
                                     "definition"),
                                   'jedi_definition/follow_imports')
        show_signature_box = newcb(_("Show signature"), 'jedi_signature_help')

        introspection_layout = QVBoxLayout()
        introspection_layout.addWidget(completion_box)
        introspection_layout.addWidget(goto_definition_box)
        introspection_layout.addWidget(follow_imports_box)
        introspection_layout.addWidget(show_signature_box)
        introspection_group.setLayout(introspection_layout)

        # Advanced group
        advanced_group = QGroupBox(_("Advanced"))
        modules_textedit = self.create_textedit(
            _("Preload the following modules to make completion faster "
              "or more accurate:"),
            'preload_modules'
        )
        if is_dark_interface():
            modules_textedit.textbox.setStyleSheet(
                "border: 1px solid #32414B;"
            )

        advanced_layout = QVBoxLayout()
        advanced_layout.addWidget(modules_textedit)
        advanced_group.setLayout(advanced_layout)

        # --- Other servers tab ---
        # Section label
        servers_label = QLabel(
            _("Spyder uses the <a href=\"{lsp_url}\">Language Server "
              "Protocol</a> technology to provide code completion and linting "
              "for its Editor. Here you can setup and configure LSP servers "
              "for languages other than Python, so Spyder can provide such "
              "features for those languages as well."
              ).format(lsp_url=LSP_URL))
        servers_label.setOpenExternalLinks(True)
        servers_label.setWordWrap(True)
        servers_label.setAlignment(Qt.AlignJustify)

        # Servers table
        table_group = QGroupBox(_('Available servers:'))
        self.table = LSPServerTable(self, text_color=ima.MAIN_FG_COLOR)
        table_layout = QVBoxLayout()
        table_layout.addWidget(self.table)
        table_group.setLayout(table_layout)

        # Buttons
        self.reset_btn = QPushButton(_("Reset to default values"))
        self.new_btn = QPushButton(_("Setup a new server"))
        self.delete_btn = QPushButton(_("Delete currently selected server"))
        self.delete_btn.setEnabled(False)

        # Slots connected to buttons
        self.new_btn.clicked.connect(self.create_new_server)
        self.reset_btn.clicked.connect(self.reset_to_default)
        self.delete_btn.clicked.connect(self.delete_server)

        # Buttons layout
        btns = [self.new_btn, self.delete_btn, self.reset_btn]
        buttons_layout = QGridLayout()
        for i, btn in enumerate(btns):
            buttons_layout.addWidget(btn, i, 1)
        buttons_layout.setColumnStretch(0, 1)
        buttons_layout.setColumnStretch(1, 2)
        buttons_layout.setColumnStretch(2, 1)

        # Combined layout
        servers_widget = QWidget()
        servers_layout = QVBoxLayout()
        servers_layout.addSpacing(-10)
        servers_layout.addWidget(servers_label)
        servers_layout.addWidget(table_group)
        servers_layout.addSpacing(10)
        servers_layout.addLayout(buttons_layout)
        servers_widget.setLayout(servers_layout)

        # --- Tabs organization ---
        tabs = QTabWidget()
        tabs.addTab(self.create_tab(introspection_group, advanced_group),
                                    _('Code completion'))
        tabs.addTab(self.create_tab(servers_widget), _('Other languages'))

        vlayout = QVBoxLayout()
        vlayout.addWidget(tabs)
        self.setLayout(vlayout)

    def reset_to_default(self):
        CONF.reset_to_defaults(section='lsp-server')
        self.table.load_servers()
        self.load_from_conf()
        self.set_modified(True)

    def create_new_server(self):
        self.table.show_editor(new_server=True)

    def delete_server(self):
        idx = self.table.currentIndex().row()
        self.table.delete_server(idx)
        self.set_modified(True)
        self.delete_btn.setEnabled(False)

    def apply_settings(self, options):
        self.table.save_servers()
        # TODO: Reset Manager
        self.main.lspmanager.update_server_list()
        self.main.apply_settings()
