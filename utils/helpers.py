import copy
import random

import h5py
import matplotlib.pyplot as plt
import numpy as np
import scipy
import seaborn as sn
import sklearn
import torch
from torch.utils.data import DataLoader

sn.set()

__all__ = ('createPlots', 'plotEigenvalues', 'oneHotEncoding', 'computeRMSE', 'compute_recall', 'compute_accuracy',
           'computeMeanVariance', 'constructSymmetricIfNotSymmetric', 'compute_precision', 'computePredictions',
           'constructSymmetricMatrix', 'isSymmetric', 'print_accuracy', 'load_kern', 'loadTargets', 'deleteDataset',
           'solve_system_old', 'deleteValues', 'diag_add', 'generateSquareRandomMatrix', 'perturbateMatrix',
           'solve_system')


def createPlots(moments, fractions, title, name, xlabel, ylabel):
    """
    Creates plots for the given moment data on y and fractions data on x with name as title
    @param title: sets the title
    @param moments: contains expected values or variances of the errors
    of the matrix approximation methods on the y-axis
    @param fractions: contains the values for the x-axis
    @param name: specifies name for the plot
    @return: None
    """
    plt.figure()
    plt.rcParams.update({'axes.titlesize': 'small'})
    plt.title(f"{title}")
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.plot(fractions, moments[0], label='svd iteration')
    plt.plot(fractions, moments[2], label='nystroem approximation')
    plt.plot(fractions, moments[1], label='soft impute')
    plt.legend()
    plt.savefig(f'./plots/{name}.svg')


def plotEigenvalues(x: np.ndarray):
    """
    @param x: contains the matrix for which the eigenvalues are computed
    @return: plots the eigenvalues of the given matrix x
    """
    print("Plotting eigenvalues")
    eigenvalues, _ = np.linalg.eigh(x)
    eigenvalues = eigenvalues[::-1]
    max_val = np.max(eigenvalues)
    smaller_vals = eigenvalues / max_val
    print(eigenvalues)
    plt.figure()
    plt.plot(eigenvalues)
    plt.xlabel("Number of eigenvalue")
    plt.ylabel("Eigenvalue")
    plt.title("Plot of the eigenvalues of the K_xx matrix")
    plt.show()
    plt.savefig('./plots/eigenvalues25.svg')
    plt.close()
    plt.figure()
    plt.plot(np.log(eigenvalues))
    plt.xlabel('Number of the eigenvalue')
    plt.ylabel('Log space of eigenvalue')
    plt.title('Plot of the eigenvalues of the K_xx matrix in the log space')
    plt.show()
    plt.savefig('./plots/log_eigenvalues.svg')
    plt.close()
    plt.figure()
    plt.title("Plot of the normalized eigenvalues")
    plt.xlabel("Number of eigenvalue")
    plt.ylabel("Magnitude of normalized eigenvalues")
    plt.plot(np.log(smaller_vals))
    plt.show()
    plt.savefig('./plots/normalized_eigenvalues.svg')
    plt.close()


def oneHotEncoding(Y):
    """
    Creates one hot encoding from given target vector
    @param Y: target vector
    @return: one hot encoding corresponding to Y
    """
    n_classes = Y.max() + 1
    Y_1hot = torch.ones((len(Y), n_classes), dtype=torch.float64).neg_()  # all -1
    Y_1hot[torch.arange(len(Y)), Y] = 1.
    return Y_1hot


def constructSymmetricIfNotSymmetric(x: np.ndarray) -> np.ndarray:
    """
    Checks if the given matrix x is symmetric if not, constructs a symmetric matrix from the upper triangle
    @param x: matrix which is checked and created symmetric
    @return: symmetric matrix of x if x is unsymmetric
    """
    if isSymmetric(x):
        return x
    else:
        return constructSymmetricMatrix(x)


def constructSymmetricMatrixwithTorch(x: torch.float64):  # -> torch.float64:
    # x_sym = torch.zeros_like(x).cuda()
    # x = x.cuda()
    x_up = torch.triu(x)
    x_sym = x_up + torch.transpose(x_up, 0, 1) - torch.diag(torch.diag(x_up))
    return x_sym


def constructSymmetricMatrix(x: np.ndarray) -> np.ndarray:
    """
    Constructs a symmetric matrix given a matrix x only with only entries in the upper triangle
    @param x: matrix only filled in upper triangle
    @return: symmetric matrix based on x
    """
    x_sym = np.empty_like(x)
    x_sym[np.triu_indices(x.shape[0], k=0)] = x[np.triu_indices(x.shape[0], k=0)]
    x_sym = x_sym + x_sym.T - np.diag(np.diag(x_sym))
    return x_sym


def isSymmetric(x, rtol=1e-5, atol=1e-5):
    return np.allclose(x, x.T, rtol=rtol, atol=atol)


def perturbateMatrix(X):
    columns = X.shape[1]
    rows = X.shape[0]
    for row in range(rows):
        ##Sampling
        sample = np.random.randint(0, columns - 1, 3)
        X[row][sample] = np.nan
    return X


def solve_system(Kxx: np.ndarray, Y) -> torch.float64:
    print("Running scipy solve Kxx^-1 Y routine")
    assert Y.dtype == torch.float64, """
    It is important that `Kxx` and `Y` are `float64`s for the inversion,
    even if they were `float32` when being calculated. This makes the
    inversion much less likely to complain about the matrix being singular.
    """
    A, _, _, _ = scipy.linalg.lstsq(
        Kxx, Y.numpy())
    return torch.from_numpy(A)


