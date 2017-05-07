# -*- coding: utf-8 -*-
"""Extends bokeh histogram with additional feature and interactivity.
"""

# -----------------------------------------------------------------------------
# Imports
# -----------------------------------------------------------------------------
from __future__ import absolute_import, print_function, division

import numpy as np
import pandas as pd
from bokeh.plotting import figure as bkfigure
#from bokeh.models.ranges import Range1d as bkRange1d
from bokeh.models.sources import ColumnDataSource as bkColumnDataSource
from bokeh.models import BoxAnnotation as bkBoxAnnotation
#from ..builder import Builder, create_and_build
#from ...models import FactorRange, Range1d
from ._rugplot import Rugplot
from bokeh.io import curdoc
from ..util import debounce


# -----------------------------------------------------------------------------
# Classes and functions
# -----------------------------------------------------------------------------
class Histogram(object):
    """This allows to draw complec histogram. If run in a bokeh server it is
    possible to add histogram interactivity.
    """

    def __init__(self, data, values=None, label=None, agg=None,
                  bins="auto", yscale="linear", figure=None,
                  limit=None, x_range=None, outliers=True, doc=None,
                  density=False, show_limits=None, orientation='vertical',
                  rug=True, details=False, x_bounds=None, auto_update=True,
                  kw_figure={}, kw_bars={}, kw_bars_outliers={},
                  kw_rug={}, kw_details={},**kw):
        """ Create a histogram chart with one or more histograms.
        Create a histogram chart using :class:`HistogramBuilder
        <bokeh.charts.builders.histogram_builder.HistogramBuilder>` to
        render the glyphs from input data and specification. This primary
        use case for the histogram is to depict the distribution of a
        variable by binning and aggregating the values in each bin.
        This chart implements functionality to provide convenience in optimal
        selection of bin count, but also for segmenting and comparing segments of
        the variable by a categorical variable.
        Args:
          data (:ref:`userguide_charts_data_types`): the data source for the chart.
            Must consist of at least 2 values. If all values are equal, the result
            is a single bin with arbitrary width.
          values (str, optional): the values to use for producing the histogram using
            table-like input data
          label (str or list(str), optional): the categorical variable to use for creating
            separate histograms
          color (str or list(str) or `~bokeh.charts._attributes.ColorAttr`, optional): the
            categorical variable or color attribute specification to use for coloring the
            histogram, or explicit color as a string.
          agg (str, optional): how to aggregate the bins. Defaults to "count".
          bins (int or list(float), optional): the number of bins to use, or an explicit
            list of bin edges. Defaults to None to auto select.
          density (bool, optional): whether to normalize the histogram. Defaults to False.
          limit (list(int), optional): The limit of the data, as list (lower_limit,upper_limit).
          x_range (list(int), optional): The range of the data in the histogram, as list
            (lower_range,upper_range). If no range is defined min and max of the data is taken.
          outliers (boolean, optional): Are values outside of the range value add everything
            outside into one last bar. By default this is True.
          auto_update (boolean, optional): Auto update range when plot view changes. This
            works only with a bokeh server.
          **kw:
        In addition to the parameters specific to this chart,
        :ref:`userguide_charts_defaults` are also accepted as keyword parameters.
        Returns:
            :class:`Chart`: includes glyph renderers that generate the histograms
        Examples:
        .. bokeh-plot::
            :source-position: above
            import bokeh_extended as bke
            from bokeh.charts import output_file, show
            from bokeh.layouts import row
            from bokeh.sampledata.autompg import autompg as df
            hist = bke.charts.Histogram(df, values='mpg', title="Auto MPG Histogram", plot_width=400)
            hist2 = bke.charts.Histogram(df, values='mpg', label='cyl', color='cyl', legend='top_right',
                              title="MPG Histogram by Cylinder Count", plot_width=400)
            output_file('hist.html')
            show(row(hist, hist2))
        """
        if figure:
            self.figure = figure
        else:
            self.figure = bkfigure(**kw_figure)
        #self.hist = bkHistogram(data, **kw)
        self.kw_bars = kw_bars
        self.kw_bars.setdefault('fill_color', "#036564")
        self.kw_bars.setdefault('line_color', "#033649")
        self.kw_bars_outliers = kw_bars_outliers
        self.kw_bars.setdefault('fill_color', "#FF0000")
        self.kw_bars.setdefault('line_color', "#222222")

        self.source = {}
        self.source['histo_out'] = bkColumnDataSource()
        self.source['histo'] = bkColumnDataSource()


        self.show_limits = show_limits if show_limits != None else True if limit else False
        self.outliers = outliers
        self._orig_bins = bins # original bins argument
        self._bin_no = bins if isinstance(bins,(float, int)) else 30 # numbers of bins
        self._bin_edges = None # list wiht all bin edges
        self.density = density
        self.agg = agg
        self.rug = rug
        self.kw_rug = kw_rug
        self.details = details
        self.kw_details = kw_details
        self._limit = limit
        self._x_bounds = x_bounds
        self._x_range = x_range
        self._values = values
        # call data late, this updates the plot, but all variable need to be defined already.
        self.data = data
        self._orig_x_range = x_range if x_range else self.x_range
        self.hist = self._create_histo()
        self.auto_update = auto_update
        self.doc = doc
        self.figure.x_range.on_change('end',self._view_changed_event)
        self.figure.x_range.on_change('start',self._view_changed_event)



    @property
    def bin_width(self):
        self.__bin_width = (self.x_range[1] - self.x_range[0]) / float(self.bins)
        return self.__bin_width
    @bin_width.setter
    def bin_width(self, w):
        """ not implemented """
        pass


    @property
    def x_range(self):
        return self._x_range

    @x_range.setter
    def x_range(self, new_range):
        self._x_range = new_range if new_range != None else self.limit
        self._calc_histogram()
        self._update_x_bounds()


    @property
    def bins(self):
        return self._bin_no

    @bins.setter
    def bins(self, bins):
        self._orig_bins = bins
        self._calc_histogram()

    @property
    def limit(self):
        return self._limit

    @limit.setter
    def limit(self, limit):
        self._limit = limit
        if hasattr(self,'_lower_limit_box'):
            self._lower_limit_box.right = self.limit[0]
        if hasattr(self,'_upper_limit_box'):
            self._upper_limit_box.left = self.limit[1]
        if hasattr(self,'_mid_limit_box'):
            self._mid_limit_box.left = self.limit[1]
            self._mid_limit_box.right = self.limit[0]

    @property
    def data(self):
        if hasattr(self,'_data'):
            return self._data
        else:
            return pd.DataFrame({self.values:[]})

    @data.setter
    def data(self, data):
        self._orig_data = data
        raw_data = pd.DataFrame()
        if self._values in data:
            raw_data[self._values] = data[self._values]
        else:
            self._values = 'x'
            raw_data[self._values] = data
        self._data = raw_data[self._values].dropna()

        if self._limit and not self._x_range:
            add_range = (self._limit[1] - self._limit[0])/4
            self._x_range = [self._limit[0] - add_range,
                    self._limit[1] + add_range]
        else:
            self._x_range = self._x_range if self._x_range != None \
                    else [self._data.min(), self._data.max()]
        self._limit = self._limit if self._limit != None else [self._data.min(), self._data.max()]
        self._calc_histogram()

    def _view_changed_event(self, value, new, old):
        if self.auto_update and self.doc:
            self._update_view_debounced()

    @debounce(0.1)
    def _update_view_debounced(self):
        #print("UPDATE view")
        self.doc.add_next_tick_callback(self.update_view)


    @property
    def values(self):
        return getattr(self,'_values')

    @values.setter
    def values(self, values):
        self._values = values
        self.data = self._orig_data

    def _update_x_bounds(self, new_bounds=None):
        lower_bound = self.data.min()-self.bin_width*self.bins/4
        lower_bound = lower_bound if lower_bound < self.x_range[0] \
                else self.x_range[0]-self.bin_width*self.bins/4
        upper_bound = self.data.max()+self.bin_width*self.bins/4
        upper_bound = upper_bound if upper_bound > self.x_range[1] \
                else self.x_range[1]+self.bin_width*self.bins/4
        self._x_bounds = new_bounds if new_bounds else (lower_bound, upper_bound)
        # self.figure.x_range = bkRange1d(start=self.x_range[0]-self.bin_width,
        #         end=self.x_range[1]+self.bin_width,
        #         bounds = self._x_bounds)
        self.figure.x_range.start=self.x_range[0]-self.bin_width
        self.figure.x_range.end=self.x_range[1]+self.bin_width
        self.figure.x_range.bounds=self._x_bounds


    def update_view(self, region='x_range', add=0, add_bins=0):
        """changes range accordingly to the visible histogram

        region: - 'x_range' : update to current x_range
                - 'data' : fit data into view
                - 'limit' : fit to limits
                - 'reset' : reset to original x_range
                """
        print("Update view to {}".format(region))
        if region == "x_range":
            start = self.figure.x_range.start
            end = self.figure.x_range.end
        if region == "data":
            start = self.data.min()
            end = self.data.max()
        if region == "limit":
            start = self.limit[0]
            end = self.limit[1]
        if region == "reset":
            start = self._orig_x_range[0]
            end = self._orig_x_range[1]
        else:
            start = self.figure.x_range.start
            end = self.figure.x_range.end
        bin_width = (end - start) / float(self.bins + 2)
        add_range = 0 if add == 0 else (end - start)/add
        add_range += 0 if add_bins == 0 else add_bins * bin_width

        self.x_range = [start + bin_width - add_range, end - bin_width + add_range]

    def _calc_histogram(self):
        hist, edges = np.histogram(self.data, density=self.density,
                bins=self._orig_bins, range= self.x_range)
        self._bin_edges= edges
        self._bin_no= len(self._bin_edges) - 1
        out_data = pd.DataFrame()
        df_lower = self.data[self.data < self.x_range[0]]
        df_upper = self.data[self.data > self.x_range[1]]
        lower = df_lower.count()
        upper = df_upper.count()
        out_data['count'] = [lower, upper]
        out_data['left'] = [df_lower.min() , edges[-1]]
        out_data['right'] = [edges[0], df_upper.max()]
        out_data['width'] = out_data['right'] - out_data['left']
        out_data['mid'] = out_data['left'] + out_data['width']/2
        self.source['histo_out'].data = bkColumnDataSource.from_df(out_data)

        data = pd.DataFrame()
        data['count'] = hist
        data['left'] = edges[:-1]
        data['right'] = edges[1:]
        data['width'] = data['right'] - data['left']
        data['mid'] = data['left'] + data['width']/2
        self.source['histo'].data = bkColumnDataSource.from_df(data)


    def _create_histo(self):
        #self._calc_histogram()
        if self.outliers:
            self.figure.vbar(source=self.source['histo_out'],x='mid', bottom=0, \
                    top='count', width='width', **self.kw_bars_outliers)
        self.figure.vbar(source=self.source['histo'],x='mid', bottom=0, \
                top='count', width='width', **self.kw_bars)
        # add rugs and detail histogram
        if self.rug or self.details:
            hist_all, edges_all = np.histogram(self.data, bins=len(self.data))
            if self.details:
                self.kw_details.setdefault('fill_alpha',0.2)
                self.kw_details.setdefault('bottom',0)
                self.kw_details.setdefault('line_width',0)
                self.kw_details.setdefault('line_alpha',0)
                self.kw_details.setdefault('fill_color',"#00ff00")
                scale = self.kw_rug.get('details_scale',0.5)

                self.figure.quad(top=hist_all* scale,
                        left=edges_all[:-1],
                        right=edges_all[1:], **self.kw_details)
            if self.rug:
                max_height = self.source['histo'].data['count'].max()
                self.rug_plot = Rugplot(self.data, self.figure, max_height=max_height, **self.kw_rug)
        if self.show_limits:
            self.kw_outer_limit_box = {}
            self.kw_outer_limit_box.setdefault('fill_alpha',0.1)
            self.kw_outer_limit_box.setdefault('fill_color','red')
            self.kw_outer_limit_box.setdefault('line_width',2)
            self.kw_outer_limit_box.setdefault('line_alpha',0.4)
            self.kw_inner_limit_box = {}
            self.kw_inner_limit_box.setdefault('fill_alpha',0.05)
            self.kw_inner_limit_box.setdefault('fill_color','yellow')
            self.kw_inner_limit_box.setdefault('line_alpha',0)
            self._lower_limit_box = bkBoxAnnotation(right=self.limit[0], \
                    **self.kw_outer_limit_box)
            self._upper_limit_box = bkBoxAnnotation(left=self.limit[1], \
                    **self.kw_outer_limit_box)
            self._mid_limit_box = bkBoxAnnotation(right=self.limit[0], left=self.limit[1], \
                **self.kw_inner_limit_box)
            self.figure.add_layout(self._lower_limit_box)
            self.figure.add_layout(self._upper_limit_box)
            self.figure.add_layout(self._mid_limit_box)


        self._update_x_bounds()
        return self.figure


    def __call__(self):
        return self.hist
    def plot(self):
        return self.hist



