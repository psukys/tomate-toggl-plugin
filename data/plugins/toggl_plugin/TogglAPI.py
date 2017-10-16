"""Toggl API functionality implementation."""
import logging
import requests
import urllib
import json
import datetime


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