def solve_system_old(Kxx, Y):
    print("Running scipy solve Kxx^-1 Y routine")
    assert Kxx.dtype == torch.float64 and Y.dtype == torch.float64, """
    It is important that `Kxx` and `Y` are `float64`s for the inversion,
    even if they were `float32` when being calculated. This makes the
    inversion much less likely to complain about the matrix being singular.
    """
    A = scipy.linalg.solve(
        Kxx.numpy(), Y.numpy(), overwrite_a=True, overwrite_b=False,
        check_finite=False, assume_a='pos', lower=False)
    return torch.from_numpy(A)


def diag_add(K, diag):
    if isinstance(K, torch.Tensor):
        K.view(K.numel())[::K.shape[-1] + 1] += diag
    elif isinstance(K, np.ndarray):
        K.flat[::K.shape[-1] + 1] += diag
    else:
        raise TypeError("What do I do with a `{}`, K={}?".format(type(K), K))


def computePredictions(A, Kxvx):
    """
    Computes Kxvx Kxx^-1 Y to obtain the predictions for the points xv
    Computes the predictions of Gaussian Processes Given A = Kxx^(-1) * Y
    and the kernel of the data points for the predictions
    @param A: the result of Kxx^-1 Y
    @param Kxvx: the kernel matrix of the unobserved data points and the observed ones
    @return: predictions for the unobserved data points
    """
    return (Kxvx @ A).argmax(dim=1)


def compute_recall(Y_pred, Y, key):
    """
    Computes the recall given the the predictions and the ground truth labels
    @param Y_pred: predictions of data points
    @param Y: ground truth labels of data points
    @return: recall
    """
    recall = sklearn.metrics.recall_score(Y, Y_pred, average='micro')
    print(f"{key} recall: {recall * 100}%")
    return recall


def compute_precision(Y_pred, Y, key):
    """
    Computes the precision given the predictions and the ground truth labels
    @param Y_pred: predictions of data points
    @param Y: ground truth labels of data points
    @param key: specifies for which dataset the predictions were generated
    @return: precision
    """
    precision = sklearn.metrics.precision_score(Y, Y_pred, average='micro')
    print(f"{key} precision: {precision * 100}%")
    return precision


def compute_accuracy(Y_pred, Y, key):
    accuracy = sklearn.metrics.accuracy_score(Y, Y_pred)
    print(f"{key} accuracy: {accuracy * 100}%")
    return accuracy


def print_accuracy(A, Kxvx, Y, key):
    Ypred = (Kxvx @ A).argmax(dim=1)
    acc = sklearn.metrics.accuracy_score(Y, Ypred)
    print(f"{key} accuracy: {acc * 100}%")


def load_kern(dset, i, diag=False):
    A = np.empty(dset.shape[1:], dtype=np.float32)
    if diag:
        dset.read_direct(A, source_sel=np.s_[i, :])
    else:
        dset.read_direct(A, source_sel=np.s_[i, :, :])
    return torch.from_numpy(A).to(dtype=torch.float64)


def computeRMSE(x: np.ndarray, y: np.ndarray) -> np.float:
    """
    @param x: original matrix which has all entries
    @param y: matrix which was filled by matrix completion algorithms
    @return: RMSE (root mean squared error) between the two matrices x and y
    """
    diff = x - y
    diff = diff ** 2
    return np.sqrt(np.sum(diff) / (x.shape[0] * x.shape[1]))


def generateSquareRandomMatrix(columns: int) -> np.ndarray:
    """
    Generate a random squared matrix with values between zero and 1 with the
    shape of (columns, columns)
    @param columns: amount of columns and rows (because it is squared)
    @return: random generated squared matrix
    """
    x = np.random.rand(columns, columns)
    return x


def deleteValues(x: np.ndarray, fraction: float) -> np.ndarray:
    """
    Takes a matrix and a fraction as input and returns a matrix
    where the fraction of elements are randomly set to Nan
    @param x: original matrix from which values are set to Nan
    @param fraction: percentage of all values of x is set  to NaN
    @return: perturbed matrix with NaNs
    """
    nan_x = copy.deepcopy(x)
    prop = int(fraction * x.size)
    mask = random.sample(range(x.size), prop)
    np.put(nan_x, mask, np.nan)
    return nan_x


def computeMeanVariance(error_list: list) -> tuple:
    """
    computes the mean and the variance for every single list in @error_list
    @param error_list: contains lists of errors for several fractions
    @return: tuple of mean and variance for every list
    """
    means = []
    variances = []
    for e_list in error_list:
        means.append(np.mean(e_list))
        variances.append(np.var(e_list))
    return means, variances


def deleteDataset(path, nyst=False):
    """
        Deletes the h5py dataset given by the path
        @param name: specifies dataset within file which is supposed to be deleted
        @param path: defines the path to the dataset which is supposed to be deleted
        @return:
        """
    with h5py.File(path, 'a') as f:
        # del f[name]
        if nyst:
            del f['C']
            del f['Cd']
        else:
            del f['Kxx']


def loadTargets(dataset):
    """
    Return labels for a given dataset
    @param dataset: containing data and its corresponding labels
    @return: labels
    """
    _, Y = next(iter(DataLoader(dataset, batch_size=len(dataset))))
    return Y