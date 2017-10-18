"""Toggl API functionality implementation."""
import logging
import urllib
import json
import time
import datetime
import requests


class UserUTC(datetime.tzinfo):
    """Fixing datetime functionality by explicitly stating current timezone."""

    def utcoffset(self, dt):
        """UTC offset method that is called when datetime needs."""
        # Use time to deduce utc offset
        offset_seconds = time.localtime().tm_gmtoff
        return datetime.timedelta(seconds=offset_seconds)


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
            self.logger.error('Token check failed: {0}'.format(response.text))

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

    def adjust_datetime_to_iso8601(self, dtime):
        """
        Adjust datetime to Toggl's specified ISO8601 format.

        Args:
            dtime: datetime object
        Returns:
            given datetime encoded in ISO8601 format, i.e. 2017-10-18T17:48:06.840314+02:00

        """
        iso_time = dtime.replace(tzinfo=UserUTC()).isoformat()
        # god bless datetime thinks that one can omit UTC 0 (+00:00)
        if '+' not in iso_time:
            iso_time += '+00:00'

        return iso_time

    def get_start_end_isodates(self, timedelta=datetime.timedelta(days=7)):
        """
        Get start and end dates in ISO 8601 format (as defined in Toggl docs).

        Args:
            timedelta: difference from end_date to start date

        end_date will be current time
        start_date has to be before end_date, thus negative time deltas are not accepted.

        Returns:
            tuple (start_date, end_date)

        """
        if timedelta < datetime.timedelta():
            self.logger.error('Bad timedelta given, should be positive')
            return None

        end_date = datetime.datetime.today()
        start_date = datetime.datetime.today() - timedelta
        return (self.adjust_datetime_to_iso8601(start_date),
                self.adjust_datetime_to_iso8601(end_date),)

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
            start_date, end_date = self.get_start_end_isodates()
            end_date_quoted = urllib.parse.quote_plus(end_date)
            start_date_quoted = urllib.parse.quote_plus(start_date)
            response = self.request_get('/time_entries?start_date={0}&end_date={1}'.format(start_date_quoted, end_date_quoted))

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
            r = self.request_put('{0}/time_entries/{1}/stop'.format(self.api_url, entry_id))
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
