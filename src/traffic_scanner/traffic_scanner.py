import logging
import time

from traffic_scanner.storage import TrafficStorage, Route, User
from traffic_scanner.yandex_maps_client import YandexMapsClient


logger = logging.getLogger('traffic_scanner/traffic_scanner.py')


class TrafficScanner:

    def __init__(self, period, yandex_maps_client: YandexMapsClient, storage: TrafficStorage):
        self.period: int = period
        self.storage: TrafficStorage = storage
        self.yandex_maps_client: YandexMapsClient = yandex_maps_client

    def add_route(self, start_coords, end_coords, user_idx, s, title=None):
        title = title or f'{start_coords} -> {end_coords}'
        route = self.storage.add_route(start_coords, end_coords, title, user_idx, s)
        self.scan_route(route, s)

    def update_traffic(self, s):
        routes = self.storage.get_routes(user_id=None, s=s)
        for route in routes:
            self.scan_route(route, s)

    def scan_route(self, route, s):
        traffic_json = self.yandex_maps_client.build_route(route.start_coords, route.end_coords)
        try:
            routes = traffic_json['data']['routes']
            if len(routes) > 0:  # TODO: Is [0] the quickest?
                duration_sec = routes[0]['durationInTraffic']
            else:
                logger.error(f'On route {route.idx} 0 available ways were found.')
                return
        except KeyError as e:
            logger.error(f'Invalid json: {traffic_json}')
            raise e
        logger.info(f'Duration: {duration_sec}')
        self.storage.append_traffic(route, duration_sec=duration_sec, s=s)

    def serve(self):
        logger.info('Start serving.')
        while True:
            t0 = time.time()
            sleep_time = max(self.period - (time.time() - t0), 0)
            logger.info(f'Sleeping for {sleep_time} seconds.')
            time.sleep(sleep_time)
            with self.storage.session_scope() as s:
                self.update_traffic(s)
