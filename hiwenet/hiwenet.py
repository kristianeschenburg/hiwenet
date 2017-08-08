import argparse
import os
import sys
import warnings
import networkx as nx
import numpy as np

list_medpy_histogram_metrics = np.array([
    'chebyshev', 'chebyshev_neg', 'chi_square',
    'correlate', 'correlate_1',
    'cosine', 'cosine_1', 'cosine_2', 'cosine_alt',
    'euclidean', 'fidelity_based',
    'histogram_intersection', 'histogram_intersection_1',
    'jensen_shannon', 'kullback_leibler', 'manhattan', 'minowski',
    'noelle_1', 'noelle_2', 'noelle_3', 'noelle_4', 'noelle_5',
    'relative_bin_deviation', 'relative_deviation'])

metric_list = [
    'kullback_leibler', 'manhattan', 'minowski', 'euclidean',
    'cosine_1',
    'noelle_2', 'noelle_4', 'noelle_5' ]

unknown_prop_list = ['histogram_intersection']
still_under_dev = ['quadratic_forms']
similarity_func = ['correlate', 'cosine', 'cosine_2', 'cosine_alt', 'fidelity_based']

semi_metric_list = [
    'jensen_shannon', 'chi_square',
    'chebyshev', 'chebyshev_neg',
    'histogram_intersection_1',
    'relative_deviation', 'relative_bin_deviation',
    'noelle_1', 'noelle_3',
    'correlate_1']

minimum_num_bins = 5

default_weight_method = 'kullback_leibler'
default_num_bins = 100
default_trim_percentile = 5

def __compute_bin_edges(features, num_bins, trim_outliers, trim_percentile):
    "Compute the edges for the histogram bins to keep it the same for all nodes."

    if trim_outliers:
        # percentiles_to_keep = [ trim_percentile, 1.0-trim_percentile] # [0.05, 0.95]
        edges_of_edges = np.array([np.percentile(features, trim_percentile),
                                   np.percentile(features, 100 - trim_percentile)])
    else:
        edges_of_edges = np.array([np.min(features), np.max(features)])

    # Edges computed using data from all nodes, in order to establish correspondence
    edges = np.linspace(edges_of_edges[0], edges_of_edges[1], num=num_bins, endpoint=True)

    return edges


