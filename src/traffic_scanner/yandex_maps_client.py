import logging
import random
import string
import time
import urllib
import re

import numpy as np
import requests as r

logger = logging.getLogger('traffic_scanner/yandex_maps_client.py')
REQUESTS_DELAY = 0.1

DAY = 60 * 60 * 24

LOCATION_TITLE_REGEX = re.compile(r'<meta property=\"og:title\" content=\"(.*?)\">')


def sleep_before_run(func):
    def closure(*args, **kwargs):
        time.sleep(REQUESTS_DELAY)
        return func(*args, **kwargs)

    return closure


def make_s(source):
    """
     return t ? String(function(e) {
         for (var t = e.length, n = 5381, r = 0; r < t; r++)
             n = 33 * n ^ e.charCodeAt(r);
         return n >>> 0
     }(t)) : ""
     """
    n = np.int32(5381)
    for r in range(len(source)):
        n = np.int32(33) * np.int32(n) ^ np.int32(ord(source[r]))
    return np.uint32(n)


class YandexMapsClient:
    ENDPOINT = 'https://yandex.ru/maps/'
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/605.1.15 (KHTML, like Gecko)\
        Version/13.1.2 Safari/605.1.15',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us'
    }

    def __init__(self, session_timeout=DAY):
        self.session_timeout = session_timeout
        self.cookies = None
        self.csrf_token = None
        self.session_id = None
        self.t_session_start = -1

    @staticmethod
    def generate_random_session_id():
        prefix = ''.join(random.choices(string.digits, k=13))
        suffix = ''.join(random.choices(string.digits, k=6))
        return '{}_{}'.format(prefix, suffix)

    @sleep_before_run
    def update_session(self, force=False):
        if force or time.time() - self.t_session_start > self.session_timeout:
            resp = r.get(self.ENDPOINT, headers=self.HEADERS)
            resp.raise_for_status()
            self.cookies = resp.cookies
            self.renew_csrf_token()
            self.session_id = self.generate_random_session_id()
            self.t_session_start = time.time()

    @sleep_before_run
    def renew_csrf_token(self, csrf_token=None):
        if csrf_token is None:
            resp = r.get(self.ENDPOINT + 'api/router/buildRoute/', headers=self.HEADERS, cookies=self.cookies)
            resp.raise_for_status()
            self.cookies.update(resp.cookies)
            try:
                csrf_token = resp.json()['csrfToken']
            except ValueError or IndexError as e:
                logger.error(f'Invalid response: {resp.text}')
                raise e

        self.csrf_token = csrf_token

    @sleep_before_run
    def make_api_request(self, url, params, retry=True):
        self.update_session()
        resp = r.get(self.ENDPOINT + url, params=params,
                     headers=self.HEADERS, cookies=self.cookies)
        self.cookies.update(resp.cookies)
        resp.raise_for_status()
        try:
            resp_json = resp.json()
        except ValueError as e:
            logger.error(f'Invalid response: {resp.text}')
            raise e

        resp_keys = resp_json.keys()
        if 'data' in resp_keys:
            return resp_json
        if retry is False:
            raise ValueError(resp_json)

        if 'csrfToken' in resp_keys:
            self.renew_csrf_token(resp_json['csrfToken'])
        if 'error' in resp_keys:
            logger.warning('error in api response: ' + str(resp))
        return self.make_api_request(url, params, retry=False)

    def build_route(self, start_coords, end_coords):
        coords_str = f'{start_coords[0]},{start_coords[1]}~{end_coords[0]},{end_coords[1]}'
        params = {
            'activeComparisonMode': 'auto',
            'ajax': 1,
            'csrfToken': self.csrf_token,
            'ignoreTravelModes': 'avia',
            'isIntercityRoute': 'false',  # FIXME: Handle this
            'lang': 'ru',
            'locale': 'ru_RU',
            'mode': 'best',
            'rll': coords_str,  # NOTE: They are swapped  '-0.12766,51.507351~-3.679508,52.384911'
            'sessionId': self.session_id,
            'type': 'auto',
        }
        params_string = urllib.parse.urlencode(params)
        params['s'] = make_s(params_string)
        logger.info(f'Building route for coordinates: {coords_str}')
        return self.make_api_request('api/router/buildRoute/', params=params)

    # @sleep_before_run
    # def get_location_title(self, coords):
    #     coords_str = f'{coords[1]},{coords[0]}'
    #     logger.info(f'Getting title for location at coordinates: {coords_str}')
    #     params = {
    #         'mode': 'search',
    #         'text': coords_str,  # User verbose format
    #         'z': '1'
    #     }
    #     resp = r.get(self.ENDPOINT, params=params, headers=self.HEADERS, cookies=self.cookies)
    #     resp.raise_for_status()
    #     regex_matches = LOCATION_TITLE_REGEX.search(resp.text)
    #     if regex_matches is None:
    #         raise ValueError('Unable to match')
    #     return regex_matches.group(1)
