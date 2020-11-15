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

    def __init__(self, session_timeout=3600):
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
            self.session_id = '1605440452714_990932'
            self.t_session_start = time.time()

    @sleep_before_run
    def renew_csrf_token(self):
        resp = r.get(self.ENDPOINT + 'api/router/buildRoute/', headers=self.HEADERS, cookies=self.cookies)
        resp.raise_for_status()
        self.cookies.update(resp.cookies)
        try:
            self.csrf_token = resp.json()['csrfToken']
        except ValueError or IndexError as e:
            logger.error(f'Invalid response: {resp.text}')
            raise e

    @sleep_before_run
    def build_route(self, coords):
        params = {
            'activeComparisonMode': 'auto',
            'ajax': 1,
            'csrfToken': self.csrf_token,
            'ignoreTravelModes': 'avia',
            'isIntercityRoute': 'false',  # FIXME: Handle this
            'lang': 'ru',
            'locale': 'ru_RU',
            'mode': 'best',
            'rll': coords,  # NOTE: They are swapped  '-0.12766,51.507351~-3.679508,52.384911'
            'sessionId': self.session_id,
            'type': 'auto',
        }
        params_string = urllib.parse.urlencode(params)
        params['s'] = make_s(params_string)
        logger.info(f'Building route for coords: {coords}')
        logger.info(f'Sending params: {params}, cookies: {self.cookies}')
        resp = r.get(self.ENDPOINT + 'api/router/buildRoute/', params=params,
                     headers=self.HEADERS, cookies=self.cookies)
        self.cookies.update(resp.cookies)
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError as e:
            logger.error(f'Invalid response: {resp.text}')
            raise e