def extract(features, groups, weight_method='histogram_intersection',
            num_bins=default_num_bins, trim_outliers=True, trim_percentile=5,
            return_networkx_graph=False, out_weights_path=None):
    """
    Extracts the histogram weighted network.
    
    Parameters
    ----------
    features : numpy 1d array of length p
        with scalar values.
    groups : numpy 1d array
        Membership array of length p, each value specifying which group that particular node belongs to.
        For example, if you have a cortical thickness values for 1000 vertices belonging to 100 patches,
        this array could  have numbers 1 to 100 specifying which vertex belongs to which cortical patch.
        Grouping with numerical values (contiguous from 1 to num_patches) is strongly recommended for simplicity,
        but this could also be a list of strings of length p, in which case a tuple is
        returned identifying which weight belongs to which pair of patches.
    weight_method : string, optional
        identifying the type of distance (or metric) to compute between the pair of histograms.
        It must be one of the methods implemented in medpy.metric.histogram: 
        [ 'chebyshev', 'chebyshev_neg', 'chi_square', 'correlate', 'correlate_1', 
        'cosine', 'cosine_1', 'cosine_2', 'cosine_alt', 'euclidean', 'fidelity_based',
        'histogram_intersection', 'histogram_intersection_1', 'jensen_shannon', 'kullback_leibler', 
        'manhattan', 'minowski', 'noelle_1', 'noelle_2', 'noelle_3', 'noelle_4', 'noelle_5', 
        'relative_bin_deviation', 'relative_deviation'] except 'quadratic_forms'.
        Note only the following are metrics: ['manhattan', 'minowski', 'euclidean', 'noelle_2', 'noelle_4', 'noelle_5'],
        the following are semi- or quasi-metrics: [ 'kullback_leibler', 'jensen_shannon', 'chi_square', 'chebyshev',
        'cosine_1', 'chebyshev_neg', 'correlate_1', 'histogram_intersection_1', 'relative_deviation', 'relative_bin_deviation',
        'noelle_1', 'noelle_3'] and the rest are similarity functions:
            ['histogram_intersection', 'correlate', 'cosine', 'cosine_2', 'cosine_alt', 'fidelity_based']
    num_bins : scalar, optional
        Number of bins to use when computing histogram within each patch/group.
        Note:
        1) Please ensure same number of bins are used across different subjects
        2) histogram shape can vary widely with number of bins (esp with fewer bins in the range of 3-20),
        and hence the features extracted based on them vary also.
        3) It is recommended to study the impact of this parameter on the final results of the experiment.
        This could also be optimized within an inner cross-validation loop if desired.
    trim_outliers : bool, optional
        Whether to trim 5% outliers at the edges of feature range,
        when features are expected to contain extreme outliers (like 0 or eps or Inf).
        This is important to avoid numerical problems and also to stabilize the weight estimates.
    trim_percentile : float
        Small value specifying the percentile of outliers to trim.
        Default: 5 (5%). Must be in open interval (0, 100).
    return_networkx_graph : bool, optional
        Specifies the need for a networkx graph populated with weights computed. Default: False.
    out_weights_path : str, optional
        Where to save the extracted weight matrix. If networkx output is returned, it would be saved in GraphML format. Default: nothing saved.

    Returns
    -------
    edge_weights : numpy 2d array of pair-wise edge-weights. 
        Size: num_groups x num_groups, wherein num_groups is determined by the total number of unique values in groups.
        Only the upper triangular matrix is filled as the distance between node i and j would be the same as j and i.
        The edge weights from the upper triangular matrix can easily be obtained by
        weights_array = edge_weights[ np.triu_indices_from(edge_weights, 1) ]
    """

    # parameter check
    features, groups, num_bins, weight_method, group_ids, num_groups, num_links = __parameter_check(
        features, groups, num_bins, weight_method, trim_outliers, trim_percentile)

    # using the same bin edges for all nodes/groups to ensure correspondence
    edges = __compute_bin_edges(features, num_bins, trim_outliers, trim_percentile)

    if return_networkx_graph:
        nx_graph = nx.Graph()
        nx_graph.add_nodes_from(np.arange(num_groups))
    else:
        edge_weights = np.zeros([num_groups, num_groups], order='F')

    exceptions_list = list()
    for g1 in xrange(num_groups):
        index1 = groups == group_ids[g1]
        hist_one = __compute_histogram(features[index1], edges)

        for g2 in xrange(g1 + 1, num_groups, 1):
            index2 = groups == group_ids[g2]
            hist_two = __compute_histogram(features[index2], edges)

            try:
                edge_value = _compute_edge_weight(hist_one, hist_two, weight_method)
                if return_networkx_graph:
                    nx_graph.add_edge(group_ids[g1], group_ids[g2], weight=edge_value)
                else:
                    edge_weights[g1, g2] = edge_value
            except BaseException as exc:
                # numerical instabilities can cause trouble for histogram distance calculations
                exceptions_list.append(str(exc))
                warnings.warn('Unable to compute edge weight between {} and {}. Skipping it.'.format(group_ids[g1], group_ids[g2]))

    error_thresh = 0.05
    if len(exceptions_list) >= error_thresh*num_links:
        print('All exceptions encountered so far:\n {}'.format('\n'.join(exceptions_list)))
        raise ValueError('Weights for {:.2f}% of edges could not be computed.'.format(error_thresh*100))

    if return_networkx_graph:
        if out_weights_path is not None:
           nx_graph.write_graphml(out_weights_path) 
        return nx_graph
    else:
        if out_weights_path is not None:
            np.savetxt(out_weights_path, edge_weights)
        return edge_weights


