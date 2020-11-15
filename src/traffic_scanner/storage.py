import datetime
import time
from abc import ABC, abstractmethod
import csv

import pandas as pd
from pathlib import Path


class RouteTrafficReport:

    def __init__(self, route, timestamps, durations):
        self.route = route
        self.timestamps = timestamps
        self.durations = durations


class TrafficStorage(ABC):

    @abstractmethod
    def get_routes(self) -> [str]:
        pass

    @abstractmethod
    def append_traffic(self, route, duration_sec) -> None:
        pass

    @abstractmethod
    def add_route(self, route) -> None:
        pass

    @abstractmethod
    def remove_route(self, route) -> None:
        pass

    @abstractmethod
    def make_report(self, route) -> RouteTrafficReport:
        pass


def validate_exists(p: Path):
    if not p.exists():
        with p.open('w'):
            pass
    return p


class TrafficStorageCSV(TrafficStorage):

    def __init__(self, routes_filename='routes.csv', traffic_filename='traffic.csv'):
        self.routes_path = validate_exists(Path(routes_filename))
        self.traffic_path = validate_exists(Path(traffic_filename))

    def get_routes(self):
        return pd.read_csv(self.routes_path)['route'].tolist()

    def append_traffic(self, route, duration_sec):
        with self.traffic_path.open('a') as f:
            writer = csv.writer(f)
            writer.writerow([route, datetime.datetime.fromtimestamp(time.time()), duration_sec])

    def add_route(self, route):
        with self.routes_path.open('a') as f:
            writer = csv.DictWriter(f, ['route', 'user_id'])
            writer.writerow({'route': route, 'user_id': None})

    def remove_route(self, route):
        routes_df = pd.read_csv(self.routes_path)
        routes_df.drop(routes_df['route'] == route)
        routes_df.to_csv(self.routes_path, index=False)

    def make_report(self, route):
        df = pd.read_csv(self.traffic_path)

        route_df = df[df['coords'] == route]
        timestamps = route_df['timestamp'].tolist()
        durations = route_df['duration'].tolist()
        return RouteTrafficReport(route=route,
                                  timestamps=timestamps,
                                  durations=durations)
