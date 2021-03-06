import os
from timeit import default_timer as timer

import fire
import h5py
import numpy as np
import torch
from torch.utils.data import Subset

from cnn_gp import save_K
from plotting.createStartPlot import loadDataset
from utils import load_kern, constructSymmetricMatrix, deleteValues, loadNormalizedModel


def computeKxxPert(inpath, outpath, fraction):
    """
    Takes a given matrix and sets randomly a fraction of all matrix values to nan.
    @param inpath: Matrix given in h5 file where values are set to nan
    @param outpath: Permuted matrix is stored in that h5 file
    @param fraction: determines how many values are set to nan from the overall matrix elements
    @return:
    """
    frac = float(fraction)
    with h5py.File(inpath, 'r') as f:
        Kxx_symm = np.array(f.get('Kxx'))
        f.close()
    Kxx_pert = deleteValues(Kxx_symm, frac)
    with h5py.File(outpath, 'w') as f:
        f.create_dataset('Kxx_pert', shape=(Kxx_symm.shape[0], Kxx_symm.shape[1]), data=Kxx_pert)
        f.close()


def computeValidationAndTestKernel(path):
    """
    Computes and stores the matrices Kxtx and Kxvx for computing the predictions the test and validation predictions
    @param path: File where the matrices are stored (Data set names are Kxvx and Kxtx)
    @return:
    """
    model = loadNormalizedModel()
    train = loadDataset()
    val = loadDataset(mode='val')
    test = loadDataset(mode='test')
    kwargs = dict(worker_rank=0, n_workers=1,
                  batch_size=200, print_interval=2.)

    def kern(x, x2, **args):
        with torch.no_grad():
            return model(x.cuda(), x2.cuda(), **args).detach().cpu().numpy()

    with h5py.File(path, 'w') as f:
        save_K(f, kern, 'Kxvx', val, train, diag=False, **kwargs)
        save_K(f, kern, 'Kxtx', test, train, diag=False, **kwargs)
        f.close()


def computeValidationKernel(path, name, mode='val'):
    """
    Computes the validation matrix and stores it in a file with a given name
    @param path: specifies file to store Kxvx matrix
    @param name: dataset name within the file
    @return:
    """
    model = loadNormalizedModel()
    train = loadDataset(mode='train')
    val = loadDataset(mode=mode)
    kwargs = dict(worker_rank=0, n_workers=1,
                  batch_size=200, print_interval=2.)

    def kern(x, x2, **args):
        with torch.no_grad():
            return model(x.cuda(), x2.cuda(), **args).detach().cpu().numpy()

    with h5py.File(path, 'w') as f:
        save_K(f, kern, name, val, train, diag=False, **kwargs)


def computeKxxMatrix(path, name, fraction=1.0):
    """
    Stores the kernel matrix Kxx between the training points
    @param fraction: determines which fraction of the dataset is used
    @param path: file path containing the kernel matrix
    @param name: name of the dataset of the kernel matrix
    @return:
    """
    fraction = float(fraction)
    model = loadNormalizedModel()
    dataset = loadDataset()
    kwargs = dict(worker_rank=0, n_workers=1,
                  batch_size=200, print_interval=2.)

    def kern(x, x2, **args):
        with torch.no_grad():
            return model(x.cuda(), x2.cuda(), **args).detach().cpu().numpy()

    if fraction == 1.0:
        with h5py.File(path, "w") as f:
            save_K(f, kern, name, X=dataset, X2=None, diag=False, **kwargs)
            f.close()
    else:
        new_length = int(fraction * len(dataset))
        subset = Subset(dataset, range(new_length))
        start = timer()
        with h5py.File(path, "w") as f:
            save_K(f, kern, name, X=subset, X2=None, diag=False, **kwargs)
            f.close()
        end = timer()
        diff = (end - start) / 60
        os.system(f"python -m plotting.computeKernel loadMatrixFromDiskAndMirror {path} {name}")
        # Create subMatrix
        with h5py.File(path, 'a') as f:
            time = np.array(f.get('time'))
            diff = diff + time
            del f['time']
            sub_Matrix = np.array(f.get(name))
            newMatrix = np.empty((len(dataset), len(dataset)))
            newMatrix.fill(np.nan)
            newMatrix[:new_length, :new_length] = sub_Matrix[:, :]
            del f[name]
            f.close()
        with h5py.File(path, 'w') as f:
            f.create_dataset(name, shape=(len(dataset), len(dataset)), data=newMatrix)
            f.create_dataset(name='time', data=np.array(diff))
            f.close()


def computeNystroem(path, components):
    model = loadNormalizedModel()
    dataset = loadDataset()
    subset = Subset(dataset, range(components))

    def kern(x, x2, **args):
        with torch.no_grad():
            return model(x.cuda(), x2.cuda(), **args).detach().cpu().numpy()

    dataset_low = Subset(dataset, range(len(subset), len(dataset)))

    with h5py.File(path, 'w') as f:
        kwargs = dict(worker_rank=0, n_workers=1,
                      batch_size=200, print_interval=2.)
        # Compute squared part first
        save_K(f, kern, 'W', X=subset, X2=None, diag=False, **kwargs)
        # Lower part
        save_K(f, kern, "C_down", X=dataset_low, X2=subset, diag=False, **kwargs)


def loadMatrixFromDiskAndMirror(path, name):
    """
    Loads a matrix from a file and mirrors it if desired before returning
    @param path: File path containing the matrix
    @param name: Name of the dataset in the file
    """
    with h5py.File(path, "a") as f:
        matrix = load_kern(f[name], 0)
        start = timer()
        sym_Matrix = constructSymmetricMatrix(matrix)
        stop = timer()
        diff = (stop - start) / 60
        del f[name]
    with h5py.File(path, 'w') as f:
        f.create_dataset(name=name, shape=(matrix.shape[0], matrix.shape[1]), data=sym_Matrix)
        f.create_dataset(name='time', data=np.array(diff))


if __name__ == "__main__":
    fire.Fire()