def __compute_histogram(values, edges):
    """Computes histogram (density) for a given vector of values."""

    hist, bin_edges = np.histogram(values, bins=edges, density=True)
    hist = __preprocess_histogram(hist, values, edges)

    return hist


def __preprocess_histogram(hist, values, edges):
    """Handles edge-cases and extremely-skewed histograms"""

    # working with extremely skewed histograms
    if np.count_nonzero(hist) == 0:
        # all of them above upper bound
        if np.all(values >= edges[-1]):
            hist[-1] = 1
        # all of them below lower bound
        elif np.all(values <= edges[0]):
            hist[0] = 1

    return hist


def _compute_edge_weight(hist_one, hist_two, weight_method_str):
    """
    Computes the edge weight between the two histograms.
    
    Parameters
    ----------
    hist_one : sequence
        First histogram
    hist_two : sequence
        Second histogram
    weight_method_str : string
        Identifying the type of distance (or metric) to compute between the pair of histograms.
        Must be one of the metrics implemented in medpy.metric.histogram
        
    Returns
    -------
    edge_value : float
        Distance or metric between the two histograms
    """

    from medpy.metric import histogram as medpy_hist_metrics

    weight_method = getattr(medpy_hist_metrics, weight_method_str)
    edge_value = weight_method(hist_one, hist_two)

    return edge_value


def _identify_groups(groups):
    """
    To compute number of unique elements in a given membership specification.
    
    Parameters
    ----------
    groups : numpy 1d array of length p, each value specifying which group that particular node belongs to.
        For examlpe, if you have a cortical thickness values for 1000 vertices belonging to 100 patches, 
        this array could  have numbers 1 to 100 specifying which vertex belongs to which cortical patch.
        Although grouping with numerical values (contiguous from 1 to num_patches) is strongly recommended for simplicity, 
        this could also be a list of strings of length p.

    Returns
    -------
    group_ids : numpy array of values identifying the unique groups specified
    num_groups : scalar value denoting the number of unique groups specified

    """

    group_ids = np.unique(groups)
    num_groups = len(group_ids)

    if num_groups < 2:
        raise ValueError('There must be atleast two nodes or groups in data, for pair-wise edge-weight calculations.')

    return group_ids, num_groups


def _range_check_parameters(num_bins, num_groups, num_values, trim_outliers, trim_percentile):
    """Ensuring the parameters are in valid ranges."""

    if num_bins < minimum_num_bins:
        raise ValueError('Too few bins! The number of bins must be >= 5')

    if num_values < num_groups:
        raise ValueError('Insufficient number of values in features (< number of nodes), or invalid membership!')

    if trim_outliers:
        if trim_percentile < 0 or trim_percentile >= 100:
            raise ValueError('percentile of tail values to trim must be in the semi-open interval [0,1).')
    elif num_values < 2:
        raise ValueError('too few features to compute minimum and maximum')

    return


def _type_cast_parameters(num_bins, features, groups):
    """Casting inputs to required types."""

    num_bins = np.rint(num_bins)

    if np.isnan(num_bins) or np.isinf(num_bins):
        raise ValueError('Invalid value for number of bins! Choose a natural number >= {}'.format(minimum_num_bins))

    if not isinstance(features, np.ndarray):
        features = np.array(features)

    if not isinstance(groups, np.ndarray):
        groups = np.array(groups)

    return num_bins, features, groups


def __parameter_check(features, groups, num_bins, weight_method, trim_outliers, trim_percentile):
    """Necessary check on values, ranges, and types."""

    num_bins, features, groups = _type_cast_parameters(num_bins, features, groups)
    num_values = len(features)

    # memberships
    group_ids, num_groups = _identify_groups(groups)
    num_links = np.int64(num_groups * (num_groups - 1) / 2.0)

    _range_check_parameters(num_bins, num_groups, num_values, trim_outliers, trim_percentile)

    if weight_method not in list_medpy_histogram_metrics:
        raise NotImplementedError('Chosen histogram distance/metric not implemented or invalid.')

    return features, groups, num_bins, weight_method, group_ids, num_groups, num_links


