import numpy as np

from bokeh.models import ColumnDataSource

from src.datastore import DATASET, INITIAL, PROBES
from src.helpers import load_isotherm as load_isotherm
from src.statistics import select_data
from functools import partial
from threading import Thread
from tornado import gen


################################
# DataModel class
################################

class DataModel():
    """
    Processing of data for a Dashboard.
    """

    def __init__(self, doc):

        # Save reference
        self.doc = doc

        # Dataset
        self._df = DATASET       # Entire dataset
        self._dfs = INITIAL      # Selected material-oriented dataset
        self.ads_list = PROBES   # All probes in the system

        # Adsorbate definitions
        self.g1 = "propane"
        self.g2 = "propene"

        # Temperature definitions
        self.t_abs = 303
        self.t_tol = 10

        # Isotherm type definitions
        self.iso_type = None

        # Pressure definitions
        self.lp = 0.5    # 0.5 bar
        self.p1 = 0.5    # 0.5 bar
        self.p2 = 5      # 5.0 bar

        # Bokeh-specific data source generation
        self.data = ColumnDataSource(data=self.gen_data())
        self.errors = ColumnDataSource(data=self.gen_error())
        self.g1_iso_sel = ColumnDataSource(data=self.gen_iso_dict())
        self.g2_iso_sel = ColumnDataSource(data=self.gen_iso_dict())

        # Data selection callback
        self.data.selected.on_change('indices', self.selection_callback)

    def callback_link_sep(self, s_dash):
        """Link the separation dashboard to the model."""

        # Store reference
        self.s_dash = s_dash

        # Data type selections
        def dtype_callback(attr, old, new):
            if new == 0:
                self.iso_type = None
            elif new == 1:
                self.iso_type = 'exp'
            elif new == 2:
                self.iso_type = 'sim'
            self.new_dtype_callback()

        self.s_dash.data_type.on_change('active', dtype_callback)

        # Adsorbate drop-down selections
        def g1_sel_callback(attr, old, new):
            self.g1 = new
            self.new_ads_callback()

        def g2_sel_callback(attr, old, new):
            self.g2 = new
            self.new_ads_callback()

        self.s_dash.g1_sel.on_change("value", g1_sel_callback)
        self.s_dash.g2_sel.on_change("value", g2_sel_callback)

        # Temperature selection callback
        def t_abs_callback(attr, old, new):
            self.t_abs = new
            self.new_t_callback()

        def t_tol_callback(attr, old, new):
            self.t_tol = new
            self.new_t_callback()

        self.s_dash.t_absolute.on_change("value", t_abs_callback)
        self.s_dash.t_tolerance.on_change("value", t_tol_callback)

        # Pressure slider
        self.s_dash.p_slider.on_change('value_throttled', self.uptake_callback)

        # Working capacity slider
        self.s_dash.wc_slider.on_change('value_throttled', self.wc_callback)


    # #########################################################################
    # Selection update

    def calculate(self):
        """Calculate and display for initial values."""
        # Generate specific dataframe
        self._dfs = select_data(
            self._df, self.iso_type,
            self.t_abs, self.t_tol,
            self.g1, self.g2
        )

        # Gen data
        self.data.data = self.gen_data()

    def new_dtype_callback(self):
        """What to do when a new data type is selected."""

        # Calculate
        self.calculate()

        # Reset any selected materials
        if self.data.selected.indices:
            self.data.selected.update(indices=[])

        # Update bottom
        self.g1_iso_sel.data = self.gen_iso_dict()
        self.g2_iso_sel.data = self.gen_iso_dict()
        print(f'finished, now {len(self._dfs)}')

    def new_t_callback(self):
        """What to do when a new temperature range is selected."""

        # Calculate
        self.calculate()

        # Reset any selected materials
        if self.data.selected.indices:
            self.data.selected.update(indices=[])

        # Update bottom
        self.g1_iso_sel.data = self.gen_iso_dict()
        self.g2_iso_sel.data = self.gen_iso_dict()

    def new_ads_callback(self):
        """What to do when a new ads is selected."""

        # Calculate
        self.calculate()

        # Reset any selected materials
        if self.data.selected.indices:
            self.data.selected.update(indices=[])

        # Update labels
        self.s_dash.top_graph_labels()

        # Update bottom
        self.g1_iso_sel.data = self.gen_iso_dict()
        self.g2_iso_sel.data = self.gen_iso_dict()
        self.s_dash.p_g1iso.title.text = 'Isotherms {0}'.format(self.g1)
        self.s_dash.p_g2iso.title.text = 'Isotherms {0}'.format(self.g2)

    # #########################################################################
    # Set up pressure slider and callback

    def uptake_callback(self, attr, old, new):
        """Callback on each pressure selected for uptake."""
        self.lp = new
        # regenerate graph data
        self.data.patch(self.patch_data_l())
        if self.data.selected.indices:
            self.errors.patch(self.patch_error_l(self.data.selected.indices))

    # #########################################################################
    # Set up working capacity slider and callback

    def wc_callback(self, attr, old, new):
        """Callback on pressure range for working capacity."""
        self.p1, self.p2 = new[0], new[1]
        # regenerate graph data
        self.data.patch(self.patch_data_w())
        if self.data.selected.indices:
            self.errors.patch(self.patch_error_wc(self.data.selected.indices))

    # #########################################################################
    # Data generator

    def gen_data(self):
        """Select or generate all KPI data for a pair of ads_list."""

        K_nx = self._dfs[('kH_x', 'size')].values
        K_x = self._dfs[('kH_x', 'med')].values
        K_ny = self._dfs[('kH_y', 'size')].values
        K_y = self._dfs[('kH_y', 'med')].values
        K_n = K_nx + K_ny

        L_nx = self._dfs[('{0:.1f}_x'.format(self.lp), 'size')].values
        L_x = self._dfs[('{0:.1f}_x'.format(self.lp), 'med')].values
        L_ny = self._dfs[('{0:.1f}_y'.format(self.lp), 'size')].values
        L_y = self._dfs[('{0:.1f}_y'.format(self.lp), 'med')].values
        L_n = L_nx + L_ny

        W_nx = np.maximum(
            self._dfs[('{0:.1f}_x'.format(self.p1), 'size')].values,
            self._dfs[('{0:.1f}_x'.format(self.p2), 'size')].values
        )
        W_x = self._dfs[('{0:.1f}_x'.format(self.p2), 'med')].values - \
            self._dfs[('{0:.1f}_x'.format(self.p1), 'med')].values
        W_ny = np.maximum(
            self._dfs[('{0:.1f}_y'.format(self.p1), 'size')].values,
            self._dfs[('{0:.1f}_y'.format(self.p2), 'size')].values
        )
        W_y = self._dfs[('{0:.1f}_y'.format(self.p2), 'med')].values - \
            self._dfs[('{0:.1f}_y'.format(self.p1), 'med')].values
        W_n = W_nx + W_ny

        sel = K_y / K_x
        psa_W = (K_y / W_x) * sel

        return {
            'labels': self._dfs.index,

            # parameters
            'sel': sel,
            'psa_W': psa_W,

            # Henry data
            'K_x': K_x, 'K_y': K_y,
            'K_nx': K_nx, 'K_ny': K_ny, 'K_n': K_n,

            # Loading data
            'L_x': L_x, 'L_y': L_y,
            'L_nx': L_nx, 'L_ny': L_ny, 'L_n': L_n,

            # Working capacity data
            'W_x': W_x, 'W_y': W_y,
            'W_nx': W_nx, 'W_ny': W_ny, 'W_n': W_n,
        }


    def patch_data_l(self):
        """Patch KPI data when uptake changes."""

        L_nx = self._dfs[('{0:.1f}_x'.format(self.lp), 'size')].values
        L_x = self._dfs[('{0:.1f}_x'.format(self.lp), 'med')].values
        L_ny = self._dfs[('{0:.1f}_y'.format(self.lp), 'size')].values
        L_y = self._dfs[('{0:.1f}_y'.format(self.lp), 'med')].values
        L_n = L_nx + L_ny

        return {
            # Loading data
            'L_x': [(slice(None), L_x)], 'L_y': [(slice(None), L_y)],
            'L_nx': [(slice(None), L_nx)], 'L_ny': [(slice(None), L_ny)],
            'L_n': [(slice(None), L_n)]
        }

    def patch_data_w(self):
        """Patch KPI data when working capacity changes."""

        W_nx = np.maximum(
            self._dfs[('{0:.1f}_x'.format(self.p1), 'size')].values,
            self._dfs[('{0:.1f}_x'.format(self.p2), 'size')].values
        )
        W_x = self._dfs[('{0:.1f}_x'.format(self.p2), 'med')].values - \
            self._dfs[('{0:.1f}_x'.format(self.p1), 'med')].values
        W_ny = np.maximum(
            self._dfs[('{0:.1f}_y'.format(self.p1), 'size')].values,
            self._dfs[('{0:.1f}_y'.format(self.p2), 'size')].values
        )
        W_y = self._dfs[('{0:.1f}_y'.format(self.p2), 'med')].values - \
            self._dfs[('{0:.1f}_y'.format(self.p1), 'med')].values
        W_n = W_nx + W_ny
        psa_W = (W_y / W_x) * self.data.data['sel']

        return {
            # parameters
            'psa_W': [(slice(None), psa_W)],

            # Working capacity data
            'W_x': [(slice(None), W_x)], 'W_y': [(slice(None), W_y)],
            'W_nx': [(slice(None), W_nx)], 'W_ny': [(slice(None), W_ny)],
            'W_n': [(slice(None), W_n)]
        }


    # #########################################################################
    # Error generator

    def gen_error(self, indices=None):
        """Select or generate all error data for selected points."""

        if indices is None:
            return {
                'labels': [],
                'K_x': [], 'K_y': [],
                'L_x': [], 'L_y': [],
                'W_x': [], 'W_y': [],
                'K_x0': [], 'K_y0': [], 'K_x1': [], 'K_y1': [],
                'L_x0': [], 'L_y0': [], 'L_x1': [], 'L_y1': [],
                'W_x0': [], 'W_y0': [], 'W_x1': [], 'W_y1': [],
            }

        else:

            mats = []
            K_X, K_Y, L_X, L_Y, W_X, W_Y = [], [], [], [], [], []
            K_X1, K_Y1, K_X2, K_Y2 = [], [], [], []
            L_X1, L_Y1, L_X2, L_Y2 = [], [], [], []
            W_X1, W_Y1, W_X2, W_Y2 = [], [], [], []

            for index in indices:

                mat = self.data.data['labels'][index]
                K_x = self.data.data['K_x'][index]
                K_y = self.data.data['K_y'][index]
                L_x = self.data.data['L_x'][index]
                L_y = self.data.data['L_y'][index]
                W_x = self.data.data['W_x'][index]
                W_y = self.data.data['W_y'][index]

                # NaN values have to be avoided
                if np.isnan(K_x) or np.isnan(K_y):
                    K_x, K_y = 0, 0
                    K_ex, K_ey = 0, 0
                else:
                    K_ex = self._dfs.loc[mat, ('kH_x', 'err')]
                    K_ey = self._dfs.loc[mat, ('kH_y', 'err')]

                if np.isnan(L_x) or np.isnan(L_y):
                    L_x, L_y = 0, 0
                    L_ex, L_ey = 0, 0
                else:
                    L_ex = self._dfs.loc[mat, ('{:.1f}_x'.format(self.lp), 'err')]
                    L_ey = self._dfs.loc[mat, ('{:.1f}_y'.format(self.lp), 'err')]

                if np.isnan(W_x) or np.isnan(W_y):
                    W_x, W_y = 0, 0
                    W_ex, W_ey = 0, 0
                else:
                    W_ex = self._dfs.loc[mat, ('{:.1f}_x'.format(self.p1), 'err')] + \
                            self._dfs.loc[mat, ('{:.1f}_x'.format(self.p2), 'err')]
                    W_ey = self._dfs.loc[mat, ('{:.1f}_y'.format(self.p1), 'err')] + \
                            self._dfs.loc[mat, ('{:.1f}_y'.format(self.p2), 'err')]

                mats.extend([mat, mat])
                K_X.extend([K_x, K_x])
                K_Y.extend([K_y, K_y])
                L_X.extend([L_x, L_x])
                L_Y.extend([L_y, L_y])
                W_X.extend([W_x, W_x])
                W_Y.extend([W_y, W_y])
                # henry data
                K_X1.extend([K_x - K_ex, K_x])
                K_Y1.extend([K_y, K_y - K_ey])
                K_X2.extend([K_x + K_ex, K_x])
                K_Y2.extend([K_y, K_y + K_ey])
                # loading data
                L_X1.extend([L_x - L_ex, L_x])
                L_Y1.extend([L_y, L_y - L_ey])
                L_X2.extend([L_x + L_ex, L_x])
                L_Y2.extend([L_y, L_y + L_ey])
                # working capacity data
                W_X1.extend([W_x - W_ex, W_x])
                W_Y1.extend([W_y, W_y - W_ey])
                W_X2.extend([W_x + W_ex, W_x])
                W_Y2.extend([W_y, W_y + W_ey])

            return {
                # labels
                'labels': mats,
                'K_x': K_X, 'K_y': K_Y,
                'L_x': L_X, 'L_y': L_Y,
                'W_x': W_X, 'W_y': W_Y,
                # henry data
                'K_x0': K_X1, 'K_y0': K_Y1, 'K_x1': K_X2, 'K_y1': K_Y2, 
                # loading data
                'L_x0': L_X1, 'L_y0': L_Y1, 'L_x1': L_X2, 'L_y1': L_Y2,
                # working capacity data
                'W_x0': W_X1, 'W_y0': W_Y1, 'W_x1': W_X2, 'W_y1': W_Y2,
            }

    def patch_error_l(self, indices=None):
        """Patch error data when uptake changes."""
        if indices is None:
            return {
                # loading data
                'L_x': [(slice(None), [])],
                'L_y': [(slice(None), [])],
                'L_x0': [(slice(None), [])],
                'L_y0': [(slice(None), [])],
                'L_x1': [(slice(None), [])],
                'L_y1': [(slice(None), [])],
            }
        else:
            L_X, L_Y = [], []
            L_X1, L_Y1, L_X2, L_Y2 = [], [], [], []

            for index in indices:

                L_x = self.data.data['L_x'][index]
                L_y = self.data.data['L_y'][index]
                if np.isnan(L_x) or np.isnan(L_y):
                    L_x, L_y = 0, 0
                    L_ex, L_ey = 0, 0
                else:
                    mat = self.data.data['labels'][index]
                    L_ex = self._dfs.loc[mat, '{:.1f}_x'.format(self.lp)][2]
                    L_ey = self._dfs.loc[mat, '{:.1f}_y'.format(self.lp)][2]

                L_X.extend([L_x, L_x])
                L_Y.extend([L_y, L_y])
                L_X1.extend([L_x - L_ex, L_x])
                L_Y1.extend([L_y, L_y - L_ey])
                L_X2.extend([L_x + L_ex, L_x])
                L_Y2.extend([L_y, L_y + L_ey])

            return {
                # loading data
                'L_x': [(slice(None), L_X)],
                'L_y': [(slice(None), L_Y)],
                'L_x0': [(slice(None), L_X1)],
                'L_y0': [(slice(None), L_Y1)],
                'L_x1': [(slice(None), L_X2)],
                'L_y1': [(slice(None), L_Y2)],
            }

    def patch_error_wc(self, indices=None):
        """Patch error data when working capacity changes."""
        if indices is None:
            return {
                # loading data
                'W_x': [(slice(None), [])],
                'W_y': [(slice(None), [])],
                'W_x0': [(slice(None), [])],
                'W_y0': [(slice(None), [])],
                'W_x1': [(slice(None), [])],
                'W_y1': [(slice(None), [])],
            }
        else:
            W_X, W_Y = [], []
            W_X1, W_Y1, W_X2, W_Y2 = [], [], [], []

            for index in indices:

                W_x = self.data.data['W_x'][index]
                W_y = self.data.data['W_y'][index]
                if np.isnan(W_x) or np.isnan(W_y):
                    W_x, W_y = 0, 0
                    W_ex, W_ey = 0, 0
                else:
                    mat = self.data.data['labels'][index]
                    W_ex = self._dfs.loc[mat, '{:.1f}_x'.format(self.p1)][2] + \
                            self._dfs.loc[mat, '{:.1f}_x'.format(self.p2)][2]
                    W_ey = self._dfs.loc[mat, '{:.1f}_y'.format(self.p1)][2] + \
                            self._dfs.loc[mat, '{:.1f}_y'.format(self.p2)][2]

                W_X.extend([W_x, W_x])
                W_Y.extend([W_y, W_y])
                W_X1.extend([W_x - W_ex, W_x])
                W_Y1.extend([W_y, W_y - W_ey])
                W_X2.extend([W_x + W_ex, W_x])
                W_Y2.extend([W_y, W_y + W_ey])

            return {
                # loading data
                'W_x': [(slice(None), W_X)],
                'W_y': [(slice(None), W_Y)],
                'W_x0': [(slice(None), W_X1)],
                'W_y0': [(slice(None), W_Y1)],
                'W_x1': [(slice(None), W_X2)],
                'W_y1': [(slice(None), W_Y2)],
            }

    # #########################################################################
    # Iso generator

    def gen_iso_dict(self):
        """Empty dictionary for isotherm display."""
        return {
            'labels': [],
            'doi': [],
            'x': [],
            'y': [],
            'temp': [],
            'color': [],
        }

    # #########################################################################
    # Callback for selection

    def selection_callback(self, attr, old, new):
        """Display selected points on graph and the isotherms."""

        # If the user has not selected anything
        if len(new) == 0:
            # Remove error points:
            self.errors.data = self.gen_error()

            # Reset bottom graphs
            self.g1_iso_sel.data = self.gen_iso_dict()
            self.g2_iso_sel.data = self.gen_iso_dict()
            self.g1_iso_sel.selected.update(indices=[])
            self.g2_iso_sel.selected.update(indices=[])
            self.s_dash.p_g1iso.x_range.end = 1
            self.s_dash.p_g1iso.y_range.end = 1
            self.s_dash.p_g2iso.x_range.end = 1
            self.s_dash.p_g2iso.y_range.end = 1

            # done here
            return

        # If the user has selected more than one point
        # Display error points:
        self.errors.data = self.gen_error(new)

        # Reset bottom graphs
        self.g1_iso_sel.data = self.gen_iso_dict()
        self.g2_iso_sel.data = self.gen_iso_dict()
        self.g1_iso_sel.selected.update(indices=[])
        self.g2_iso_sel.selected.update(indices=[])
        self.s_dash.p_g1iso.x_range.end = 1
        self.s_dash.p_g1iso.y_range.end = 1
        self.s_dash.p_g2iso.x_range.end = 1
        self.s_dash.p_g2iso.y_range.end = 1

        # If we have only one point then we display isotherms
        if len(new) == 1:
            # Generate bottom graphs
            Thread(target=self.populate_isos, args=[new[0], 'g1']).start()
            Thread(target=self.populate_isos, args=[new[0], 'g2']).start()

    # #########################################################################
    # Isotherm interactions

    def populate_isos(self, index, ads):
        """Threaded code to add isotherms to bottom graphs."""

        mat = self.data.data['labels'][index]

        if ads == 'g1':

            loading = self._dfs.loc[mat, (self.g1, 'mL')]
            pressure = [p * 0.5 for p in range(len(loading) + 1)]

            self.doc.add_next_tick_callback(
                partial(
                    self.iso_update_g1,
                    iso = ['median', loading, pressure, '', ''], color = 'k'))

            for iso in self._dfs.loc[mat, (self.g1, 'iso')]:

                parsed=load_isotherm(iso)

                # update the document from callback
                if parsed:
                    self.doc.add_next_tick_callback(
                        partial(self.iso_update_g1, iso = parsed))

        elif ads == 'g2':

            loading=self._dfs.loc[mat, (self.g2, 'mL')]
            pressure=[p * 0.5 for p in range(len(loading) + 1)]

            self.doc.add_next_tick_callback(
                partial(
                    self.iso_update_g2,
                    iso = ['median', loading, pressure, '', ''], color = 'k'))

            for iso in self._dfs.loc[mat, (self.g2, 'iso')]:
                parsed=load_isotherm(iso)

                # update the document from callback
                if parsed:
                    self.doc.add_next_tick_callback(
                        partial(self.iso_update_g2, iso = parsed))

    @gen.coroutine
    def iso_update_g1(self, iso, color=None):
        if not color:
            color=next(self.c_cyc)
        self.g1_iso_sel.stream({
            'labels': [iso[0]],
            'x': [iso[2]],
            'y': [iso[1]],
            'doi': [iso[3]],
            'temp': [iso[4]],
            'color': [color],
        })
        if float(iso[2][-1]) > self.s_dash.p_g1iso.x_range.end:
            self.s_dash.p_g1iso.x_range.end = float(iso[2][-1])
        if float(iso[1][-1]) > self.s_dash.p_g1iso.y_range.end:
            self.s_dash.p_g1iso.y_range.end = float(iso[1][-1])

    @gen.coroutine
    def iso_update_g2(self, iso, color=None):
        if not color:
            color = next(self.c_cyc)
        self.g2_iso_sel.stream({
            'labels': [iso[0]],
            'x': [iso[2]],
            'y': [iso[1]],
            'doi': [iso[3]],
            'temp': [iso[4]],
            'color': [color],
        })
        if float(iso[2][-1]) > self.s_dash.p_g2iso.x_range.end:
            self.s_dash.p_g2iso.x_range.end = float(iso[2][-1])
        if float(iso[1][-1]) > self.s_dash.p_g2iso.y_range.end:
            self.s_dash.p_g2iso.y_range.end = float(iso[1][-1])