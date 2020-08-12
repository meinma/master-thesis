"""
Given a pre-computed kernel and a data set, compute train/validation/test accuracy.
"""
import importlib
from timeit import default_timer as timer

import absl.app
import h5py
import numpy as np
import torch

from cnn_gp import DatasetFromConfig
from matrix_factorization.experiments import deleteValues, computeRMSE
from matrix_factorization.factorization import softImpute, iterativeSVD, matrix_completion
from matrix_factorization.nystroem import Nystroem
from utils.utils import print_accuracy, solve_system, constructSymmetricIfNotSymmetric, load_kern, diag_add

FLAGS = absl.app.flags.FLAGS


def main(_):
    config = importlib.import_module(f"configs.{FLAGS.config}")
    dataset = DatasetFromConfig(FLAGS.datasets_path, config)
    computation = FLAGS.computation

    print("Reading training labels")
    _, Y = dataset.load_full(dataset.train)
    n_classes = Y.max() + 1
    Y_1hot = torch.ones((len(Y), n_classes), dtype=torch.float64).neg_()  # all -1
    Y_1hot[torch.arange(len(Y)), Y] = 1.

    with h5py.File(FLAGS.in_path, "r") as f:
        print("Loading kernel")
        Kxx = load_kern(f["Kxx"], 0)
        diag_add(Kxx, FLAGS.jitter)

        if computation < 1.0:
            # Use Nystroem Approximation
            print('Nystroem')
            Kxx_symm = constructSymmetricIfNotSymmetric(Kxx.numpy())
            start = timer()
            nystroem = Nystroem(n_components=int(0.7 * Kxx.shape[0]), k=int(0.1 * Kxx.shape[0]), dataset=dataset.train,
                                model=config.initial_model.cuda(), batch_size=200, out_path='nystroem.h5')
            output = nystroem.fit_transform()
            end = timer()
            diff = (end - start) // 60  # time in minutes
            print(f'Nystroem took {diff} minutes')
            print(output.shape)
            print(f'error nystrom and original matrix: {computeRMSE(Kxx_symm, output)}]')
            A = solve_system(Kxx_symm, Y_1hot)
            A_nyst = solve_system(output, Y_1hot)
            _, Yv = dataset.load_full(dataset.validation)
            Kxvx = load_kern(f["Kxvx"], 0)
            print_accuracy(A, Kxvx, Yv, "validation_original")
            print_accuracy(A_nyst, Kxvx, Yv, "validation_nyst")

        elif computation > 1.0:
            Kxx_symm = constructSymmetricIfNotSymmetric(Kxx.numpy())
            print(Kxx_symm)
            nans = np.sum(np.isnan(Kxx_symm))
            print(f"nans in symmetric original matrix: {nans}")
            Kxx_perturbated = deleteValues(Kxx_symm, 0.5)
            start = timer()
            Kxx_svd = iterativeSVD(Kxx_perturbated)
            end = timer()
            diff = end - start
            print(f"svd time: {diff}")
            nans_svd = np.sum(np.isnan(Kxx_svd))
            print(f"nans in svd reconstruction: {nans_svd}")
            start = timer()
            Kxx_soft = softImpute(Kxx_perturbated)
            end = timer()
            diff = end - start
            soft_nans = np.sum(np.isnan(Kxx_soft))
            print(f"number of nans after osftimpute reconstruction: {soft_nans}")
            print(f"Soft time: {diff}")
            start = timer()
            Kxx_mf = matrix_completion(Kxx_perturbated)
            end = timer()
            diff = end - start
            print(f"Matrix factorization: {diff}")
            print("Kxx_svd is symmetric after applying iterative svd: " + str(isSymmetric(Kxx_svd)))
            print("Kxx_soft is symmetric after applying softImpute: " + str(isSymmetric(Kxx_soft)))
            print("Kxx_mf is symmetric after applying MatrixFactorization: " + str(isSymmetric(Kxx_mf)))
            svd_error = computeRMSE(Kxx_symm.numpy(), Kxx_svd)
            soft_error = computeRMSE(Kxx_symm.numpy(), Kxx_soft)
            mf_error = computeRMSE(Kxx_symm.numpy(), Kxx_mf)
            print("Errors of the different methods:")
            print(f"Iterative svd error: {svd_error}")
            print(f"SoftImpute error: {soft_error}")
            print(f"Matrix Factorization error: {mf_error}")

            print("Classification:")
            A_original = solve_system(Kxx_symm, Y_1hot)
            A_svd = solve_system(Kxx_svd, Y_1hot)
            A_soft = solve_system(Kxx_soft, Y_1hot)
            A_mf = solve_system(Kxx_mf, Y_1hot)

            _, Yv = dataset.load_full(dataset.validation)
            Kxvx = load_kern(f["Kxvx"], 0)

            print('Validation:')
            print_accuracy(A_original, Kxvx, Yv, "validation_orig")
            print_accuracy(A_svd, Kxvx, Yv, "validation_svd")
            print_accuracy(A_soft, Kxvx, Yv, "validation_soft")
            print_accuracy(A_mf, Kxvx, Yv, "validation_mf")

            print('Testing:')
            _, Yt = dataset.load_full(dataset.test)
            Kxtx = load_kern(f["Kxtx"], 0)

            print_accuracy(A_original, Kxtx, Yt, "test_orig")
            print_accuracy(A_svd, Kxtx, Yt, "test_svd")
            print_accuracy(A_soft, Kxtx, Yt, "test_soft")
            print_accuracy(A_mf, Kxtx, Yt, "test_mf")

            del Kxx
            del Kxx_symm
            # del Kxx_mf
            del Kxx_soft
            del Kxx_perturbated
            del Kxx_svd

        else:
            Kxx_symm = constructSymmetricIfNotSymmetric(Kxx.numpy())
            # plotEigenvalues(Kxx_symm)
            #
            # max_val = torch.max(torch.tensor(Kxx_symm)).item()
            # print(f"Maximum value of Kxx: {max_val}")

            print("Solving Kxx^{-1} Y")
            A = solve_system(Kxx_symm, Y_1hot)

            _, Yv = dataset.load_full(dataset.validation)
            Kxvx = load_kern(f["Kxvx"], 0)

            print_accuracy(A, Kxvx, Yv, "validation")
            del Kxvx
            del Yv

            _, Yt = dataset.load_full(dataset.test)
            Kxtx = load_kern(f["Kxtx"], 0)
            print_accuracy(A, Kxtx, Yt, "test")
            del Kxtx
            del Yt

            del Kxx


# @(py36) ag919@ulam:~/Programacio/cnn-gp-pytorch$ python classify_gp.py --in_path=/scratch/ag919/grams_pytorch/mnist_as_tf/00_nwork07.h5 --config=mnist_as_tf
# magma.py has some problem loading. Proceeding anyways using CPU.
# Original error: ignoring magma shit
# Reading training labels
# Loading kernel
# Solving Kxx^{-1} Y
# Running scipy solve Kxx^-1 Y routine
# train accuracy: 10.26%
# validation accuracy: 99.31%
# test accuracy: 99.11999999999999%


if __name__ == '__main__':
    f = absl.app.flags
    f.DEFINE_string("datasets_path", "/scratch/ag919/datasets/",
                    "where to save datasets")
    f.DEFINE_string("config", "mnist", "which config to load from `configs`")
    f.DEFINE_string('in_path', "/scratch/ag919/grams_pytorch/mnist/dest.h5",
                    "path of h5 file to load kernels from")
    f.DEFINE_float("jitter", 0.0, "add to the diagonal")
    f.DEFINE_float("computation", 1.0, "fraction of kxx which is computed exactly")
    absl.app.run(main)