def __run():
    "Main entry point from the command line."

    features_path, groups_path, weight_method, num_bins, \
        trim_outliers, trim_percentile, return_networkx_graph, out_weights_path = __parse_args()
    
    # TODO add the possibility to process multiple combinations of parameters: diff subjects, diff metrics
    # for features_path to be a file containing multiple subjects (one/line)
    # -w could take multiple values kldiv,histint,
    # each line: input_features_path,out_weights_path

    features, groups = __read_features_groups(features_path, groups_path)

    extract(features, groups, weight_method, num_bins, trim_outliers, trim_percentile, return_networkx_graph, out_weights_path)


def __read_features_groups(features_path, groups_path):
    "Reader for data and groups"

    try:
        features = np.loadtxt(features_path)
        groups = np.loadtxt(groups_path)
    except:
        raise IOError('error reading the specified features and/or groups.')

    assert len(features) == len(groups), "lengths of features and groups do not match!"

    return features, groups


def __parse_args():
    """Parser/validator for the cmd line args."""

    parser = argparse.ArgumentParser(prog="hiwenet")

    parser.add_argument("-f", "--in_features_path", action="store", dest="in_features_path",
                        required=True,
                        help="Abs. path to file containing features for a given subject")

    parser.add_argument("-g", "--groups_path", action="store", dest="groups_path",
                        required=True,
                        help="path to a file containing element-wise membership into groups/nodes/patches.")

    parser.add_argument("-w", "--weight_method", action="store", dest="weight_method",
                        default= default_weight_method, required=False,
                        help="Method used to estimate the weight between the pair of nodes. Default : {}".format(default_weight_method))

    parser.add_argument("-o", "--out_weights_path", action="store", dest="out_weights_path",
                        required=False, default = None,
                        help="Where to save the extracted weight matrix. If networkx output is returned, it would be saved in GraphML format. Default: nothing saved.")

    parser.add_argument("-n", "--num_bins", action="store", dest="num_bins",
                        default= minimum_num_bins, required=False,
                        help="Number of bins used to construct the histogram. Default : {}".format(minimum_num_bins))

    parser.add_argument("-t", "--trim_outliers", action="store", dest="trim_outliers",
                        default=True, required=False,
                        help="Boolean flag indicating whether to trim the extreme/outlying values. Default True.")

    parser.add_argument("-p", "--trim_percentile", action="store", dest="trim_percentile",
                        default= default_trim_percentile, required=False,
                        help="Small value specifying the percentile of outliers to trim. "
                             "Default: {0}%% , must be in open interval (0, 100).".format(default_trim_percentile))

    parser.add_argument("-r", "--return_networkx_graph", action="store", dest="return_networkx_graph",
                        default=False, required=False,
                        help="Boolean flag indicating whether to return a networkx graph populated with weights computed. Default: False")

    if len(sys.argv) < 2:
        print('Too few arguments!')
        parser.print_help()
        parser.exit(1)

    # parsing
    try:
        params = parser.parse_args()
    except:
        parser.exit(1)

    # noinspection PyUnboundLocalVariable
    in_features_path = os.path.abspath(params.features_path)
    assert os.path.exists(in_features_path), "Given features file doesn't exist."

    groups_path = os.path.abspath(params.groups_path)
    assert os.path.exists(groups_path), "Given groups file doesn't exist."

    return in_features_path, groups_path, params.weight_method, params.num_bins, \
           params.trim_outliers, params.trim_percentile, params.return_networkx_graph, params.out_weights_path


if __name__ == '__main__':
    __run()