from scipy.ndimage import find_objects
from scipy.ndimage import measurements
import numpy as np


def _get_superpixel_means_band(label_array: np.ndarray,
                               band: np.ndarray) -> np.ndarray:
    # Assume labels are 0, 1, 2, ..., n
    # scipy wants labels to begin at 1 and transforms to 1, 2, ..., n+1
    labels_ = label_array + 1
    labels_unique = np.unique(labels_)
    means = measurements.mean(band, labels=labels_, index=labels_unique)
    return means.reshape((-1, 1))


def get_superpixel_means_as_features(label_array: np.ndarray,
                                     img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 2:
        measurements = _get_superpixel_means_band(label_array, img)
    elif len(img.shape) == 3:
        temp = [_get_superpixel_means_band(label_array,
                                           img[..., k])
                for k in range(img.shape[2])]
        measurements = np.concatenate(temp, axis=1)
    else:
        raise ValueError('img must be 2d or 3d array')
    return measurements


def get_array_from_features(label_array: np.ndarray,
                            features: np.ndarray) -> np.ndarray:
    """
    Using p x q segmentation labels (2d) and feature array with dimension (m x
    n) where m is the number of unique labels and n is the number of features,
    obtain a p x q x m channel array in which each spatial segment is labeled
    according to n-features.
    See `find_objects` found
    [here](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.find_objects.html)
    for the crucial scipy function used.
    Parameters
    ----------
    label_array : np.array
        p x q integer array of labels corresponding to superpixels
    features : np.array
        m x n array of features - M corresponds to number of distinct items to
        be classified and N number of features for each item.
    Returns
    -------
    out : np.array
        p x q (x n) array where we drop the dimension if n == 1.
    Notes
    ------
    Inverse of get_features_from_array with fixed labels, namely if `f` are
    features and `l` labels, then:
        get_features_from_array(l, get_array_from_features(l, f)) == f
    And similarly, if `f_array` is an array of populated segments, then
        get_array_from_features(l, get_features_from_array(l, f)) == f
    """
    # Assume labels are 0, 1, 2, ..., n
    if len(features.shape) != 2:
        raise ValueError('features must be 2d array')
    elif features.shape[1] == 1:
        out = np.zeros(label_array.shape, dtype=features.dtype)
    else:
        m, n = label_array.shape
        out = np.zeros((m, n, features.shape[1]), dtype=features.dtype)

    labels_p1 = label_array + 1
    indices = find_objects(labels_p1)
    labels_unique = np.unique(labels_p1)
    # ensures that (number of features) == (number of unique superpixel labels)
    assert(len(labels_unique) == features.shape[0])
    for k, label in enumerate(labels_unique):
        indices_temp = indices[label-1]
        # if features is m x 1, then do not need extra dimension when indexing
        label_slice = labels_p1[indices_temp] == label
        if features.shape[1] == 1:
            out[indices_temp][label_slice] = features[k, 0]
        # if features is m x n with n > 1, then requires extra dimension when
        # indexing
        else:
            out[indices_temp + (np.s_[:], )][label_slice] = features[k, ...]
    return out


def scale_img(img: np.ndarray,
              new_min: int = 0,
              new_max: int = 1) -> np.ndarray:
    """
    Scale an image by the absolute max and min in the array to have dynamic
    range new_min to new_max. Useful for visualization.
    Parameters
    ----------
    img : np.ndarray
    new_min : int
    new_max : int
    Returns
    -------
    np.ndarray:
       New image with shape equal to img, scaled to [new_min, new_max]
    """
    i_min = np.nanmin(img)
    i_max = np.nanmax(img)
    if i_min == i_max:
        # then image is constant image and clip between new_min and new_max
        return np.clip(img, new_min, new_max)
    img_scaled = (img - i_min) / (i_max - i_min) * (new_max - new_min)
    img_scaled += new_min
    return img_scaled
