import datetime
import logging
import math

import numpy as np
from matplotlib import pyplot as plt, dates as md

MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR

logger = logging.getLogger('traffic_scanner/traffic_view.py')


class TrafficView:

    def __init__(self, period):
        assert period < 24 * 60 * 60
        self.time_intervals = math.ceil(DAY / period)
        self.timedelta = datetime.timedelta(seconds=period)

    @staticmethod
    def seconds_to_time(seconds):
        hour = math.floor(seconds / HOUR)
        minute = math.floor((seconds % HOUR) / MINUTE)
        second = math.floor(seconds % MINUTE)
        return datetime.datetime(2011, 1, 11, hour, minute, second)

    def plot_traffic(self, timestamps, durations):
        datetimes = tuple(map(datetime.datetime.fromisoformat, timestamps))
        time_intervals = []
        durations_in_time_intervals = []

        time_start = datetime.datetime.min
        time_end = datetime.datetime.min + self.timedelta
        nonzero_idx = []
        for i in range(self.time_intervals):
            durations_in_this_interval = tuple(durations[j] for j in range(len(datetimes))
                                               if time_start.time() <= datetimes[j].time() < time_end.time())
            if len(durations_in_this_interval) != 0:
                # TODO: Handle nans
                nonzero_idx.append(i)
            durations_in_time_intervals.append(durations_in_this_interval)
            time_intervals.append(time_start.time())
            time_start += self.timedelta
            time_end += self.timedelta

        # Removing empty
        durations_in_time_intervals = tuple(filter(len, durations_in_time_intervals))
        time_intervals = np.array(time_intervals)[nonzero_idx]

        alpha = 0.4
        fig = plt.figure(figsize=(12, 4))
        max_ = tuple(map(np.max, durations_in_time_intervals))
        mean = tuple(map(np.mean, durations_in_time_intervals))
        min_ = tuple(map(np.min, durations_in_time_intervals))
        x_labels = tuple(map(lambda x: datetime.datetime(2011, 11, 11, x.hour, x.minute, x.second), time_intervals))
        ax = fig.gca()

        ax.xaxis_date()
        ax.xaxis.set_major_formatter(md.DateFormatter('%H:%M'))
        ax.yaxis.set_major_formatter(md.DateFormatter('%H:%M'))

        # Casting to time
        max_ = tuple(map(self.seconds_to_time, max_))
        min_ = tuple(map(self.seconds_to_time, min_))
        mean = tuple(map(self.seconds_to_time, mean))

        ax.bar(x_labels, max_, alpha=alpha, label='Min', width=0.005)
        ax.bar(x_labels, min_, alpha=alpha, label='Max', width=0.015)
        ax.set_ylim(np.min(min_) - datetime.timedelta(minutes=10), np.max(max_) + datetime.timedelta(minutes=10))
        fig.legend()
        return fig