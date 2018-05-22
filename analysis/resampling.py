from analysis import analysis_utils as au
from multiprocessing import Process
from multiprocessing import Queue
import numpy as np
import os
import pandas as pd

def compute_two_side_p_val(resampled_df, original_D_hat_df, neuron):
    """Compute a two-sided p-value for permutation test
    
        IMPORTANT: Use this function in place when the data you resampled does 
        not is not normally distributed. 
       
       Args:
           resampled_df: a Pandas DataFrame of all the rates computed after resampling.
           original_D_hat_df: a Pandas DataFrame with a single row of all the ACTUAL 
           rate values that were computed for a given set of neurons.
           neuron: the name of the neuron column vector to compute the 2-sided p valaue for.
       
       Returns:
           the two-sided p-value for a given neuron column vector 
    """
    return (1 / len(resampled_df.index)) * len(resampled_df.loc[:, neuron].loc[abs(resampled_df[neuron]) >= abs(original_D_hat_df[neuron].values[0])])

def get_num_of_events(dataframe, neuron):
    """Get the number of signal spikes for a given column vector
       
       Args:
           dataframe: a Pandas DataFrame that contains at least one 
           neuron's signal data, in column vector form.
           neuron: the name of the neuron column vector to get the 
           number of events for. 
       
       Returns:
           the amount of datapoints in a given column vector with 
           of nonzero value.
    """
    return len(dataframe.loc[:, neuron][dataframe[neuron] != 0])
    
def shuffle(total_experiments, neuron_and_behavior_df, neuron_activity_df, behavior1, behavior2):
    """Homebrewed resampling function for EPM Analysis
    
    Resampling function that gives the capability to "simulate"
    experiments using random shuffling of the observations for each 
    pandas dataframe. 
    
    Args: 
        total_experiments: the total amount of epxeriments to simulate via bootstrapping
        neuron_and_behavior_df: the concatenated neuron activity and behavior dataframes
        for a given animal
        neuron_activity_df: the neuron activity dataframe for a given animal
        behavior: the specific behavior to simulate the experiments on
    
    Returns: a (vertically) concatenated pandas DataFrame of all the shuffled DataFrames 
    that all the shuffle_worker processes produced
    """
    experiments_per_worker = total_experiments // os.cpu_count() 
    q = Queue()
    processes = []
    rets = []
    for _ in range(0, os.cpu_count()):
        p = Process(target=shuffle_worker, args=(q, experiments_per_worker, neuron_activity_df, neuron_and_behavior_df, behavior1, behavior2))
        processes.append(p)
        p.start()
    for p in processes:
        ret = q.get()  # will block
        rets.append(ret)
    for p in processes:
        p.join()

    return pd.concat(rets, ignore_index=True)

def shuffle_worker(q, num_of_experiments, neuron_activity_df, neuron_and_behavior_df, behavior1, behavior2):
    """Helper function for shuffle()

    Given a certain number of experiments to simulate, this function will
    add a dataframe to a provided queue full of the amount of experiments 
    desired as obervations rows. 
    Note: This function is meant to be only be used as a helper function 
    for the shuffle() function

    Args:
        q: the blocking queue to which the resulting dataframe will be added to
        num_of_experiments: the number of experiments that will be simulated 
        and appended, as observations, to the dataframe to be returned
        neuron_activity_df: the neuron activity dataframe for a given mouse
        neuron_and_behavior_df: the concatenated neuron activity and behavior 
        dataframes for a given mouse 
        behavior: the specific behavior to simulate the experiments on
    """ 
    first_col = neuron_activity_df.columns[0]
    last_col = neuron_activity_df.columns[len(neuron_activity_df.columns)-1]
    shuffled_df = pd.DataFrame(columns=neuron_activity_df.columns)
    
    for index in range(num_of_experiments):
        neuron_and_behavior_df.loc[:, first_col:last_col] = neuron_and_behavior_df.loc[:, first_col:last_col].sample(frac=1).reset_index(drop=True)
        shuffled_df.loc[index] = au.compute_diff_rate(neuron_and_behavior_df, neuron_activity_df, behavior1, behavior2)

    q.put(shuffled_df)
    
