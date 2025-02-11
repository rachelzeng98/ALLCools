"""
The function art_of_tsne is from cytograph2 package
https://github.com/linnarsson-lab/cytograph2/blob/master/cytograph/embedding/art_of_tsne.py

The idea behind that is based on :cite:p:`Kobak2019` with T-SNE algorithm implemented in
[openTSNE](https://opentsne.readthedocs.io/en/latest/) :cite:p:`Policar2019`.

"""

import logging
from typing import Callable, Union

import numpy as np
from openTSNE import TSNEEmbedding, affinity, initialization


def art_of_tsne(
        X: np.ndarray,
        metric: Union[str, Callable] = "euclidean",
        exaggeration: float = -1,
        perplexity: int = 30,
        n_jobs: int = -1,
) -> TSNEEmbedding:
    """
    Implementation of Dmitry Kobak and Philipp Berens
    "The art of using t-SNE for single-cell transcriptomics" based on openTSNE.
    See https://doi.org/10.1038/s41467-019-13056-x | www.nature.com/naturecommunications

    Parameters
    ----------
    X
        The data matrix of shape (n_cells, n_genes) i.e. (n_samples, n_features)
    metric
        Any metric allowed by PyNNDescent (default: 'euclidean')
    exaggeration
        The exaggeration to use for the embedding
    perplexity
        The perplexity to use for the embedding
    n_jobs
        Number of CPUs to use

    Returns
    -------
    The embedding as an opentsne.TSNEEmbedding object (which can be cast to an np.ndarray)
    """
    n = X.shape[0]
    if n > 100_000:
        if exaggeration == -1:
            exaggeration = 1 + n / 333_333
        # Subsample, optimize, then add the remaining cells and optimize again
        # Also, use exaggeration == 4
        logging.info(f"Creating subset of {n // 40} elements")
        # Subsample and run a regular art_of_tsne on the subset
        indices = np.random.permutation(n)
        reverse = np.argsort(indices)
        X_sample, X_rest = X[indices[: n // 40]], X[indices[n // 40:]]
        logging.info(f"Embedding subset")
        Z_sample = art_of_tsne(X_sample, metric=metric)

        logging.info(
            f"Preparing partial initial embedding of the {n - n // 40} remaining elements"
        )
        if isinstance(Z_sample.affinities, affinity.Multiscale):
            rest_init = Z_sample.prepare_partial(
                X_rest, k=1, perplexities=[1 / 3, 1 / 3]
            )
        else:
            rest_init = Z_sample.prepare_partial(X_rest, k=1, perplexity=1 / 3)
        logging.info(f"Combining the initial embeddings, and standardizing")
        init_full = np.vstack((Z_sample, rest_init))[reverse]
        init_full = init_full / (np.std(init_full[:, 0]) * 10000)

        logging.info(f"Creating multiscale affinities")
        affinities = affinity.PerplexityBasedNN(
            X, perplexity=perplexity, metric=metric, method="approx", n_jobs=n_jobs
        )
        logging.info(f"Creating TSNE embedding")
        Z = TSNEEmbedding(
            init_full, affinities, negative_gradient_method="fft", n_jobs=n_jobs
        )
        logging.info(f"Optimizing, stage 1")
        Z.optimize(
            n_iter=250,
            inplace=True,
            exaggeration=12,
            momentum=0.5,
            learning_rate=n / 12,
            n_jobs=n_jobs,
        )
        logging.info(f"Optimizing, stage 2")
        Z.optimize(
            n_iter=750,
            inplace=True,
            exaggeration=exaggeration,
            momentum=0.8,
            learning_rate=n / 12,
            n_jobs=n_jobs,
        )
    elif n > 3_000:
        if exaggeration == -1:
            exaggeration = 1
        # Use multiscale perplexity
        affinities_multiscale_mixture = affinity.Multiscale(
            X,
            perplexities=[perplexity, n / 100],
            metric=metric,
            method="approx",
            n_jobs=n_jobs,
        )
        init = initialization.pca(X)
        Z = TSNEEmbedding(
            init,
            affinities_multiscale_mixture,
            negative_gradient_method="fft",
            n_jobs=n_jobs,
        )
        Z.optimize(
            n_iter=250,
            inplace=True,
            exaggeration=12,
            momentum=0.5,
            learning_rate=n / 12,
            n_jobs=n_jobs,
        )
        Z.optimize(
            n_iter=750,
            inplace=True,
            exaggeration=exaggeration,
            momentum=0.8,
            learning_rate=n / 12,
            n_jobs=n_jobs,
        )
    else:
        if exaggeration == -1:
            exaggeration = 1
        # Just a plain TSNE with high learning rate
        lr = max(200, n / 12)
        aff = affinity.PerplexityBasedNN(
            X, perplexity=perplexity, metric=metric, method="approx", n_jobs=n_jobs
        )
        init = initialization.pca(X)
        Z = TSNEEmbedding(
            init, aff, learning_rate=lr, n_jobs=n_jobs, negative_gradient_method="fft"
        )
        Z.optimize(250, exaggeration=12, momentum=0.5, inplace=True, n_jobs=n_jobs)
        Z.optimize(
            750, exaggeration=exaggeration, momentum=0.8, inplace=True, n_jobs=n_jobs
        )
    return Z


def tsne(
        adata,
        obsm="X_pca",
        metric: Union[str, Callable] = "euclidean",
        exaggeration: float = -1,
        perplexity: int = 30,
        n_jobs: int = -1,
):
    """
    Calculating T-SNE embedding with the openTSNE package :cite:p:`Policar2019` and
    parameter optimization strategy described in :cite:p:`Kobak2019`.

    Parameters
    ----------
    adata
        adata object with principle components or equivalent matrix stored in .obsm
    obsm
        name of the matrix in .obsm that can be used as T-SNE input
    metric
        Any metric allowed by PyNNDescent (default: 'euclidean')
    exaggeration
        The exaggeration to use for the embedding
    perplexity
        The perplexity to use for the embedding
    n_jobs
        Number of CPUs to use

    Returns
    -------
    T-SNE embedding will be stored at adata.obsm["X_tsne"]
    """
    X = adata.obsm[obsm]
    Z = art_of_tsne(
        X=X,
        metric=metric,
        exaggeration=exaggeration,
        perplexity=perplexity,
        n_jobs=n_jobs,
    )
    adata.obsm["X_tsne"] = np.array(Z)
    return
