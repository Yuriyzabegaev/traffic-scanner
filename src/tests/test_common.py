import unittest

from traffic_scanner.bot_controller import *


class TestParseCoordinates(unittest.TestCase):

    def test_common(self):
        user_id = 1829
        yandex_map_client.update_session()
        with storage.session_scope() as s:
            bc.traffic_scanner.storage.update_user(User(user_id=user_id, timezone=+3), s)
            bc.traffic_scanner.add_route((37.5229855552, 55.9271870459),
                                         (37.4460039634, 55.8852399212964),
                                         title='Долгопрудный -> Москва',
                                         user_idx=user_id, s=s)