def classify_neurons_non_parametrically(dataframe, resampled_df, real_diff_df, p_value=0.05, threshold=10):
    """Classify neurons as selective or not-selective
    
        IMPORTANT: Use this function if your resampled data is NOT normally distributed. 
        Remember that this function can only tell you if a neuron is selective
        for a certain behavior or not. It will not classify what behavior the 
        behavior the neuron was actually selective for.

       Args:
           dataframe: a Pandas DataFrame that contains the neuron(s) column vector(s) to be classified.
           resampled_df: the Pandas Dataframe of all the computed rates after resampling.
           real_diff_df: a Pandas DataFrame with one row that has the real difference of means
           p_value: the cutoff value for the probability that an effect could occur by chance.
           threshold: the minimum required number of events for a neuron to be considered classifiable, 
           default is 10.

       Returns:
           classified_neurons: a dictionary of key-value pairs, where the name of each classified 
           neuron is a key, and that neuron's classification is the corresponding value. 
    """
    classified_neurons = dict()
    for neuron in dataframe.columns:
        if get_num_of_events(dataframe, neuron) < threshold:
            if not neuron in classified_neurons:
                classified_neurons[neuron] = "unclassified"
                
    for neuron in resampled_df.columns:
        if compute_two_side_p_val(resampled_df, real_diff_df, neuron) <= p_value:
            if not neuron in classified_neurons:
                classified_neurons[neuron] = "selective"
        else:
            if not neuron in classified_neurons:
                classified_neurons[neuron] = "not-selective"
                
    return classified_neurons

def two_tailed_neuron_classification(resampled_df, real_d_df, neuron, behavior_name, high_tail, low_tail):
    """Classifies a given neuron as selective for a behavior, non-selective for a behavior, or not-selective
    
    IMPORTANT: Use this function ONLY if your resampled data is indeed normally distributed. 
    Classifies a given neuron as selective for a certain behavior, selective for 
    when that behavior is not performed, or non-selective. 
    Although one can use this as a stand alone function to classify a single neuron for 
    a certain animal as either a <behavior> neuron, a "Not"-<behavior> neuron, or
    a "Non-selective" neuron, it is meant to be used a helper function for the 
    classify_neurons_parametrically() function.
    
    Args: 
        resampled_df: a resampled Pandas DataFrame with all the possible rates
        real_diff_df: a pandas DataFrame with one row that has the real difference of means
        values for a given animal and a corresponding behavior
        neuron: a single neuron of the neuron to classify use the 2-tailed hypothesis test
        behavior_name: the behavior to classify the neuron by, e.g. "Running" or "Non-Running"
        high_tail: the cutoff for the upper-tail of the distribution
        low_tail: the cutoff for the lower-tail of the distribution
    
    Returns:
        behavior_name, Not-<behavior_name>, or "Not-selective"; based on the result of the
        two-tailed hypothesis test. 
    """
    if real_d_df[neuron]['d'] >= np.percentile(resampled_df[neuron], high_tail):
        return behavior_name
    elif real_d_df[neuron]['d'] <= np.percentile(resampled_df[neuron], low_tail):
        return "Non-" + behavior_name
    else: 
        return "Not-selective"
    
def classify_neurons_parametrically(dataframe, resampled_df, real_diff_df, behavior_name, high_tail, low_tail, threshold=10):
    """Classifies a given set of neurons
    
    This function simply calls is_neuron_selective for all the neurons 
    for a given animal. 
    
    Args: 
        resampled_df: a resampled Pandas DataFrame
        real_diff_df: a Pandas DataFrame with one row that has the real difference of means.
        behavior_name: the behavior to classify each neuron by, e.g. "Running" or "Non-Running"
        high_tail: the cutoff for the upper-tail of the distribution
        low_tail: the cutoff for the lower-tail of the distribution
        threshold: the minimum required number of events for a neuron to be considered classifiable, 
        default is 10.
    
    Returns: 
        classified_neurons: a dictionary of key-value pairs, where the name of each classified 
        neuron is a key, and that neuron's classification is the corresponding value. 
    """
    classified_neurons = dict()
    for neuron in dataframe.columns:
        if get_num_of_events(dataframe, neuron) < threshold:
            if not neuron in classified_neurons:
                classified_neurons[neuron] = "unclassified"

    for neuron in resampled_df.columns:
        if not neuron in classified_neurons:
            classified_neurons[neuron] = two_tailed_neuron_classification(resampled_df, real_diff_df, neuron, behavior_name, high_tail, low_tail)

    return classified_neurons