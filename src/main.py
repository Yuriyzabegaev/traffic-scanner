import logging
import os
import traceback

import numpy
from telegram.ext import Updater

from traffic_scanner.bot_controller import BotController
from traffic_scanner.storage import TrafficStorageSQL
from traffic_scanner.traffic_scanner import TrafficScanner
from traffic_scanner.traffic_view import TrafficView
from traffic_scanner.yandex_maps_client import YandexMapsClient


def error_callback(update, context):
    update.effective_message.reply_text(str(context.error))
    update.effective_message.reply_text(traceback.format_exc())
    raise context.error


numpy.seterr(all="ignore")
logging.basicConfig(level=logging.INFO)

period = 10 * 60
yandex_map_client = YandexMapsClient()
yandex_map_client.update_session()

storage = TrafficStorageSQL(db_url=os.environ.get('DATABASE_URL', 'sqlite:///:memory:'))
traffic_scanner = TrafficScanner(period=period, yandex_maps_client=yandex_map_client, storage=storage)
traffic_plotter = TrafficView(period)
bc = BotController(traffic_scanner=traffic_scanner,
                   traffic_plotter=traffic_plotter)
updater = Updater(token=os.environ['TELEGRAM_BOT_TOKEN'])

dp = updater.dispatcher
bc.initialize_dispatcher(dp)
dp.add_error_handler(error_callback)

if __name__ == '__main__':
    dp.run_async(bc.traffic_scanner.serve_restart)
    updater.start_polling()
    updater.idle()
