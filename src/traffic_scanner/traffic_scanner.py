import logging
import time

from traffic_scanner.storage import TrafficStorage
from traffic_scanner.yandex_maps_client import YandexMapsClient


logger = logging.getLogger('traffic_scanner/traffic_scanner.py')


class TrafficScanner:

    def __init__(self, period, yandex_maps_client: YandexMapsClient, storage: TrafficStorage):
        self.period = period
        self.storage = storage
        self.yandex_maps_client = yandex_maps_client

    def update_traffic(self):
        self.yandex_maps_client.update_session()
        routes = self.storage.get_routes()
        for route in routes:
            self.scan_route(route)

    def scan_route(self, route):
        traffic_json = self.yandex_maps_client.build_route(route)
        try:
            routes = traffic_json['data']['routes']
            if len(routes) > 0:  # TODO: Is [0] the quickest?
                duration_sec = routes[0]['durationInTraffic']
            else:
                logger.error(f'On route {route} 0 available ways were found.')
                duration_sec = None  # TODO: Handle this
        except KeyError as e:
            logger.error(f'Invalid json: {traffic_json}')
            raise e
        logger.info(f'Duration: {duration_sec}')
        self.storage.append_traffic(route, duration_sec)

    def serve(self):
        logger.info('Start serving.')
        while True:
            t0 = time.time()
            self.update_traffic()
            sleep_time = max(self.period - (time.time() - t0), 0)
            logger.info(f'Sleeping for {sleep_time} seconds.')
            time.sleep(sleep_time)
