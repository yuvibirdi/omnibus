from publisher import publisher
from pyqtgraph.Qt import QtWidgets
from pyqtgraph.Qt.QtWidgets import QGridLayout, QMenu
from pyqtgraph.Qt.QtCore import QEvent
import pyqtgraph as pg
from pyqtgraph.console import ConsoleWidget


from pyqtgraph.graphicsItems.LabelItem import LabelItem
from pyqtgraph.graphicsItems.TextItem import TextItem

import numpy as np

from .dashboard_item import DashboardItem
import config
from utils import prompt_user
from .registry import Register


@Register
class PlotDashItem(DashboardItem):
    def __init__(self, props):
        # Call this in **every** dash item constructor
        super().__init__()

        self.size = config.GRAPH_RESOLUTION * config.GRAPH_DURATION
        self.avgSize = config.GRAPH_RESOLUTION * config.RUNNING_AVG_DURATION
        self.sum = {}
        self.last = {}

        # storing the series name as key, its time and points as value
        # since each PlotDashItem can contain more than one curve
        self.times = {}
        self.points = {}

        # Specify the layout
        self.layout = QGridLayout()
        self.setLayout(self.layout)

        # set the limit for triggering red tint area
        self.limit = props["limit"]

        # a list of series names to be plotted
        self.series = props["series"]

        # save props as a field
        self.props = props

        # subscribe to stream dictated by properties
        for series in self.series:
            publisher.subscribe(series, self.on_data_update)

        # a default color list for plotting multiple curves
        # yellow green cyan white blue magenta
        self.color = ['y', 'g', 'c', 'w', 'b', 'm']

        # create the plot
        self.plot = pg.PlotItem(title='/'.join(self.series), left="Data", bottom="Seconds")
        self.plot.setMenuEnabled(False)     # hide the default context menu when right-clicked
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        if (len(self.series) > 1):
            self.plot.addLegend()
        # draw the curves
        # storing the series name as key, its plot object as value
        # update all curves every time on_data_update() is called
        self.curves = {}
        for i, series in enumerate(self.series):
            curve = self.plot.plot([], [], pen=self.color[i], name=series)
            self.curves[series] = curve
            self.times[series] = np.zeros(self.size)
            self.points[series] = np.zeros(self.size)
            self.sum[series] = 0
            self.last[series] = 0

        # initialize the threshold line, but do not plot it unless a limit is specified
        self.warning_line = self.plot.plot([], [], brush=(255, 0, 0, 50), pen='r')

        # create the plot widget
        self.widget = pg.PlotWidget(plotItem=self.plot)

        # add it to the layout
        self.layout.addWidget(self.widget, 0, 0)

    # overriding QWidget method to create custom context menu
    # this idea is generated by ChatGPT :-o, neater than my previous solution found on stackoverflow
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        change_threshold = menu.addAction('Change threshold')

        action = menu.exec_(event.globalPos())
        if action == change_threshold:
            threshold_input = prompt_user(
                self,
                "Threshold Value",
                "Set an upper limit",
                "number",
                cancelText="No Threshold"
            )
            self.limit = threshold_input
            self.props["limit"] = threshold_input
            # if user changes threshold to No threshold
            if self.limit == None:
                self.warning_line.setData([], [])
                self.warning_line.setFillLevel(None)

    def prompt_for_properties(self):

        channel_and_series = prompt_user(
            self,
            "Data Series",
            "Select the series you wish to plot. Up to 6 if plotting together.",
            "checkbox",
            publisher.get_all_streams(),
        )
        if not channel_and_series[0]:
            return None
        # if more than 6 series are selected, only plot the first 6
        if len(channel_and_series) > 6:
            channel_and_series = channel_and_series[:6]

        if channel_and_series[1]:     # plot separately
            props = [{"series": [series], "limit": None} for series in channel_and_series[0]]
        else:                           # plot together
            # if more than 6 series are selected, only plot the first 6
            if len(channel_and_series) > 6:
                channel_and_series = channel_and_series[:6]
            props = [{"series": channel_and_series[0], "limit": None}]

        return props

    def on_data_update(self, stream, payload):
        time, point = payload

        # time should be passed as seconds, GRAPH_RESOLUTION is points per second
        if time - self.last[stream] < 1 / config.GRAPH_RESOLUTION:
            return

        if self.last[stream] == 0:  # is this the first point we're plotting?
            # prevent a rogue datapoint at (0, 0)
            self.times[stream].fill(time)
            self.points[stream].fill(point)
            self.sum[stream] = self.avgSize * point

        self.last[stream] = time

        self.sum[stream] -= self.points[stream][self.size - self.avgSize]
        self.sum[stream] += point

        # add the new datapoint to the end of the corresponding stream array, shuffle everything else back
        self.times[stream][:-1] = self.times[stream][1:]
        self.times[stream][-1] = time
        self.points[stream][:-1] = self.points[stream][1:]
        self.points[stream][-1] = point

        # get the min/max point in the whole data set
        min_point = min(min(v) for v in self.points.values())
        max_point = max(max(v) for v in self.points.values())

        # set the displayed range of Y axis
        self.plot.setYRange(min_point, max_point, padding=0.1)

        if self.limit is not None:
            # plot the warning line, using two points (start and end)
            self.warning_line.setData(
                [self.times[stream][0], self.times[stream][-1]], [self.limit] * 2)
            # set the red tint
            self.warning_line.setFillLevel(max_point*2)

        # update the data curve
        self.curves[stream].setData(self.times[stream], self.points[stream])

        # round the time to the nearest GRAPH_STEP
        t = round(self.times[stream][-1] / config.GRAPH_STEP) * config.GRAPH_STEP
        self.plot.setXRange(t - config.GRAPH_DURATION + config.GRAPH_STEP,
                            t + config.GRAPH_STEP, padding=0)

        # value readout in the title for at most 2 series
        title = ""
        if len(self.series) <= 2:
            # avg values
            avg_values = [self.sum[item]/self.avgSize for item in self.series]
            title += "avg: "
            for v in avg_values:
                title += f"[{v: < 4.4f}]"
            # current values
            title += "    current: "
            last_values = [self.points[item][-1] for item in self.series]
            for v in last_values:
                title += f"[{v: < 4.4f}]"
            title += "    "
        # data series name
        title += "/".join(self.series)

        self.plot.setTitle(title)

    def get_props(self):
        return self.props

    @staticmethod
    def get_name():
        return "Plot"

    def on_delete(self):
        publisher.unsubscribe_from_all(self.on_data_update)
