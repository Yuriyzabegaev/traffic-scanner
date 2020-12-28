import io
import logging
import re

from matplotlib import pyplot as plt
from requests import get as get_request
from requests.exceptions import MissingSchema, HTTPError
from telegram import InputFile, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, Filters, CallbackQueryHandler

from traffic_scanner.traffic_scanner import TrafficScanner
from traffic_scanner.traffic_view import TrafficView

logger = logging.getLogger('traffic_scanner/bot_controller.py')


COORDS_REGEX = re.compile(r'-?\d+\.\d+')
COORDS_FROM_URL_REGEX = re.compile(r'\"point\":[^}]*-?\d+\.\d+')


def cancelable(func):

    def closure(controller, update, context):
        # if update.message.text == '/cancel':
        #     update.message.reply_text(BotController.RESPONSE_ON_CANCEL)
        #     return ConversationHandler.END
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

New commands:
/routes
''')
    PROPOSAL_ENTER_START = 'Enter start point coordinates or url'
    PROPOSAL_COORDINATES_INSTEAD_OF_URL = 'Could you send coordinates please?'
    PROPOSAL_ENTER_LOCATION_TITLE = 'Now please enter name for this route'
    RESPONSE_ON_CANCEL = 'Ok'
    RESPONSE_ON_SUCCESS = 'Ok'
    RESPONSE_ON_FAILURE = 'Not ok('
    FAILURE_PARSING_COORDINATES = '''Could not understand your coordinates
 Retry?
 Please, send coordinates or link from Yandex maps
 '''

    def __init__(self, traffic_scanner, traffic_plotter):
        self.traffic_scanner: TrafficScanner = traffic_scanner
        self.traffic_plotter: TrafficView = traffic_plotter

    def initialize_dispatcher(self, dispatcher):
        conversation_add_route = ConversationHandler(
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
            fallbacks=[
                CommandHandler('cancel', self.cancel)
            ]
        )

        conversation_rename_route = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.choose_rename_route, pattern=self.RENAME_ROUTE_PREFIX)
            ],
            states={
                self.ENTER_TITLE: [MessageHandler(Filters.text, self.do_rename_route)]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel)
            ]
        )

        dispatcher.add_handler(CommandHandler('start', self.start))
        dispatcher.add_handler(CommandHandler('report', self.build_report))
        dispatcher.add_handler(CommandHandler('list', self.list_routes))
        dispatcher.add_handler(CommandHandler('routes', self.show_routes))
        dispatcher.add_handler(CallbackQueryHandler(self.choose_route, pattern=self.SHOW_ROUTES_CALLBACK_PREFIX))
        dispatcher.add_handler(CallbackQueryHandler(self.choose_edit, pattern=self.EDIT_ROUTE_PREFIX))
        dispatcher.add_handler(conversation_rename_route)
        dispatcher.add_handler(conversation_add_route)

    '''BOT COMMANDS'''

    def cancel(self, update, context):
        update.message.reply_text(BotController.RESPONSE_ON_CANCEL)

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
                plt.close(fig)

    def list_routes(self, update, context):
        with self.traffic_scanner.storage.session_scope() as s:
            user_id = update.message.from_user.id
            routes = [route.title for route in self.traffic_scanner.storage.get_routes(user_id, s)]
            update.message.reply_text(str(routes))

    SHOW_ROUTES_CALLBACK_PREFIX = '__show_routes__'

    def show_routes(self, update, context):
        proposal_select_route = 'Select route?'
        with self.traffic_scanner.storage.session_scope() as s:
            user_id = update.message.from_user.id
            routes = [route.title for route in self.traffic_scanner.storage.get_routes(user_id, s)]
            keyboard = [[InlineKeyboardButton(
                route, callback_data='{}{}'.format(self.SHOW_ROUTES_CALLBACK_PREFIX, route)
            )] for route in routes]
            update.message.reply_text(proposal_select_route, reply_markup=InlineKeyboardMarkup(keyboard))

    EDIT_ROUTE_PREFIX = '__edit_image__'

    def choose_route(self, update, context):
        query = update.callback_query
        query.answer()

        effective_data = query.data.removeprefix(self.SHOW_ROUTES_CALLBACK_PREFIX)
        context.chat_data['route_name'] = effective_data
        query.edit_message_text(text=effective_data)
        user_id = update.effective_user.id
        update.effective_user.send_chat_action('upload_photo')

        with self.traffic_scanner.storage.session_scope() as s:
            route = self.traffic_scanner.storage.get_route(user_id=user_id,
                                                           route_title=effective_data,
                                                           s=s)
            if route is None:
                return

            report = self.traffic_scanner.storage.make_report(route, s)
            figure = self.traffic_plotter.plot_traffic(report.timestamps, report.durations,
                                                       report.timezone, report.route.title)
            with io.BytesIO() as buf:
                figure.savefig(buf, format='png')
                buf.seek(0)
                plot_file = InputFile(buf)

            keyboard = [[InlineKeyboardButton('Edit', callback_data=self.EDIT_ROUTE_PREFIX)]]
            update.effective_message.reply_photo(plot_file, reply_markup=InlineKeyboardMarkup(keyboard))
            plt.close(figure)

    RENAME_ROUTE_PREFIX = '__rename_route__'
    DELETE_ROUTE_PREFIX = '__delete_route__'
    CLOSE_EDIT_PREFIX = '__close_edit__'

    def choose_edit(self, update, context):
        query = update.callback_query
        query.answer()

        keyboard = [[InlineKeyboardButton('Rename', callback_data=self.RENAME_ROUTE_PREFIX),
                     InlineKeyboardButton('Delete', callback_data=self.DELETE_ROUTE_PREFIX),
                     InlineKeyboardButton('Ok', callback_data=self.CLOSE_EDIT_PREFIX)]]
        query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))

    def choose_rename_route(self, update, context):
        query = update.callback_query
        query.answer()
        update.effective_message.reply_text(BotController.PROPOSAL_ENTER_LOCATION_TITLE)
        return self.ENTER_TITLE

    def do_rename_route(self, update, context):
        new_name = update.message.text
        try:
            old_name = context.chat_data['route_name']
        except KeyError:
            update.message.reply_text(self.RESPONSE_ON_FAILURE)
            return ConversationHandler.END
        with self.traffic_scanner.storage.session_scope() as s:
            self.traffic_scanner.storage.rename_route(user_id=update.message.from_user.id,
                                                      old_name=old_name,
                                                      new_name=new_name,
                                                      s=s)
        update.message.reply_text(self.RESPONSE_ON_SUCCESS)
        return ConversationHandler.END
