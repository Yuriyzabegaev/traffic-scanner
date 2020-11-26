import unittest
import time

from traffic_scanner.bot_controller import parse_coordinates_or_url


class TestParseCoordinates(unittest.TestCase):

    def test_parse_coordinates_or_url(self):
        l0, l1 = parse_coordinates_or_url('37.5229855552,55.9271870459')
        assert l0 == 55.9271870459 and l1 == 37.5229855552

        l0, l1 = parse_coordinates_or_url('37.5229855552, 55.9271870459')
        assert l0 == 55.9271870459 and l1 == 37.5229855552

        l0, l1 = parse_coordinates_or_url('37.5229855552,  55.9271870459')
        assert l0 == 55.9271870459 and l1 == 37.5229855552

        l0, l1 = parse_coordinates_or_url('https://yandex.ru/maps/org/obshchezhitiye_mfti_9/1938940848/')
        assert l0 == 55.9271870459 and l1 == 37.5229855552

        time.sleep(0.01)
        l0, l1 = parse_coordinates_or_url('https://yandex.ru/maps/org/obshchezhitiye_mfti_9/1938940848/')
        assert l0 == 55.9271870459 and l1 == 37.5229855552

        time.sleep(0.01)
        l0, l1 = parse_coordinates_or_url('https://yandex.ru/maps/-/CCUAFNhf2A')
        assert l0 == 55.9239846487 and l1 == 37.5246040482

        time.sleep(0.01)
        l0, l1 = parse_coordinates_or_url('https://yandex.ru/maps/-/CCUAFNtr1C')
        assert l0 == 55.923751 and l1 == 37.525851
