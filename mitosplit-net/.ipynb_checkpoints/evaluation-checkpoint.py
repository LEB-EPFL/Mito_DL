import numpy as np
from skimage import filters, measure
from tqdm import tqdm
import tensorflow as tf

def predict(input_test, model):
    try:
        return model.predict(input_test)[:, :, :, 0].astype(np.float32)
    except:
        nb_models = len(model)
        pred_output_test = np.zeros((nb_models, *input_test.shape), dtype=np.float32)
        for model_id, model_name in enumerate(models):
            pred_output_test[model_id] = model[model_name].predict(input_test)[:, :, :, 0]
        return pred_output_test

def label(pred_outputs, threshold=None):
    if threshold is None:
        threshold = filters.threshold_otsu(pred_outputs)
    if isinstance(threshold, (int, np.integer, float, np.floating)):
        return measure.label(pred_outputs > threshold).astype(int)
    
    if len(pred_outputs)==len(threshold):
        labels = np.zeros(pred_outputs.shape, dtype=np.uint8)
        for i in range(labels.shape[0]):
            labels[i] = measure.label(pred_outputs[i] > threshold[i])
        return labels
    else:
        raise ValueError("'pred_outpus' and 'threshold' lenghts don't match.")

def fissionStats(true_labels, pred_labels):
    """Calculates TP, FP and FN of detected fissions (pred_labels) by comparing them to true fissions (true_labels)."""
    TP, FN, FP = 0, 0, 0
    used_pred_labels = np.zeros(pred_labels.shape, dtype=bool) #Mask of labels
    if np.any(true_labels!=0):
        for true_fission in np.unique(true_labels)[1:]: #Positives, first label is the bg_label=0
            overlapping_fissions = np.unique(pred_labels[true_labels==true_fission]) 
            overlapping_fissions = overlapping_fissions[overlapping_fissions!=0] #All of the pred_labels that overlap with true_fission
            if len(overlapping_fissions)>0: 
                TP += 1  #Add a TP if there is at least one pred_label that overlaps with the true fission
                for pred_fission in overlapping_fissions:
                    used_pred_labels[pred_labels==pred_fission] = True #Register used labels in a mask
            else:
                FN += 1 #Add a FN if the true fission was not detected
        remaining_pred_labels = np.unique(pred_labels[~used_pred_labels]) #Keep only pred_labels that are not in contact with true_labels
        remaining_pred_labels = remaining_pred_labels[remaining_pred_labels!=0]
        if len(remaining_pred_labels)>0:
            FP = len(remaining_pred_labels) #Remove bg_label=0 (index=0) and add the remaining_pred_labels as FP
    return np.array([TP, FP, FN])

def fissionStatsStack(true_labels, pred_labels):
    """Iterates fissionStats"""
    if true_labels.ndim==2:
        return fissionStats(true_labels, pred_labels)
    
    stats = np.zeros(3, dtype=np.int16)
    for true_lab, pred_lab in tqdm(zip(true_labels, pred_labels), total=true_labels.shape[0]):
        stats += fissionStats(true_lab, pred_lab)
    return stats
      
def confusion_matrix(outputs, predictions, threshold):
    """Confusion matrix of fission detections """
    out_binary = outputs>0
    nb_pixels = out_binary.size

    if isinstance(threshold, (int, np.integer, float, np.floating)):
        conf_matrix = np.zeros((2, 2), dtpye=int)
        pred_binary = predictions>threshold

        tp_mask = out_binary & pred_binary
        fn_mask = out_binary & (~pred_binary)
        fp_mask = (~out_binary) & pred_binary

        conf_matrix[0, 0] = tp_mask.sum() #True Positives
        conf_matrix[0, 1] = fn_mask.sum() #False Negatives
        conf_matrix[1, 0] = fp_mask.sum() #False Positives
        conf_matrix[1, 1] = nb_pixels - conf_matrix[0, 0] - conf_matrix[0, 1] - conf_matrix[1, 0] #True Negatives
        return conf_matrix

    nb_thr = len(threshold)
    conf_matrix = np.zeros((nb_thr, 2, 2), dtype=int)
    for i, thr in tqdm(enumerate(threshold), total=nb_thr):
        pred_binary = predictions>thr
    
        tp_mask = out_binary & pred_binary
        fn_mask = out_binary & (~pred_binary)
        fp_mask = (~out_binary) & pred_binary

        conf_matrix[i, 0, 0] = tp_mask.sum() #True Positives
        conf_matrix[i, 0, 1] = fn_mask.sum() #False Negatives
        conf_matrix[i, 1, 0] = fp_mask.sum() #False Positives
        conf_matrix[i, 1, 1] = nb_pixels - conf_matrix[i, 0, 0] - conf_matrix[i, 0, 1] - conf_matrix[i, 1, 0] #True Negatives
    
    return conf_matrix

def get_metrics(outputs, predictions, threshold):
    conf_matrix = confusion_matrix(outputs, predictions, threshold)
    
    if isinstance(threshold, (int, float)):
        tp = conf_matrix[0, 0]
        fn = conf_matrix[0, 1]
        fp = conf_matrix[1, 0]
        tn = conf_matrix[1, 1]
    else:
        tp = conf_matrix[:, 0, 0]
        fn = conf_matrix[:, 0, 1]
        fp = conf_matrix[:, 1, 0]
        tn = conf_matrix[:, 1, 1]
    
    metrics = {'binary accuracy': (tp+tn)/(tp+tn+fp+fn), 
               'precision': tp/(tp+fp), 
               'TPR': tp/(tp+fn),
               'FPR': fp/(fp+tn)}
    metrics['F1-score'] = 2*(metrics['precision']*metrics['TPR'])/(metrics['precision']+metrics['TPR'])
    return metrics

def detection_match(y_true, y_pred, threshold=0.99):
    total = y_true.shape[0]
    isTrue = np.any(np.any(y_true, axis=-1), axis=-1)
    isPred = np.any(np.any(y_pred>=threshold, axis=1), axis=1)
    return np.sum(np.equal(isPred[None, :], isTrue), axis=1)/total

def get_AUC(metrics):
    AUC = {}
    for model_name in metrics:
        x = metrics[model_name]['TPR']
        y = metrics[model_name]['precision']

        nan_mask = (~np.isnan(x)) & (~np.isnan(y))

        x = x[nan_mask]
        y = y[nan_mask]

        id_sort = np.argsort(x)
        AUC[model_name] = np.trapz(y[id_sort], x=x[id_sort])
    
    return AUC
