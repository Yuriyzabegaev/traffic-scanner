import io

import numpy as np
import re
from requests import get as get_request
from requests.exceptions import MissingSchema, HTTPError
from telegram import InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, Filters
import csv
import logging
import pandas as pd
import matplotlib

from traffic_scanner.storage import TrafficStorageCSV
from traffic_scanner.yandex_maps_client import YandexMapsClient

matplotlib.use('Agg')
import matplotlib.pyplot as plt

from traffic_scanner.traffic_scanner import TrafficScanner
from traffic_scanner.traffic_view import TrafficView

plt.style.use('fivethirtyeight')

logger = logging.getLogger('traffic_scanner/bot_controller.py')
np.seterr(all="ignore")
logging.basicConfig(level=logging.INFO)


MINUTE = 60 * 60


COORDS_REGEX = re.compile(r'-?\d+\.\d+')
COORDS_FROM_URL_REGEX = re.compile(r'\"point\":[^}]*-?\d+\.\d+')


def check_cancel(update):
    if update.message.text == '/cancel':
        update.message.reply_text(BotController.RESPONSE_ON_CANCEL)
        return True
    return False


def get_coords_string_from_url(input_string):
    response = get_request(input_string)
    response.raise_for_status()
    coordinate_strings = COORDS_FROM_URL_REGEX.search(response.text)
    if coordinate_strings is None:
        raise ValueError
    return coordinate_strings.group()


def parse_coordinates_or_url(input_str):
    # Determine if input_str is url or coordinates
    try:
        coords_string = get_coords_string_from_url(input_str)
        is_url = True
    except MissingSchema:
        # This is not an url
        coords_string = input_str
        is_url = False

    # User sent coordinates
    coords = COORDS_REGEX.findall(coords_string)
    if len(coords) != 2:
        raise ValueError

    return coords[1], coords[0]


class BotController:

    ENTER_START, ENTER_FINISH, = range(2)

    RESPONSE_ON_START = ('''
    Hello!
    
    Commands:
    /add
    /list
    /report
    ''')
    PROPOSAL_ENTER_START = 'Enter start point coordinates or url'
    PROPOSAL_COORDINATES_INSTEAD_OF_URL = 'Could you send coordinates please?'
    RESPONSE_ON_CANCEL = 'Ok'
    RESPONSE_ON_SUCCESS = 'Ok'
    FAILURE_PARSING_COORDINATES = '''Could not understand your coordinates
 Retry?
 Please, send coordinates or link from Yandex maps
 '''

    def __init__(self, traffic_scanner, traffic_plotter, traffic_parser):
        self.traffic_parser = traffic_parser
        self.traffic_scanner: TrafficScanner = traffic_scanner
        self.traffic_plotter: TrafficView = traffic_plotter

    '''BOT COMMANDS'''

    def add_route(self, start_coords, end_coords):
        # TODO: Remove whitespaces
        route = f'{start_coords}~{end_coords}'

        self.traffic_scanner.storage.add_route(route)

    def remove_route(self, route):
        self.traffic_scanner.storage.remove_route(route)

    @staticmethod
    def start(update, context):
        update.message.reply_text(BotController.RESPONSE_ON_START)

    @staticmethod
    def add(update, context):
        update.message.reply_text(BotController.PROPOSAL_ENTER_START)
        return BotController.ENTER_START

    def enter_start(self, update, context):
        if check_cancel(update):
            return ConversationHandler.END
        try:
            l1, l0 = parse_coordinates_or_url(update.message.text)
        except ValueError:
            update.message.reply_text(BotController.FAILURE_PARSING_COORDINATES)
            return BotController.ENTER_START
        except HTTPError:
            update.message.reply_text(BotController.PROPOSAL_COORDINATES_INSTEAD_OF_URL)
            return BotController.ENTER_START

        context.chat_data['start_location'] = l0, l1
        update.message.reply_text('Now enter finish coordinates')
        return self.ENTER_FINISH

    def enter_finish(self, update, context):
        if check_cancel(update):
            return ConversationHandler.END
        try:
            l1, l0 = parse_coordinates_or_url(update.message.text)
        except ValueError:
            update.message.reply_text(BotController.FAILURE_PARSING_COORDINATES)
            return BotController.ENTER_FINISH
        except HTTPError:
            update.message.reply_text(BotController.PROPOSAL_COORDINATES_INSTEAD_OF_URL)
            return BotController.ENTER_FINISH
        context.chat_data['finish_location'] = l0, l1
        self.add_route(context.chat_data['start_location'], context.chat_data['finish_location'])
        update.message.reply_text(BotController.RESPONSE_ON_SUCCESS)
        return ConversationHandler.END

    def build_report(self, update, context):
        reports = map(self.traffic_scanner.storage.make_report, self.traffic_scanner.storage.get_routes())
        figures = [self.traffic_plotter.plot_traffic(r.timestamps, r.durations) for r in reports]
        if len(figures) == 0:
            update.message.reply_text('No routes')
        for fig in figures:
            with io.BytesIO() as buf:
                fig.savefig(buf, format='png')
                buf.seek(0)
                plot_file = InputFile(buf)
            update.message.reply_photo(plot_file)

    def list_routes(self, update, context):
        routes_df = self.traffic_scanner.storage.get_routes()
        update.message.reply_text(str(routes_df))


def error_callback(update, context):
    if update is not None:
        update.message.reply_text(str(context.error))

    raise context.error


period = 10 * 60
yandex_map_client = YandexMapsClient()
storage = TrafficStorageCSV()
traffic_scanner = TrafficScanner(period=period, yandex_maps_client=yandex_map_client, storage=storage)
traffic_plotter = TrafficView(period * 3)
bc = BotController(traffic_scanner=traffic_scanner,
                   traffic_plotter=traffic_plotter,
                   traffic_parser=None)
updater = Updater(token=
                  # '672100742:AAEC7GTgY32rkDB5mBdYmqxPvO2gXLRREs0',  # prod bot
                  '853266267:AAGw5iNAOrLVMWLjsHcesEFLpS8QfX1fFqA',  # dev bot
                  use_context=True)
dp = updater.dispatcher
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('add', bc.add)],
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

dp.add_handler(CommandHandler('start', bc.start))
dp.add_handler(conv_handler)
dp.add_handler(CommandHandler('report', bc.build_report))
dp.add_handler(CommandHandler('list', bc.list_routes))
dp.add_error_handler(error_callback)


def main():
    dp.run_async(bc.traffic_scanner.serve)
    updater.start_polling()
    updater.idle()
