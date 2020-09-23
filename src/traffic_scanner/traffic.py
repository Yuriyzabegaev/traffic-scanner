import io
import base64
import string
import math
import random

import numpy as np
import time
import re
import requests as r
from telegram import InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, Filters
import urllib
from urllib import parse
import csv
import logging
import pandas as pd
import datetime
import matplotlib
import matplotlib.dates as md
matplotlib.use('Agg')
import matplotlib.pyplot as plt


plt.style.use('fivethirtyeight')

logger = logging.getLogger('traffic.py')
np.seterr(all="ignore")
logging.basicConfig(level=logging.INFO)

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR


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
    REQUESTS_DELAY = 0.1
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

    def update_session(self, forse=False):
        if forse or time.time() - self.t_session_start > self.session_timeout:
            time.sleep(self.REQUESTS_DELAY)
            resp = r.get(self.ENDPOINT, headers=self.HEADERS)
            resp.raise_for_status()
            self.cookies = resp.cookies
            self.renew_csrf_token()
            self.session_id = self.generate_random_session_id()
            self.t_session_start = time.time()

    def renew_csrf_token(self):
        time.sleep(self.REQUESTS_DELAY)
        resp = r.get(self.ENDPOINT + 'api/router/buildRoute/', headers=self.HEADERS, cookies=self.cookies)
        self.cookies.update(resp.cookies)
        resp.raise_for_status()
        try:
            self.csrf_token = resp.json()['csrfToken']
        except ValueError or IndexError as e:
            logger.error(f'Invalid response: {resp.text}')
            raise e

    def build_route(self, coords):
        time.sleep(self.REQUESTS_DELAY)
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
        params['s'] = make_s(urllib.parse.urlencode(params))
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


class RouteHandler:

    def __init__(self, yandex_maps_client, coords, filename):
        self.filename = filename
        self.coords = coords
        self.y = yandex_maps_client

    def update_traffic(self):
        t = time.time()
        traffic_json = self.y.build_route(self.coords)
        try:
            routes = traffic_json['data']['routes']
            if len(routes) > 0:  # TODO: Is [0] the quickest?
                duration_sec = routes[0]['durationInTraffic']
            else:
                logger.error(f'On route {self.coords} 0 available ways were found.')
                duration_sec = None  # TODO: Handle this
        except KeyError as e:
            logger.error(f'Invalid json: {traffic_json}')
            raise e
        logger.info(f'Duration: {duration_sec}')
        self.write_traffic(t, duration_sec)

    def write_traffic(self, t, duration):
        with open(self.filename, 'a') as f:
            writer = csv.writer(f)
            writer.writerow([self.coords, datetime.datetime.fromtimestamp(t), duration])


class TrafficDispatcher:

    def __init__(self, period, routes, filename='traffic.csv'):
        self.period = period
        self.filename = filename
        self.y = YandexMapsClient()
        self.routes = [RouteHandler(self.y, coords, filename=filename) for coords in routes]

    def update_traffic(self):
        self.y.update_session()
        for route in self.routes:
            route.update_traffic()

    def serve(self):
        logger.info('Start serving.')
        while True:
            t0 = time.time()
            self.update_traffic()
            sleep_time = max(self.period - (time.time() - t0), 0)
            logger.info(f'Sleeping for {sleep_time} seconds.')
            time.sleep(sleep_time)

    def add_route(self, route):
        self.routes.append((RouteHandler(self.y, coords=route, filename=self.filename)))

    def remove_route(self, route):
        self.routes.remove(route)


class TrafficView:

    def __init__(self, period):
        assert period < 24 * 60 * 60
        self.time_intervals = math.ceil(DAY / period)
        self.timedelta = datetime.timedelta(seconds=period)

    @staticmethod
    def seconds_to_time(seconds):
        hour = math.floor(seconds / HOUR)
        minute = math.floor((seconds % HOUR) / MINUTE)
        second = math.floor(seconds % MINUTE)
        return datetime.datetime(2011, 1, 11, hour, minute, second)

    def plot_traffic(self, timestamps, durations):
        datetimes = tuple(map(datetime.datetime.fromisoformat, timestamps))
        time_intervals = []
        durations_in_time_intervals = []

        time_start = datetime.datetime.min
        time_end = datetime.datetime.min + self.timedelta
        nonzero_idx = []
        for i in range(self.time_intervals):
            durations_in_this_interval = tuple(durations[j] for j in range(len(datetimes))
                                               if time_start.time() <= datetimes[j].time() < time_end.time())
            if len(durations_in_this_interval) != 0:
                # TODO: Handle nans
                nonzero_idx.append(i)
            durations_in_time_intervals.append(durations_in_this_interval)
            time_intervals.append(time_start.time())
            time_start += self.timedelta
            time_end += self.timedelta

        # Removing empty
        durations_in_time_intervals = tuple(filter(len, durations_in_time_intervals))
        time_intervals = np.array(time_intervals)[nonzero_idx]

        alpha = 0.4
        fig = plt.figure(figsize=(12, 4))
        max_ = tuple(map(np.max, durations_in_time_intervals))
        mean = tuple(map(np.mean, durations_in_time_intervals))
        min_ = tuple(map(np.min, durations_in_time_intervals))
        x_labels = tuple(map(lambda x: datetime.datetime(2011, 11, 11, x.hour, x.minute, x.second), time_intervals))
        ax = fig.gca()

        ax.xaxis_date()
        ax.xaxis.set_major_formatter(md.DateFormatter('%H:%M'))
        ax.yaxis.set_major_formatter(md.DateFormatter('%H:%M'))

        # Casting to time
        max_ = tuple(map(self.seconds_to_time, max_))
        min_ = tuple(map(self.seconds_to_time, min_))
        mean = tuple(map(self.seconds_to_time, mean))

        ax.bar(x_labels, max_, alpha=alpha, label='Min', width=0.005)
        ax.bar(x_labels, min_, alpha=alpha, label='Max', width=0.015)
        ax.set_ylim(np.min(min_) - datetime.timedelta(minutes=10), np.max(max_) + datetime.timedelta(minutes=10))
        fig.legend()
        return fig


