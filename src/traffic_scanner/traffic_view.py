import datetime
import logging
import math
import time

import numpy as np
from matplotlib import pyplot as plt, dates as md

plt.rcParams.update(plt.rcParamsDefault)
plt.style.use([
    'dark_background',
    # 'seaborn-pastel',
    # 'seaborn-darkgrid',
    # 'seaborn'
])
plt.rcParams.update({'figure.figsize': [12, 4]})

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR

logger = logging.getLogger('traffic_scanner/traffic_view.py')

DAYS_OF_WEEK = 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'


class TrafficView:

    def __init__(self, period):
        assert period < 24 * 60 * 60
        self.num_time_intervals = math.ceil(DAY / period)
        self.timedelta = period

    def plot_traffic(self, timestamps, durations, timezone, route_name):
        durations, nonzero_intervals = sort_days_intervals(np.array(timestamps) + timezone * HOUR,
                                                           durations,
                                                           self.timedelta)

        fig = plt.figure()
        ax = fig.gca()
        for day_idx, day in enumerate(DAYS_OF_WEEK):
            nonzero_intervals_day = np.array(nonzero_intervals[day_idx]) * self.timedelta
            if len(nonzero_intervals_day) == 0:
                continue
            durations_day = tuple(map(int, map(np.mean, durations[day_idx])))
            if np.max(durations_day) <= DAY:
                y_labels = tuple(map(datetime.datetime.utcfromtimestamp, durations_day))
                ax.yaxis.set_major_formatter(md.DateFormatter('%H:%M'))
            else:
                y_labels = [ts / HOUR for ts in durations_day]
                ax.set_ylabel('Hours')

            x_labels = tuple(map(datetime.datetime.utcfromtimestamp, nonzero_intervals_day))
            ax.xaxis.set_major_formatter(md.DateFormatter('%H:%M'))
            ax.plot(x_labels, y_labels, label=day)
        ax.set_title(route_name)
        fig.legend()
        return fig


def sort_days_intervals(timestamps, durations, timedelta):
    dates = np.array(list(map(datetime.datetime.fromtimestamp, timestamps)))
    durations = np.array(durations)
    dates_days_indices = argsort_days(dates)
    durations_days_intervals = []
    nonzero_intervals = []
    for dates_day_idx in dates_days_indices:
        dates_day = dates[dates_day_idx]
        durations_day = durations[dates_day_idx]
        dates_intervals_indices = argsort_time(dates_day, timedelta)
        nonzero_intervals.append([i for i in range(len(dates_intervals_indices))
                                  if len(dates_intervals_indices[i]) > 0])

        durations_days_intervals.append([durations_day[dates_intervals_idx]
                                         for dates_intervals_idx in dates_intervals_indices
                                         if len(durations_day[dates_intervals_idx]) > 0])
    return (
        durations_days_intervals,
        nonzero_intervals
    )


def argsort_days(dates):
    return [[j for j in range(len(dates)) if dates[j].day % 7 == i] for i in range(7)]


def date_in_interval(time_interval, i, date):
    return time_interval * i <= date.hour * HOUR + date.minute * MINUTE + date.second < time_interval * (i + 1)


def argsort_time(dates, time_interval):
    num_intervals = math.ceil(DAY / time_interval)
    return [[j for j in range(len(dates))
             if date_in_interval(time_interval, i, dates[j])]
            for i in range(num_intervals)]
