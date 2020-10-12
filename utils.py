import tensorflow as tf
import math


@tf.function
def f_basis(n, dtype=tf.complex128):
    """The function returns basis in the space of real traceless matrices
    of size n. For all matrices, the following condition holds true
    <F_i, F_j> = I_ij, where I is the identity matrix.
    Args:
        n: int value, dimension of a space
        dtype: type of matrices
    Returns:
        tensor of shape (n**2-1, n, n), 0th index enumerates matrices"""

    F = tf.eye(n ** 2, dtype=dtype)
    F = tf.reshape(F, (n ** 2, n, n))[:-1]
    F = tf.reshape(F, (n-1, n+1, n, n))[:, 1:]
    F00 = tf.ones((n, 1), dtype=dtype) / math.sqrt(n)
    diag = tf.concat([F00, tf.eye(n, n-1, dtype=dtype)], axis=1)
    q, _ = tf.linalg.qr(diag)
    diag = tf.linalg.diag(tf.transpose(q))[1:]
    diag = diag[:, tf.newaxis]
    F = tf.concat([diag, F], axis=1)
    F = tf.reshape(F, (-1, n, n))
    return F


@tf.function
def hankel(T, K):
    """Return Hankel tensor from an ordinary tensor.
    Args:
        T: tensor of shape (batch_size, n, m)
        K: int value, depth of the Hankel matrix
    Returns:
        tensor of shape (batch_size, n-K+1, K, m)"""

    L = T.shape[1]
    i = tf.constant(1)
    t = T[:, tf.newaxis, :K]
    cond = lambda i, t: i<=L-K
    body = lambda i, t: [i+1, tf.concat([t, T[:, tf.newaxis, i:K+i]], axis=1)]
    _, t = tf.while_loop(cond, body, loop_vars=[i, t],
                  shape_invariants=[i.shape, tf.TensorShape([T.shape[0], None, K, T.shape[-1]])])
    return t


@tf.function
def dmd(trajectories, K, eps=1e-5):
    """Solves the following linear regression problem
    ||TX - Y||_F --> min with respect to transition matrix T.
    Matrix T is found by using dynamic mode decomposition (dmd) in the form
    of its eigendecomposition with the minimal possible rank.
    You may read more about dmd in the following paper
    https://arxiv.org/pdf/1312.0041.pdf
    Args:
        trajectories: complex valued tensor of shape (bs, n, m, m),
            quantum trajectories, bs enumerates trajectories, n is total
            number of time steps, m is dimension of density matrix
        K: int number, memory depth
        eps: float value, tolerance that defines rank
    Returns:
        three tensors of shapes (r,), (n, r), and (n, r),
        dominant eigenvalues and corresponding (right and left)
        eigenvectors
    Note:
        n -- dimension of one data point, r -- rank that is determined
        by tolerance eps."""

    # bs is batch size
    # n is number of time steps
    # m is the size of density matrix
    bs, n, m, _ = trajectories.shape
    dtype = trajectories.dtype
    # reshape density matrices to vectors
    t = tf.reshape(trajectories, (bs, n, m**2))
    # build hankel matrix of shape (bs, n-K+1, K, m**2)
    t = hankel(t, K)
    # build X and Y tensors, both have shape (K*(m**2), bs, n-K)
    t = tf.reshape(t, (bs, n-K+1, K*(m**2)))
    t = tf.transpose(t, (2, 0, 1))
    X = t[..., :-1]
    Y = t[..., 1:]
    # reshape X and Y tensors to matrices
    X_resh = tf.reshape(X, (K*(m**2), bs*(n-K)))
    Y_resh = tf.reshape(Y, (K*(m**2), bs*(n-K)))
    # SVD of X_resh matrix
    lmbd, u, v = tf.linalg.svd(X_resh)
    # number of singular vals > eps
    ind = tf.reduce_sum(tf.cast(lmbd > eps, dtype=tf.int32))
    # truncation of all elements of the svd
    lmbd = lmbd[:ind]
    lmbd_inv = 1 / lmbd
    lmbd_inv = tf.cast(lmbd_inv, dtype=dtype)
    u = u[:, :ind]
    v = v[:, :ind]
    # eigendecomposition of T_tilda
    T_tilda = tf.linalg.adjoint(u) @ Y_resh @ (v * lmbd_inv)
    eig_vals, right = tf.linalg.eig(T_tilda)
    left = tf.linalg.adjoint(tf.linalg.inv(right))
    # eigendecomposition of T
    right = Y_resh @ (v * lmbd_inv) @ right
    left = u @ left
    norm = tf.linalg.adjoint(left) * tf.linalg.matrix_transpose(right)
    norm = tf.reduce_sum(norm, axis=-1)
    norm = tf.math.sqrt(norm)
    right = right / norm
    left = left / tf.math.conj(norm)
    return eig_vals, right, left


@tf.function
def solve_regression(X, Y):
    """Solves the following linear regression problem
    ||TX - Y||_F --> min with respect to transition matrix T.
    T = Y @ pinv(X)
    Args:
        X: tensor of shape(n, ...)
        Y: tensor of shape(n, ...)
    Returns:
        tensor of shape (n, n), transition matrix
    Note:
        n -- dimension of one data point"""

    dtype = X.dtype
    X_resh = tf.reshape(X, (X.shape[0], -1))
    Y_resh = tf.reshape(Y, (Y.shape[0], -1))
    s, u, v = tf.linalg.svd(X_resh)
    ind = tf.cast(s > 1e-8, dtype=tf.int32)
    ind = tf.reduce_sum(ind)
    s_inv = tf.concat([1 / s[:ind], s[ind:]], axis=0)
    s_inv = tf.cast(s_inv, dtype=dtype)
    X_pinv = (v * s_inv) @ tf.linalg.adjoint(u)
    return Y_resh @ X_pinv


@tf.function
def pinv(X, eps=1e-5):
    """Returns pinv of a given matrix.
    Args:
        X: tensor of shape (..., a, b)
        eps: float value, tolerance
    Returns:
        tensor of shape (..., a, b)"""

    s, u, v = tf.linalg.svd(X)
    ind = tf.reduce_sum(tf.cast(s > eps, dtype=tf.int32))
    u = u[:, :ind]
    v = v[:, :ind]
    s = s[:ind]
    s_inv = 1 / s
    s_inv = tf.cast(s_inv, dtype=u.dtype)
    return (v * s_inv) @ tf.linalg.adjoint(u)
