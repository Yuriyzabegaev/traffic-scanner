from itertools import count
import time
from abc import ABC, abstractmethod
import csv
from typing import List
import re
from dataclasses import dataclass, field

import pandas as pd
from pathlib import Path


COORDS_REGEX = re.compile(r'-?\d+\.\d+')


@dataclass
class Route:
    start_coords: [float, float]
    end_coords: [float, float]
    title: str
    idx: int = field(default=None)
    user_idx: int = field(default=None)


@dataclass
class RouteTrafficReport:
    route: Route
    timestamps: List
    durations: List
    timezone: int


@dataclass
class User:
    timezone: int
    user_idx: int


class TrafficStorage(ABC):

    @abstractmethod
    def get_routes(self) -> [str]:
        pass

    @abstractmethod
    def append_traffic(self, route, duration_sec) -> None:
        pass

    @abstractmethod
    def add_route(self, route: Route) -> None:
        pass

    @abstractmethod
    def remove_route(self, route) -> None:
        pass

    @abstractmethod
    def make_report(self, route) -> RouteTrafficReport:
        pass

    @abstractmethod
    def update_user(self, user: User) -> None:
        pass


def validate_exists(p: Path):
    if not p.exists():
        with p.open('w'):
            pass
    return p


class TrafficStorageCSV(TrafficStorage):
    TRAFFIC_FIELDS = ['route_id', 'timestamp', 'duration_sec']
    ROUTES_FIELDS = ['route_id', 'title', 'start_coords', 'end_coords', 'user_id']
    USERS_FIELDS = ['user_id', 'time_zone']

    def __init__(self, routes_filename='routes.csv', traffic_filename='traffic.csv', users_filename='users.csv'):
        self.routes_path = validate_exists(Path(routes_filename))
        self.traffic_path = validate_exists(Path(traffic_filename))
        self.users_path = validate_exists(Path(users_filename))
        self.free_indices = count(len(pd.read_csv(self.routes_path)))

    def get_routes(self):
        df = pd.read_csv(self.routes_path)
        routes = []
        for _, row in df.iterrows():
            start_coords = COORDS_REGEX.findall(row['start_coords'])
            end_coords = COORDS_REGEX.findall(row['end_coords'])
            routes.append(Route(start_coords=start_coords, end_coords=end_coords,
                                title=row['title'], idx=row['route_id'], user_idx=row['user_id']))
        return tuple(routes)

    def append_traffic(self, route: Route, duration_sec):
        assert route.idx is not None
        with self.traffic_path.open('a') as f:
            writer = csv.DictWriter(f, TrafficStorageCSV.TRAFFIC_FIELDS)
            writer.writerow(dict(
                route_id=route.idx,
                timestamp=int(time.time()),
                duration_sec=int(duration_sec)
            ))

    def add_route(self, route):
        route.idx = next(self.free_indices)
        with self.routes_path.open('a') as f:
            writer = csv.DictWriter(f, TrafficStorageCSV.ROUTES_FIELDS)
            writer.writerow(dict(
                route_id=route.idx,
                title=route.title,
                start_coords=route.start_coords,
                end_coords=route.end_coords,
                user_id=route.user_idx,
            ))

    def remove_route(self, route):
        assert route.idx is not None
        routes_df = pd.read_csv(self.routes_path)
        routes_df.drop(routes_df['route_id'] == route.idx)
        routes_df.to_csv(self.routes_path, index=False)

    def make_report(self, route):
        df = pd.read_csv(self.traffic_path)
        users_df = pd.read_csv(self.users_path)

        route_df = df[df['route_id'] == route.idx]
        timestamps = route_df['timestamp'].tolist()
        durations = route_df['duration_sec'].tolist()
        timezone = users_df[users_df['user_id'] == 91945569]['time_zone'][0]
        return RouteTrafficReport(route=route,
                                  timestamps=timestamps,
                                  durations=durations,
                                  timezone=timezone)

    def update_user(self, user):
        users_df = pd.read_csv(self.users_path)
        user_in_df = users_df[users_df['user_id'] == user.user_idx]
        if len(user_in_df) == 0:
            with self.users_path.open('a') as f:
                writer = csv.DictWriter(f, TrafficStorageCSV.USERS_FIELDS)
                writer.writerow(dict(
                    user_id=user.user_idx,
                    time_zone=user.timezone
                ))
