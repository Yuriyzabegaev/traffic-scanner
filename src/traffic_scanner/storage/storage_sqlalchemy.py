import time
from contextlib import contextmanager

from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, Float
from sqlalchemy import create_engine
from sqlalchemy.orm import mapper, relationship, sessionmaker

from traffic_scanner.storage import User, Route, RouteTrafficReport, TrafficStorage, Traffic

MAX_SYMBOLS_IN_STRING = 50

metadata = MetaData()

users_table = Table(
    'users', metadata,
    Column('user_id', Integer, primary_key=True),
    Column('timezone', Integer, nullable=True),
)

routes_table = Table(
    'routes', metadata,
    Column('route_id', Integer, primary_key=True),
    Column('title', String(MAX_SYMBOLS_IN_STRING)),
    Column('start_l0', Float),
    Column('start_l1', Float),
    Column('end_l0', Float),
    Column('end_l1', Float),
    Column('user_id', Integer, ForeignKey('users.user_id'))
)

traffic_table = Table(
    'traffic', metadata,
    Column('traffic_id', Integer, primary_key=True),
    Column('route_id', Integer, ForeignKey('routes.route_id')),
    Column('timestamp', Integer),
    Column('duration_sec', Integer)
)

mapper(User, users_table)
mapper(Route, routes_table, properties={'user': relationship(User, backref='routes')})
mapper(Traffic, traffic_table, properties={'route': relationship(Route, backref='traffic')})

Session = sessionmaker()


class TrafficStorageSQL(TrafficStorage):

    def __init__(self, db_url):
        engine = create_engine(db_url, echo=False)
        metadata.create_all(engine)
        Session.configure(bind=engine)

    @contextmanager
    def session_scope(self):
        session = Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def get_routes(self, user_id, s) -> [Route]:
        routes_query = s.query(Route)
        if user_id is None:
            return routes_query.all()
        return routes_query.filter_by(user_id=user_id).all()

    def append_traffic(self, route, duration_sec, s) -> None:
        s.add(Traffic(route=route, timestamp=int(time.time()), duration_sec=duration_sec))

    def add_route(self, start_coords, end_coords, title, user_id, s) -> Route:
        user = s.query(User).filter_by(user_id=user_id).first()
        if user is None:
            user = User(user_id=user_id, timezone=None)
            self.update_user(user, s)
        route = Route(start_l0=start_coords[0],
                      start_l1=start_coords[1],
                      end_l0=end_coords[0],
                      end_l1=end_coords[1],
                      title=title,
                      user=user)
        s.add(route)
        return route

    def remove_route(self, route, s) -> None:
        s.delete(route)

    def make_report(self, route, s) -> RouteTrafficReport:
        traffic_report = s.query(Traffic).filter_by(route=route)
        traffic_entities: [Traffic] = traffic_report.all()
        return RouteTrafficReport(route=route,
                                  timestamps=tuple(map(lambda x: x.timestamp, traffic_entities)),
                                  durations=tuple(map(lambda x: x.duration_sec, traffic_entities)))

    def update_user(self, user: User, s) -> None:
        s.merge(user)
