import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Tuple, Optional


@dataclass
class User:
    user_id: int
    timezone: Optional[int] = field(default=None)


@dataclass
class Route:
    start_l0: float
    start_l1: float
    end_l0: float
    end_l1: float
    title: str
    user: User

    @property
    def start_coords(self) -> (float, float):
        return self.start_l0, self.start_l1

    @property
    def end_coords(self) -> (float, float):
        return self.end_l0, self.end_l1


@dataclass
class Traffic:
    route: Route
    timestamp: int
    duration_sec: int


@dataclass
class RouteTrafficReport:
    route: Route
    timestamps: Tuple
    durations: Tuple

    @property
    def timezone(self) -> int:
        return self.route.user.timezone or os.environ['TIMEZONE']


class TrafficStorage(ABC):

    @abstractmethod
    def session_scope(self):
        pass

    @abstractmethod
    def get_route(self, user_id, route_id, s) -> Route:
        pass

    @abstractmethod
    def get_routes(self, user_id, s) -> [Route]:
        pass

    @abstractmethod
    def append_traffic(self, route: Route, duration_sec, s) -> None:
        pass

    @abstractmethod
    def add_route(self, start_coords, end_coords, title, user_id, s) -> Route:
        pass

    @abstractmethod
    def remove_route(self, user_id, route_id, s) -> None:
        pass

    @abstractmethod
    def make_report(self, route, s) -> RouteTrafficReport:
        pass

    @abstractmethod
    def update_user(self, user: User, s) -> None:
        pass

    @abstractmethod
    def rename_route(self, user_id, route_id: str, new_name: str, s) -> None:
        pass
