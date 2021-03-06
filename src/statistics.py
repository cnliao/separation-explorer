import numpy as np
import pandas as pd
from contextlib import contextmanager


@contextmanager
def _group_selection_context(groupby):
    """
    Set / reset the _group_selection_context.
    """
    groupby._set_group_selection()
    yield groupby
    groupby._reset_group_selection()


def stats(series):

    no_nan = series.dropna()
    size = len(no_nan)

    if size == 0:
        med, std = np.nan, 0
    elif size == 1:
        med, std = float(no_nan), 0
    elif 1 < size <= 4:
        med, std = np.median(no_nan), np.std(no_nan)
    elif 4 < size:
        # Compute IQR
        Q3, Q1 = np.nanpercentile(
            sorted(no_nan), [75, 25], interpolation='linear')
        IQR = Q3 - Q1
        o_rem = no_nan[(Q1 - 1.5 * IQR < no_nan) | (no_nan > Q3 + 1.5 * IQR)]
        med, std = np.median(o_rem), np.std(o_rem)

    return pd.Series((size, med, std),
                     index=(["size", "med", "err"]),
                     name=series.name)


def calc_kpi(data):
    with _group_selection_context(data):
        return data.apply(
            lambda x: pd.concat(
                [stats(s) for _, s in x.items()],
                axis=1, sort=False)
        ).unstack()


def select_data(data, i_type, t_abs, t_tol, g1, g2):
    """Generate two-ads dataframe when selected."""
    if i_type:
        dft = data[
            (data['type'] == i_type) &
            (data['t'].between(t_abs - t_tol, t_abs + t_tol))
        ]
    else:
        dft = data[data['t'].between(t_abs - t_tol, t_abs + t_tol)]

    g1_filt = dft[dft['ads'] == g1]
    g2_filt = dft[dft['ads'] == g2]
    common = list(set(g1_filt['mat'].unique()).intersection(
        g2_filt['mat'].unique()))

    if len(common) == 0:
        return None

    return pd.merge(
        calc_kpi(g1_filt[g1_filt['mat'].isin(common)].drop(
            columns=['type', 't', 'ads']).groupby('mat', sort=False)),
        calc_kpi(g2_filt[g2_filt['mat'].isin(common)].drop(
            columns=['type', 't', 'ads']).groupby('mat', sort=False)),
        on=('mat'), suffixes=('_x', '_y'))


def select_data_single(data, i_type, t_abs, t_tol, g1):
    """Generate two-ads dataframe when selected."""
    if i_type:
        dft = data[
            (data['type'] == i_type) &
            (data['t'].between(t_abs - t_tol, t_abs + t_tol))
        ]
    else:
        dft = data[data['t'].between(t_abs - t_tol, t_abs + t_tol)]

    return calc_kpi(dft[dft['ads'] == g1].drop(columns=['type', 't', 'ads']).groupby('mat', sort=False))


def get_isohash(data, i_type, t_abs, t_tol, ads, mat):

    if i_type:
        dft = data[data['type'] == i_type]
    else:
        dft = data

    return dft[
        (dft['t'].between(t_abs - t_tol, t_abs + t_tol)) &
        (dft['ads'] == ads) &
        (dft['mat'] == mat)
    ].index


def find_nearest(array, value):
    return array[(np.abs(array - value)).argmin()]
