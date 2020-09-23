import io

import numpy as np
import re
from telegram import InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, ConversationHandler, Filters
import csv
import logging
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from traffic_scanner.traffic_dispatcher import TrafficDispatcher
from traffic_scanner.traffic_view import TrafficView


plt.style.use('fivethirtyeight')

logger = logging.getLogger('traffic_scanner/bot_controller.py')
np.seterr(all="ignore")
logging.basicConfig(level=logging.INFO)

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR


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