class BotController:
    ENTER_START, ENTER_FINISH, = range(2)

    def __init__(self, period, routes_filename='routes.csv'):
        self.routes_filename = routes_filename
        routes = pd.read_csv(routes_filename)['route'].tolist()
        self.td = TrafficDispatcher(period=period, routes=routes)
        self.tv = TrafficView(period=30 * MINUTE)
        self.coords_regexp = re.compile(r'^(-?\d+(\.\d+)?),\s*(-?\d+(\.\d+)?)$')

    def make_traffic_figures(self):
        df = pd.read_csv(self.td.filename)
        figures = list()
        for route in self.td.routes:
            route_df = df[df['coords'] == route.coords]
            timestamps = route_df['timestamp'].tolist()
            durations = route_df['duration'].tolist()
            figures.append(self.tv.plot_traffic(timestamps, durations))
        return tuple(figures)

    # BOT COMMANDS

    def add_route(self, start_coords, end_coords):
        # TODO: Remove whitespaces
        route = f'{start_coords}~{end_coords}'
        self.td.add_route(route)
        with open(self.routes_filename, 'a') as f:
            writer = csv.DictWriter(f, ['route', 'user_id'])
            writer.writerow({'route': route, 'user_id': None})

    def remove_route(self, route):
        self.td.remove_route(route)
        routes_df = pd.read_csv(self.routes_filename)
        routes_df.drop(routes_df['route'] == route)
        routes_df.to_csv(self.routes_filename, index=False)

    def start(self, update, context):
        update.message.reply_text(
            'Enter start point coordinates or url'
        )
        return self.ENTER_START

    def enter_start(self, update, context):
        if update.message.text == '/cancel':
            update.message.reply_text('Ok')
            return ConversationHandler.END
        coords = self.coords_regexp.match(update.message.text)
        if coords is None:
            update.message.reply_text('Could not understand your coordinates. Retry? :(')
            return self.ENTER_START
        context.chat_data['start_location'] = coords.group(0)
        # logger.info("Gender of %s: %s", user.first_name, update.message.text)
        update.message.reply_text('Now enter finish coordinates')
        return self.ENTER_FINISH

    def enter_finish(self, update, context):
        if update.message.text == '/cancel':
            update.message.reply_text('Ok')
            return ConversationHandler.END
        coords = self.coords_regexp.match(update.message.text)
        if coords is None:
            update.message.reply_text('Could not understand your coordinates. Retry? :(')
            return self.ENTER_FINISH
        context.chat_data['finish_location'] = coords.group(0)
        # logger.info("Gender of %s: %s", user.first_name, update.message.text)
        self.add_route(context.chat_data['start_location'], context.chat_data['finish_location'])
        update.message.reply_text('Ok!')
        return ConversationHandler.END

    def build_report(self, update, context):
        figures = self.make_traffic_figures()
        for fig in figures:
            with io.BytesIO() as buf:
                fig.savefig(buf, format='png')
                buf.seek(0)
                plot_file = InputFile(buf)
            # update.message.reply_text(f'route: {route.coords}')
            update.message.reply_photo(plot_file)

    def list_routes(self, update, context):
        routes_df = pd.read_csv(self.routes_filename)
        update.message.reply_text(str(routes_df['route'].tolist()))


period = 10 * 60
bc = BotController(period)
updater = Updater(token='672100742:AAEC7GTgY32rkDB5mBdYmqxPvO2gXLRREs0', use_context=True)
dp = updater.dispatcher
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', bc.start)],
    states={
        bc.ENTER_START: [MessageHandler(
            Filters.text,
            bc.enter_start)],
        bc.ENTER_FINISH: [MessageHandler(
            Filters.text,
            bc.enter_finish)],
    },
    fallbacks=[]
)

dp.add_handler(conv_handler)
dp.add_handler(CommandHandler('report', bc.build_report))
dp.add_handler(CommandHandler('list', bc.list_routes))

# figs = bc.make_traffic_figures()

dp.run_async(bc.td.serve)
updater.start_polling()
updater.idle()
