import unittest

from traffic_scanner.storage import User
from traffic_scanner.storage.storage_sqlalchemy import TrafficStorageSQL
from traffic_scanner.traffic_scanner import TrafficScanner
from traffic_scanner.yandex_maps_client import YandexMapsClient


class TestParseCoordinates(unittest.TestCase):

    def test_common(self):
        user_id = 1829
        yandex_map_client = YandexMapsClient()
        storage = TrafficStorageSQL(db_url='sqlite:///_db_test')
        traffic_scanner = TrafficScanner(period=600, yandex_maps_client=yandex_map_client, storage=storage)

        with storage.session_scope() as s:
            traffic_scanner.storage.update_user(User(user_id=user_id, timezone=+3), s)
            traffic_scanner.add_route((37.5229855552, 55.9271870459),
                                      (37.4460039634, 55.8852399212964),
                                      title='Долгопрудный -> Москва',
                                      user_idx=user_id, s=s)
