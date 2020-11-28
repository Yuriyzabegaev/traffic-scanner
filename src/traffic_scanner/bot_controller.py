import io
import logging
import re

from requests import get as get_request
from requests.exceptions import MissingSchema, HTTPError
from telegram import InputFile
from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, Filters

from traffic_scanner.traffic_scanner import TrafficScanner
from traffic_scanner.traffic_view import TrafficView

logger = logging.getLogger('traffic_scanner/bot_controller.py')


COORDS_REGEX = re.compile(r'-?\d+\.\d+')
COORDS_FROM_URL_REGEX = re.compile(r'\"point\":[^}]*-?\d+\.\d+')


def cancelable(func):

    def closure(controller, update, context):
        if update.message.text == '/cancel':
            update.message.reply_text(BotController.RESPONSE_ON_CANCEL)
            return ConversationHandler.END
        return func(controller, update, context)

    return closure


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
        swap_result = True
    except MissingSchema:
        # This is not an url, user sent coordinates
        coords_string = input_str
        swap_result = False

    coords = COORDS_REGEX.findall(coords_string)

    if len(coords) < 2:
        raise ValueError('Could not find l0 and l1 in coordinates regex')
    if swap_result:
        return float(coords[1]), float(coords[0])
    else:
        return float(coords[0]), float(coords[1])


class BotController:

    ENTER_START, ENTER_FINISH, ENTER_TITLE = range(3)

    RESPONSE_ON_START = ('''Hello!

Commands:
/list
/report
''')
    PROPOSAL_ENTER_START = 'Enter start point coordinates or url'
    PROPOSAL_COORDINATES_INSTEAD_OF_URL = 'Could you send coordinates please?'
    PROPOSAL_ENTER_LOCATION_TITLE = 'Now please enter name for this route'
    RESPONSE_ON_CANCEL = 'Ok'
    RESPONSE_ON_SUCCESS = 'Ok'
    FAILURE_PARSING_COORDINATES = '''Could not understand your coordinates
 Retry?
 Please, send coordinates or link from Yandex maps
 '''

    def __init__(self, traffic_scanner, traffic_plotter):
        self.traffic_scanner: TrafficScanner = traffic_scanner
        self.traffic_plotter: TrafficView = traffic_plotter

    def initialize_dispatcher(self, dispatcher):
        conversation_handler = ConversationHandler(
            entry_points=[MessageHandler(
                Filters.text,
                self.enter_start)],
            states={
                self.ENTER_START: [MessageHandler(
                    Filters.text,
                    self.enter_start)],
                self.ENTER_FINISH: [MessageHandler(
                    Filters.text,
                    self.enter_finish)],
                self.ENTER_TITLE: [MessageHandler(
                    Filters.text,
                    self.enter_title)]
            },
            fallbacks=[]
        )

        dispatcher.add_handler(CommandHandler('start', self.start))
        dispatcher.add_handler(CommandHandler('report', self.build_report))
        dispatcher.add_handler(CommandHandler('list', self.list_routes))
        dispatcher.add_handler(conversation_handler)

    '''BOT COMMANDS'''

    def remove_route(self, route):
        with self.traffic_scanner.storage.session_scope() as s:
            self.traffic_scanner.storage.remove_route(route, s)

    @staticmethod
    def start(update, context):
        update.message.reply_text(BotController.RESPONSE_ON_START)

    @cancelable
    def enter_start(self, update, context):
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

    @cancelable
    def enter_finish(self, update, context):
        try:
            l1, l0 = parse_coordinates_or_url(update.message.text)
        except ValueError:
            update.message.reply_text(BotController.FAILURE_PARSING_COORDINATES)
            return BotController.ENTER_FINISH
        except HTTPError:
            update.message.reply_text(BotController.PROPOSAL_COORDINATES_INSTEAD_OF_URL)
            return BotController.ENTER_FINISH
        context.chat_data['finish_location'] = l0, l1
        update.message.reply_text(BotController.PROPOSAL_ENTER_LOCATION_TITLE)
        return BotController.ENTER_TITLE

    @cancelable
    def enter_title(self, update, context):
        with self.traffic_scanner.storage.session_scope() as s:
            title = update.message.text
            self.traffic_scanner.add_route(context.chat_data['start_location'],
                                           context.chat_data['finish_location'],
                                           title=title,
                                           user_idx=update.message.from_user.id,
                                           s=s)
        update.message.reply_text(BotController.RESPONSE_ON_SUCCESS)
        return ConversationHandler.END

    def build_report(self, update, context):
        with self.traffic_scanner.storage.session_scope() as s:
            user_id = update.message.from_user.id
            reports = (self.traffic_scanner.storage.make_report(r, s)
                       for r in self.traffic_scanner.storage.get_routes(user_id, s))
            figures = [self.traffic_plotter.plot_traffic(r.timestamps, r.durations, r.timezone, r.route.title)
                       for r in reports
                       if len(r.timestamps) > 0]
            if len(figures) == 0:
                update.message.reply_text('No routes')
            for fig in figures:
                with io.BytesIO() as buf:
                    fig.savefig(buf, format='png')
                    buf.seek(0)
                    plot_file = InputFile(buf)
                update.message.reply_photo(plot_file)

    def list_routes(self, update, context):
        with self.traffic_scanner.storage.session_scope() as s:
            user_id = update.message.from_user.id
            routes = [route.title for route in self.traffic_scanner.storage.get_routes(user_id, s)]
            update.message.reply_text(str(routes))
