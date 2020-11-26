import csv
import re
import time
from contextlib import contextmanager
from itertools import count
from pathlib import Path

import pandas as pd

from traffic_scanner.storage.model import User, Route, RouteTrafficReport, TrafficStorage

COORDS_REGEX = re.compile(r'-?\d+\.\d+')


def validate_exists(p: Path):
    if not p.exists():
        with p.open('w'):
            pass
    return p


class TrafficStorageCSV(TrafficStorage):
    TRAFFIC_FIELDS = ['timestamp', 'duration_sec']
    ROUTES_FIELDS = ['title', 'start_coords', 'end_coords', 'user_id']
    USERS_FIELDS = ['user_id', 'time_zone']

    def __init__(self, routes_filename='routes.csv', traffic_filename='traffic.csv', users_filename='users.csv'):
        self.routes_path = validate_exists(Path(routes_filename))
        self.traffic_path = validate_exists(Path(traffic_filename))
        self.users_path = validate_exists(Path(users_filename))
        self.free_indices = count(len(pd.read_csv(self.routes_path)))

    def get_routes(self, user_id, s):
        df = pd.read_csv(self.routes_path)
        routes = []
        if user_id is not None:
            df = df[df['user_id'] == user_id]
        for _, row in df.iterrows():
            start_coords = COORDS_REGEX.findall(row['start_coords'])
            end_coords = COORDS_REGEX.findall(row['end_coords'])
            routes.append(Route(start_l0=float(start_coords[0]),
                                start_l1=float(start_coords[1]),
                                end_l0=float(end_coords[0]),
                                end_l1=float(end_coords[1]),
                                title=row['title'],
                                user=User(user_id=user_id, timezone=None)))
        return tuple(routes)

    def append_traffic(self, route: Route, duration_sec, s):
        with self.traffic_path.open('a') as f:
            writer = csv.DictWriter(f, TrafficStorageCSV.TRAFFIC_FIELDS)
            writer.writerow(dict(
                timestamp=int(time.time()),
                duration_sec=int(duration_sec)
            ))

    def add_route(self, start_coords, end_coords, title, user_id, s) -> Route:
        user_df = pd.read_csv(self.users_path)
        user_df = user_df[user_df['user_id'] == user_id]
        user = User(user_id=user_df['user_id'].values[0], timezone=user_df['time_zone'].values[0])
        route = Route(start_l0=start_coords[0],
                      start_l1=start_coords[1],
                      end_l0=end_coords[0],
                      end_l1=end_coords[1],
                      title=title,
                      user=user)
        with self.routes_path.open('a') as f:
            writer = csv.DictWriter(f, TrafficStorageCSV.ROUTES_FIELDS)
            writer.writerow(dict(
                title=route.title,
                start_coords=route.start_coords,
                end_coords=route.end_coords,
                user_id=route.user.user_id,
            ))
        return route

    def remove_route(self, route, s):
        assert route.idx is not None
        routes_df = pd.read_csv(self.routes_path)
        routes_df.drop(routes_df['route_id'] == route.idx)
        routes_df.to_csv(self.routes_path, index=False)

    def make_report(self, route, s):
        df = pd.read_csv(self.traffic_path)

        route_df = df[df['route_id'] == route.idx]
        timestamps = route_df['timestamp'].tolist()
        durations = route_df['duration_sec'].tolist()
        return RouteTrafficReport(
            route=route,
            timestamps=timestamps,
            durations=durations,
            )

    def update_user(self, user, s):
        users_df = pd.read_csv(self.users_path)
        user_in_df = users_df[users_df['user_id'] == user.user_id]
        if len(user_in_df) == 0:
            with self.users_path.open('a') as f:
                writer = csv.DictWriter(f, TrafficStorageCSV.USERS_FIELDS)
                writer.writerow(dict(
                    user_id=user.user_id,
                    time_zone=user.timezone
                ))

    @contextmanager
    def session_scope(self):
        yield None
