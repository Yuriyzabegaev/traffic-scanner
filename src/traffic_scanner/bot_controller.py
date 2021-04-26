import io
import logging
import re

from matplotlib import pyplot as plt
from requests import get as get_request
from requests.exceptions import MissingSchema, HTTPError
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputFile
from telegram.ext import CommandHandler, MessageHandler, ConversationHandler, Filters, CallbackQueryHandler

from traffic_scanner.traffic_scanner import TrafficScanner
from traffic_scanner.traffic_view import TrafficView

logger = logging.getLogger('traffic_scanner/bot_controller.py')

COORDS_REGEX = re.compile(r'-?\d+\.\d+')
COORDS_FROM_URL_REGEX = re.compile(r'\"point\":[^}]*-?\d+\.\d+')


def cancelable(func):
    def closure(controller, update, context):
        if update.effective_message.text == '/cancel':
            update.effective_message.reply_text(BotController.RESPONSE_ON_CANCEL)
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

    RESPONSE_ON_START = ('''Hello! 🙋‍♂️

I can help you to organize your automobile journey without traffic jams! 😏

How it works?
* You tell me points A and B of your trip 📲
* I scan yandex maps and build you a chart of how long will your route take versus time of day 🚗

To begin, send me a link from yandex maps of the route start

Commands:
/add_route
/routes
''')
    PROPOSAL_ENTER_START = 'Enter start point coordinates or url 🤓'
    PROPOSAL_ENTER_FINISH = 'Now enter finish coordinates 🧐'
    PROPOSAL_COORDINATES_INSTEAD_OF_URL = 'Could you send coordinates please? 🤐'
    PROPOSAL_ENTER_LOCATION_TITLE = 'Now please enter name for this route 🤤'
    RESPONSE_ON_CANCEL = '🆗'
    RESPONSE_ON_SUCCESS = '🆗'
    RESPONSE_ON_FAILURE = 'Not ok 😔'
    RESPONSE_NO_ROUTES = 'No routes 🙌'

    BUTTON_EDIT = 'Edit 🛠'
    BUTTON_SHOW_BY_DAY = 'Show day'

    FAILURE_PARSING_COORDINATES = '''Could not understand your coordinates
 Retry? 🤔
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
            fallbacks=[]
        )

        conversation_rename_route = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.choose_rename_route, pattern=self.CALLBACK_RENAME_ROUTE)
            ],
            states={
                self.ENTER_TITLE: [MessageHandler(Filters.text, self.do_rename_route)]
            },
            fallbacks=[]
        )

        conversation_add_road_back = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.choose_add_road_back, pattern=self.CALLBACK_ADD_ROAD_BACK)
            ],
            states={
                self.ENTER_TITLE: [MessageHandler(Filters.text, self.do_add_road_back)]
            },
            fallbacks=[]
        )

        dispatcher.add_handler(CommandHandler('start', self.start))
        dispatcher.add_handler(CommandHandler('list', self.list_routes))
        dispatcher.add_handler(CommandHandler('routes', self.show_routes))
        dispatcher.add_handler(CommandHandler('add_route', self.add_route))
        dispatcher.add_handler(CallbackQueryHandler(self.choose_route, pattern=self.CALLBACK_SHOW_ROUTES))
        dispatcher.add_handler(CallbackQueryHandler(self.choose_edit, pattern=self.CALLBACK_EDIT_ROUTE))
        dispatcher.add_handler(CallbackQueryHandler(self.choose_delete_route, pattern=self.CALLBACK_DELETE_ROUTE))
        dispatcher.add_handler(CallbackQueryHandler(self.choose_close_edit, pattern=self.CALLBACK_CLOSE_EDIT))

        dispatcher.add_handler(CallbackQueryHandler(self.show_by_day, pattern=self.CALLBACK_SHOW_BY_DAY))
        dispatcher.add_handler(CallbackQueryHandler(self.select_day, pattern=self.CALLBACK_SELECT_DAY))

        dispatcher.add_handler(conversation_rename_route)
        dispatcher.add_handler(conversation_add_road_back)
        dispatcher.add_handler(conversation_add_route)

    '''BOT COMMANDS'''

    @staticmethod
    def start(update, context):
        update.effective_message.reply_text(BotController.RESPONSE_ON_START)

    @staticmethod
    def add_route(update, context):
        update.effective_message.reply_text('Ok, send point A link or coordinates from yandex maps.\n'
                                            'By the way, you may not use this command, just send it anytime 🤪')

    @cancelable
    def enter_start(self, update, context):
        try:
            l1, l0 = parse_coordinates_or_url(update.effective_message.text)
        except ValueError:
            update.effective_message.reply_text(BotController.FAILURE_PARSING_COORDINATES)
            return BotController.ENTER_START
        except HTTPError:
            update.effective_message.reply_text(BotController.PROPOSAL_COORDINATES_INSTEAD_OF_URL)
            return BotController.ENTER_START

        context.chat_data['start_location'] = l0, l1
        update.effective_message.reply_text(self.PROPOSAL_ENTER_FINISH)
        return self.ENTER_FINISH

    @cancelable
    def enter_finish(self, update, context):
        try:
            l1, l0 = parse_coordinates_or_url(update.effective_message.text)
        except ValueError:
            update.effective_message.reply_text(BotController.FAILURE_PARSING_COORDINATES)
            return BotController.ENTER_FINISH
        except HTTPError:
            update.effective_message.reply_text(BotController.PROPOSAL_COORDINATES_INSTEAD_OF_URL)
            return BotController.ENTER_FINISH
        context.chat_data['finish_location'] = l0, l1
        update.effective_message.reply_text(BotController.PROPOSAL_ENTER_LOCATION_TITLE)
        return BotController.ENTER_TITLE

    @cancelable
    def enter_title(self, update, context):
        with self.traffic_scanner.storage.session_scope() as s:
            title = update.effective_message.text
            self.traffic_scanner.add_route(context.chat_data['start_location'],
                                           context.chat_data['finish_location'],
                                           title=title,
                                           user_idx=update.effective_message.from_user.id,
                                           s=s)
        update.effective_message.reply_text(BotController.RESPONSE_ON_SUCCESS)
        return ConversationHandler.END

    def list_routes(self, update, context):
        with self.traffic_scanner.storage.session_scope() as s:
            user_id = update.effective_message.from_user.id
            routes = [route.title for route in self.traffic_scanner.storage.get_routes(user_id, s)]
            update.effective_message.reply_text(str(routes))

    CALLBACK_SHOW_ROUTES = '__show_routes__'

    def show_routes(self, update, context):
        proposal_select_route = 'Select route?'
        with self.traffic_scanner.storage.session_scope() as s:
            user_id = update.effective_message.from_user.id
            routes = [route for route in self.traffic_scanner.storage.get_routes(user_id, s)]
            if len(routes) > 0:
                keyboard = [[InlineKeyboardButton(
                    route.title, callback_data='{}{}'.format(self.CALLBACK_SHOW_ROUTES, route.route_id)
                )] for route in routes]
                update.effective_message.reply_text(proposal_select_route, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                update.effective_message.reply_text(self.RESPONSE_NO_ROUTES)

    CALLBACK_EDIT_ROUTE = '__edit_image__'
    CALLBACK_SHOW_BY_DAY = '__show_by_day__'

    def _get_route_inline_markup(self, route_id):
        return [
            [InlineKeyboardButton(self.BUTTON_EDIT, callback_data=self.CALLBACK_EDIT_ROUTE + str(route_id))],
            [InlineKeyboardButton(self.BUTTON_SHOW_BY_DAY, callback_data=self.CALLBACK_SHOW_BY_DAY + str(route_id))],
        ]

    def choose_route(self, update, context):
        query = update.callback_query
        query.answer()

        route_id = query.data[len(self.CALLBACK_SHOW_ROUTES):]
        user_id = update.effective_user.id
        update.effective_user.send_chat_action('upload_photo')

        with self.traffic_scanner.storage.session_scope() as s:
            route = self.traffic_scanner.storage.get_route(user_id=user_id,
                                                           route_id=route_id,
                                                           s=s)
            if route is None:
                query.edit_message_text(text='Route not found')
                return
            query.edit_message_text(text=route.title)

            report = self.traffic_scanner.storage.make_report(route, s)
            figure = self.traffic_plotter.plot_traffic_minmax(report.timestamps, report.durations,
                                                       report.timezone, report.route.title)
            with io.BytesIO() as buf:
                figure.savefig(buf, format='png')
                buf.seek(0)

                if len(update.effective_message.photo) == 0:
                    plot_file = InputFile(buf)
                    keyboard = self._get_route_inline_markup(route_id)
                    update.effective_message.reply_photo(plot_file, reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    plot_file = InputMediaPhoto(buf)
                    query.edit_message_media(plot_file)
            plt.close(figure)

    CALLBACK_RENAME_ROUTE = '__rename_route__'
    CALLBACK_DELETE_ROUTE = '__delete_route__'
    CALLBACK_CLOSE_EDIT = '__close_edit__'
    CALLBACK_ADD_ROAD_BACK = '__add_road_back__'

    def choose_edit(self, update, context):
        query = update.callback_query
        query.answer()

        route_id = query.data[len(self.CALLBACK_EDIT_ROUTE):]

        keyboard = [
            [InlineKeyboardButton('Rename 🗣', callback_data='{}{}'.format(self.CALLBACK_RENAME_ROUTE, route_id)),
             InlineKeyboardButton('Delete ❌', callback_data='{}{}'.format(self.CALLBACK_DELETE_ROUTE, route_id))],
            [InlineKeyboardButton('Add road back ♻️', callback_data='{}{}'
                                  .format(self.CALLBACK_ADD_ROAD_BACK, route_id)),
             InlineKeyboardButton('🆗', callback_data=self.CALLBACK_CLOSE_EDIT + str(route_id))]
        ]
        query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))

    def choose_rename_route(self, update, context):
        query = update.callback_query
        query.answer()

        route_id = query.data[len(self.CALLBACK_RENAME_ROUTE):]
        context.chat_data['old_route_id'] = route_id

        update.effective_message.reply_text(BotController.PROPOSAL_ENTER_LOCATION_TITLE)
        return self.ENTER_TITLE

    @cancelable
    def do_rename_route(self, update, context):
        new_name = update.effective_message.text
        try:
            route_id = context.chat_data['old_route_id']
        except KeyError:
            update.effective_message.reply_text(self.RESPONSE_ON_FAILURE)
            return ConversationHandler.END
        del context.chat_data['old_route_id']
        with self.traffic_scanner.storage.session_scope() as s:
            self.traffic_scanner.storage.rename_route(user_id=update.effective_message.from_user.id,
                                                      route_id=route_id,
                                                      new_name=new_name,
                                                      s=s)
        update.effective_message.reply_text(self.RESPONSE_ON_SUCCESS)
        return ConversationHandler.END

    def choose_delete_route(self, update, context):
        query = update.callback_query
        query.answer()

        route_id = query.data[len(self.CALLBACK_DELETE_ROUTE):]

        with self.traffic_scanner.storage.session_scope() as s:
            self.traffic_scanner.storage.remove_route(update.effective_user.id, route_id=route_id, s=s)
        query.edit_message_reply_markup(None)
        update.effective_message.reply_text(self.RESPONSE_ON_SUCCESS)

    def choose_close_edit(self, update, context):
        query = update.callback_query
        query.answer()
        keyboard = self._get_route_inline_markup(route_id=None)
        query.edit_message_reply_markup(InlineKeyboardMarkup(keyboard))

    def choose_add_road_back(self, update, context):
        query = update.callback_query
        query.answer()

        route_id = query.data[len(self.CALLBACK_ADD_ROAD_BACK):]
        context.chat_data['forward_route_id'] = route_id

        update.effective_message.reply_text(BotController.PROPOSAL_ENTER_LOCATION_TITLE)
        return self.ENTER_TITLE

    @cancelable
    def do_add_road_back(self, update, context):
        new_route_name = update.effective_message.text
        try:
            forward_route_name = context.chat_data['forward_route_id']
        except KeyError:
            update.effective_message.reply_text(self.RESPONSE_ON_FAILURE)
            return ConversationHandler.END
        del context.chat_data['forward_route_id']
        user_id = update.effective_user.id
        with self.traffic_scanner.storage.session_scope() as s:
            forward_route = self.traffic_scanner.storage.get_route(user_id=user_id,
                                                                   route_id=forward_route_name,
                                                                   s=s)
            if forward_route is not None:
                self.traffic_scanner.add_route(start_coords=forward_route.end_coords,
                                               end_coords=forward_route.start_coords,
                                               user_idx=user_id,
                                               s=s,
                                               title=new_route_name)
        update.effective_message.reply_text(self.RESPONSE_ON_SUCCESS)
        return ConversationHandler.END

    CALLBACK_SELECT_DAY = '__select_day__'
    DAYS = dict(enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']))

    def _get_show_by_day_inline_markup(self, route_id):
        keyboard = [[InlineKeyboardButton(day, callback_data='{}{}__{}'.format(self.CALLBACK_SELECT_DAY, route_id, day_id))] for (day_id, day) in self.DAYS.items()]
        keyboard.append([InlineKeyboardButton('Back', callback_data='{}{}'.format(self.CALLBACK_CLOSE_EDIT, route_id))])
        return keyboard

    def show_by_day(self, update, context):
        query = update.callback_query
        query.answer()
        route_id = query.data[len(self.CALLBACK_SHOW_BY_DAY):]
        
        query.edit_message_reply_markup(InlineKeyboardMarkup(self._get_show_by_day_inline_markup(route_id)))

    def select_day(self, update, context):
        query = update.callback_query
        query.answer()

        route_id = query.data[len(self.CALLBACK_SELECT_DAY):-3]
        day_id = int(query.data[-1])
        
        user_id = update.effective_user.id
        update.effective_user.send_chat_action('upload_photo')

        with self.traffic_scanner.storage.session_scope() as s:
            route = self.traffic_scanner.storage.get_route(user_id=user_id,
                                                           route_id=route_id,
                                                           s=s)
            if route is None:
                return

            report = self.traffic_scanner.storage.make_report_day(route, s, day_id=day_id)
            figure = self.traffic_plotter.plot_traffic_minmax(report.timestamps, report.durations, report.timezone, report.route.title + ': ' + self.DAYS[day_id])
            with io.BytesIO() as buf:
                figure.savefig(buf, format='png')
                buf.seek(0)
                plot_file = InputMediaPhoto(buf)

            query.edit_message_media(plot_file)
            plt.close(figure)

        query.edit_message_reply_markup(InlineKeyboardMarkup(self._get_show_by_day_inline_markup(route_id)))
