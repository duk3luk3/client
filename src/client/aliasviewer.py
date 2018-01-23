import urllib.request
import urllib.error
import urllib.parse
import json
import copy
import time
from PyQt5 import QtWidgets
from PyQt5.QtCore import pyqtSignal

import logging
logger = logging.getLogger(__name__)

import api.methods

class ApiError(Exception):
    def __init__(self, reason):
        Exception.__init__(self)
        self.reason = reason


class AliasFinder(QObject):
    finished = pyqtSignal(list, list)

    def __init__(self, client, *args, **kwargs):
        QObject.__init__(self, *args, **kwargs)
        self.client = client
        self.previous_names = None
        self.other_users = None

        self._player_name = None

    def check_finish(self):
        if self.previous_names != None and self.other_users != None:
            self.finished.emit(self.previous_names, self.other_users)

    def previous_names_result(self, response):
        data = response.get('data')
        if not data:
            self.previous_names = ApiError('The name {} has never been used')
        else:
            included = response.get('included')
            if included:
                self.previous_names = [
                        {
                            'name': rec['attributes']['name'], 
                            'time': self._parse_time(rec['attributes']['changeTime'])
                        } for rec in included if rec['type'] == 'nameRecord'
                    ]
            else:
                self.previous_names = []
        self.check_finish()

    def previous_names_error(self, response):
        self.previous_names = ApiError(response)
        self.check_finish()

    def other_name_users_result(self, response):
        data = response.get('data')
        included = response.get('included', [])

        # invert included
        included_dict = {}
        for record in included:
            if not record['type'] in included_dict:
                included_dict[record['type']] = {}
            id = record['id']
            included_dict[record['type']][id] = record

        def find_change_time(player_rec):
            nameRecord_ids = [
                    rec['id']
                    for rec in player_rec['relationships']['names'] if
                    rec['type'] == 'nameRecord'
                ]
            nameRecords = [included_dict['nameRecord'][id] for id in nameRecords_ids]
            for nameRecord in nameRecords:
                if nameRecord['attributes']['name'] == player_rec['attributes']['login']:
                    return self._parse_time(nameRecord['attributes']['changeTime'])

        if not data:
            self.other_users = []
        else:
            self.other_users = [
                    {
                        'name': rec['attributes']['login'],
                        'id': rec['id'],
                        'time': find_change_time(rec)

                    }
                    for rec in data if
                    rec['type'] == 'player' and rec['attributes']['login'] != self_player_name
                ]
        self.check_finish()


    def other_name_users_error(self, response):
        self.other_users = ApiError(response)
        self.check_finish()

    def run(self, player_name):
        self._player_name = player_name
        api.methods.previous_names_used(client.Api, 250, 1, player_name,
            self.previous_names_result,
            self.previous_names_error)
        api.methods.other_name_users(client.Api, 250, 1, player_name,
            self.other_name_users_result,
            self.other_name_users_error)

    def _parse_time(self, t):
        try:
            return time.strptime(t, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None

class AliasFormatter:
    def __init__(self):
        pass

    def nick_times(self, times):
        past_times = [t for t in times if t['time'] is not None]
        current_times = [t for t in times if t['time'] is None]

        past_times.sort(key=lambda t: t['time'])
        name_format = "{}"
        past_format = "{}"
        current_format = "now"
        past_strings = [(name_format.format(e['name']),
                        past_format.format(time.strftime('%Y-%m-%d &nbsp; %H:%M', e['time'])))
                        for e in past_times]
        current_strings = [(name_format.format(e['name']),
                           current_format)
                           for e in current_times]
        return past_strings + current_strings

    def nick_time_table(self, nicks):
        table = '<br/><table border="0" cellpadding="0" cellspacing="1" width="220"><tbody>' \
                '{}' \
                '</tbody></table>'
        head = '<tr><th align="left"> Name</th><th align="center"> used until</th></tr>'
        line_fmt = '<tr><td>{}</td><td align="right">{}</td></tr>'
        lines = [line_fmt.format(*n) for n in nicks]
        return table.format(head + "".join(lines))

    def name_used_by_others(self, others, original_user=None):
        if others is None:
            return ''

        others = [u for u in others if u['name'] != original_user]
        if len(others) == 0 and original_user is None:
            return 'The name has never been used.'
        if len(others) == 0 and original_user is not None:
            return 'The name has never been used by anyone else.'

        return 'The name has previously been used by:{}'.format(
                self.nick_time_table(self.nick_times(others)))

    def names_previously_known(self, response):
        if response is None:
            return ''

        if len(response) == 0:
            return 'The user has never changed their name.'
        return 'The player has previously been known as:{}'.format(
                self.nick_time_table(self.nick_times(response)))


class AliasWindow:
    def __init__(self, parent):
        self._parent = parent
        self._api = AliasViewer()
        self._fmt = AliasFormatter()

    def view_aliases(self, name, id_=None):
        player_aliases = None
        other_users = None
        try:
            other_users = self._api.name_used_by_others(name)
            if id_ is None:
                users_now = [u for u in other_users if u['time'] is None]
                if len(users_now) > 0:
                    id_ = users_now[0]['id']
            if id_ is not None:
                player_aliases = self._api.names_previously_known(id_)
        except ApiError as e:
            logger.error(e.reason)
            warning_text = ("Failed to query the FAF API:<br/>"
                            "<i>{exception}</i><br/>"
                            "Some info may be incomplete!")
            warning_text = warning_text.format(exception=e.reason)
            QtWidgets.QMessageBox.warning(self._parent,
                                          "API read error",
                                          warning_text)

        if player_aliases is None and other_users is None:
            return

        alias_format = self._fmt.names_previously_known(player_aliases)
        others_format = self._fmt.name_used_by_others(other_users, name)
        result = '{}<br/><br/>{}'.format(alias_format, others_format)
        QtWidgets.QMessageBox.about(self._parent,
                                    "Aliases : {}".format(name),
                                    result)


class AliasSearchWindow:
    def __init__(self, parent):
        self._parent = parent
        self._alias_window = AliasWindow(parent)
        self._search_window = None

    def search_alias(self, name):
        self._alias_window.view_aliases(name)
        self._search_window = None

    def run(self):
        self._search_window = QtWidgets.QInputDialog(self._parent)
        self._search_window.setInputMode(QtWidgets.QInputDialog.TextInput)
        self._search_window.textValueSelected.connect(self.search_alias)
        self._search_window.setLabelText("User name / alias:")
        self._search_window.setWindowTitle("Alias search")
        self._search_window.open()
