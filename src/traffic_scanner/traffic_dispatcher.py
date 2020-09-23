import csv
import datetime
import logging
import time

from traffic_scanner.yandex_maps_client import YandexMapsClient


logger = logging.getLogger('traffic_scanner/traffic_dispatcher.py')


class RouteHandler:

    def __init__(self, yandex_maps_client, coords, filename):
        self.filename = filename
        self.coords = coords
        self.y = yandex_maps_client

    def update_traffic(self):
        t = time.time()
        traffic_json = self.y.build_route(self.coords)
        try:
            routes = traffic_json['data']['routes']
            if len(routes) > 0:  # TODO: Is [0] the quickest?
                duration_sec = routes[0]['durationInTraffic']
            else:
                logger.error(f'On route {self.coords} 0 available ways were found.')
                duration_sec = None  # TODO: Handle this
        except KeyError as e:
            logger.error(f'Invalid json: {traffic_json}')
            raise e
        logger.info(f'Duration: {duration_sec}')
        self.write_traffic(t, duration_sec)

    def write_traffic(self, t, duration):
        with open(self.filename, 'a') as f:
            writer = csv.writer(f)
            writer.writerow([self.coords, datetime.datetime.fromtimestamp(t), duration])


class TrafficDispatcher:

    def __init__(self, period, routes, filename='traffic.csv'):
        self.period = period
        self.filename = filename
        self.y = YandexMapsClient()
        self.routes = [RouteHandler(self.y, coords, filename=filename) for coords in routes]

    def update_traffic(self):
        self.y.update_session()
        for route in self.routes:
            route.update_traffic()

    def serve(self):
        logger.info('Start serving.')
        while True:
            t0 = time.time()
            self.update_traffic()
            sleep_time = max(self.period - (time.time() - t0), 0)
            logger.info(f'Sleeping for {sleep_time} seconds.')
            time.sleep(sleep_time)

    def add_route(self, route):
        self.routes.append((RouteHandler(self.y, coords=route, filename=self.filename)))

    def remove_route(self, route):
        self.routes.remove(route)