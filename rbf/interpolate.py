'''
This module provides a class for RBF interpolation, `RBFInterpolant`. This
function has numerous features that are lacking in `scipy.interpolate.rbf`.
They include:

* variable weights on the data (when creating a smoothed interpolant)
* more choices of basis functions (you can also easily make your own)
* analytical differentiation of the interpolant
* added polynomial terms for improved accuracy

RBF Interpolation
-----------------
Consider a vector of :math:`n` observations :math:`\mathbf{d}` made at
locations :math:`\mathbf{y}`. These observations could potentially have
normally distributed noise described by the covariance matrix :math:`\Sigma`.
An RBF interpolant :math:`\mathbf{f(x)}` for these observations is
parameterized as

.. math::
  \mathbf{f(x)} = \mathbf{K(x,y) a} + \mathbf{P(x) b}

where :math:`\mathbf{K(x,y)}` consists of the RBFs with centers at
:math:`\mathbf{y}` evaluated at the interpolation points :math:`\mathbf{x}`.
:math:`\mathbf{P(x)}` is a polynomial matrix containing :math:`m` monomial
basis function evaluated at the interpolation points. The monomial basis
functions span the space of all polynomials with a user specified order. The
coefficients :math:`\mathbf{a}` and :math:`\mathbf{b}` are chosen to minimize
the objective function

.. math::
  \mathcal{L}(\mathbf{a, b}) =
  \mathbf{a^T K(y,y) a} +
  \lambda \mathbf{(f(y; a, b) - d)^T \Sigma^{-1} (f(y; a, b) - d)}.

In the above expression, the second term on the right side is a norm measuring
the misfit between the interpolant and the observations. The first term on the
right side is a norm that essentially penalizes the roughness of the
interpolant (technically, it is the norm associated with the reproducing kernel
Hilbert space for the chosen radial basis function). We have also introduced
:math:`\lambda` which is a smoothing parameter that controls how well we want
the interpolant to fit the data. This problem formulation is a combination of
the formulations used in section 19.2 and 6.3 of [1].

To determine :math:`\mathbf{a}` and :math:`\mathbf{b}`, we need :math:`n+m`
linear constraints. We can recognize that :math:`\mathcal{L}` is a convex
function, and so it can be minimized by finding where its gradient is zero. We
differentiate :math:`\mathcal{L}` with respect to :math:`\mathbf{a}` and set it
equal to zero to get :math:`n` constraints


.. math::
  (\mathbf{K(y,y)} + \lambda^{-1}\mathbf{\Sigma}) \mathbf{a}
  + \mathbf{P(y) b} = \mathbf{d}.

For the remaining :math:`m` constraints, we differentiate
:math:`\mathcal{L}` with respect to :math:`\mathbf{b}`, set it equal to zero,
and substitute the above equation in for :math:`\mathbf{d}` to get

.. math::
  \mathbf{P(y)^T a} = \mathbf{0}.

For most purposes, the above two equations provide the linear constrains that
are needed to solve for :math:`\mathbf{a}` and :math:`\mathbf{b}`. However,
there are cases where the system cannot be solved due to, for example, too few
data points or a polynomial order that is too high. There are also some radial
basis functions which are conditionally positive definite, which means that the
norm :math:`\mathbf{a^T K(y, y) a}` is only guaranteed to be positive when the
order of the added polynomial is sufficiently high. The user is referred to [1]
for details on when the interpolation problem is well-posed. For the default
settings in `RBFInterpolant`, the interpolation problem is well-posed as long
as :math:`n \geq D+1`, where `D` is the number of spatial dimensions.

In our implementation, we have combined the effect of :math:`\Sigma` and
:math:`\lambda` into one variable, `sigma`, which is a scalar or a vector that
is *proportional* to the standard deviation of the noise. When `sigma` is `0`
the observations are fit perfectly by the interpolant. Increasing `sigma`
degrades the fit while improving the smoothness of the interpolant.

References
----------
[1] Fasshauer, G., Meshfree Approximation Methods with Matlab. World
Scientific Publishing Co, 2007.

'''
import numpy as np
import scipy.sparse
import scipy.spatial

from rbf.poly import powers, mvmonos
from rbf.basis import get_rbf, SparseRBF
from rbf.utils import assert_shape, KDTree
from rbf.linalg import PartitionedSolver


def _in_hull(p, hull):
  '''
  Tests if points in `p` are in the convex hull made up by `hull`
  '''
  dim = p.shape[1]
  # if there are not enough points in `hull` to form a simplex then
  # return False for each point in `p`.
  if hull.shape[0] <= dim:
    return np.zeros(p.shape[0], dtype=bool)

  if dim >= 2:
    hull = scipy.spatial.Delaunay(hull)
    return hull.find_simplex(p)>=0
  else:
    # one dimensional points
    min = np.min(hull)
    max = np.max(hull)
    return (p[:, 0] >= min) & (p[:, 0] <= max)


class RBFInterpolant(object):
  '''
  Regularized radial basis function interpolant

  Parameters
  ----------
  y : (N, D) array
    Observation points

  d : (N,) array
    Observed values at `y`

  sigma : float or (N,) array, optional
    Smoothing parameter. Setting this to 0 causes the interpolant to perfectly
    fit the data. Increasing the smoothing parameter degrades the fit while
    improving the smoothness of the interpolant. If this is a vector, it should
    be proportional to the one standard deviation uncertainties for the
    observations. This defaults to zeros.

  eps : float or float array, optional
    Shape parameter

  phi : rbf.basis.RBF instance or str, optional
    Radial basis function. This can be an `RBF` instance (e.g,
    `rbf.basis.phs3`) or a string for a predefined RBF (e.g., 'phs3'). See
    `rbf.basis` for all the available options.

  order : int, optional
    Order of the added polynomial terms. Set this to `-1` for no added
    polynomial terms.

  extrapolate : bool, optional
    Whether to allows points to be extrapolated outside of a convex hull formed
    by `y`. If False, then np.nan is returned for outside points.

  Notes
  -----
  This function does not make any estimates of the uncertainties on the
  interpolated values.  See `rbf.gauss` for interpolation with uncertainties.

  With certain choices of basis functions and polynomial orders this
  interpolant is equivalent to a thin-plate spline.  For example, if the
  observation space is one-dimensional then a thin-plate spline can be obtained
  with the arguments `phi` = `rbf.basis.phs3` and `order` = 1.  For
  two-dimensional observation space a thin-plate spline can be obtained with
  the arguments `phi` = `rbf.basis.phs2` and `order` = 1.

  References
  ----------
  [1] Fasshauer, G., Meshfree Approximation Methods with Matlab, World
  Scientific Publishing Co, 2007.

  '''
  def __init__(self, y, d,
               sigma=0.0,
               eps=1.0,
               phi='phs3',
               order=1,
               extrapolate=True):
    y = np.asarray(y, dtype=float)
    assert_shape(y, (None, None), 'y')

    d = np.asarray(d, dtype=float)
    assert_shape(d, (y.shape[0],), 'd')

    if np.isscalar(sigma):
      sigma = np.full((y.shape[0],), sigma, dtype=float)
    else:
      sigma = np.asarray(sigma, dtype=float)
      assert_shape(sigma, (y.shape[0],), 'sigma')

    phi = get_rbf(phi)
    # form block consisting of the RBF and uncertainties on the diagonal
    K = phi(y, y, eps=eps)
    K = K + scipy.sparse.diags(sigma**2)
    # form the block consisting of the monomials
    pwr = powers(order, y.shape[1])
    if pwr.shape[0] > y.shape[0]:
      raise ValueError(
        'The polynomial order is too high for the number of observations')

    P = mvmonos(y, pwr)
    # create zeros vector for the right-hand-side
    z = np.zeros((pwr.shape[0],))
    # solve for the RBF and mononomial coefficients
    phi_coeff, poly_coeff = PartitionedSolver(K, P).solve(d, z)

    self.y = y
    self.phi = phi
    self.order = order
    self.eps = eps
    self.phi_coeff = phi_coeff
    self.poly_coeff = poly_coeff
    self.pwr = pwr
    self.extrapolate = extrapolate

  def __call__(self, x, diff=None, chunk_size=1000):
    '''
    Evaluates the interpolant at `x`

    Parameters
    ----------
    x : (N, D) float array
      Target points

    diff : (D,) int array, optional
      Derivative order for each spatial dimension

    chunk_size : int, optional
      Break `x` into chunks with this size and evaluate the interpolant for
      each chunk

    Returns
    -------
    (N,) float array

    '''
    x = np.asarray(x,dtype=float)
    assert_shape(x, (None, self.y.shape[1]), 'x')

    if chunk_size is not None:
      out = np.zeros((x.shape[0],), dtype=float)
      for start in range(0, x.shape[0], chunk_size):
        stop = start + chunk_size
        out[start:stop] = self(x[start:stop], diff=diff, chunk_size=None)

      return out

    K = self.phi(x, self.y, eps=self.eps, diff=diff)
    P = mvmonos(x, self.pwr, diff=diff)
    out = K.dot(self.phi_coeff) + P.dot(self.poly_coeff)

    # return nan for points outside of the convex hull if extrapolation is not
    # allowed
    if not self.extrapolate:
      out[~_in_hull(x, self.y)] = np.nan

    return out


class NearestRBFInterpolant(object):
  '''
  Approximation to `RBFInterpolant` that only uses the k nearest observations
  for each interpolation point. This requires significantly less memory than
  `RBFInterpolant` when the number of observations is large.

  Parameters
  ----------
  y : (N, D) array
    Observation points

  d : (N,) array
    Observed values at `y`

  sigma : float or (N,) array, optional
    Smoothing parameter. Setting this to 0 causes the interpolant to perfectly
    fit the data. Increasing the smoothing parameter degrades the fit while
    improving the smoothness of the interpolant. If this is a vector, it should
    be proportional to the one standard deviation uncertainties for the
    observations. This defaults to zeros.

  k : int, optional
    Number of neighboring observations to use for each interpolation point

  eps : float or float array, optional
    Shape parameter

  phi : rbf.basis.RBF instance or str, optional
    Radial basis function. This can be an `RBF` instance (e.g,
    `rbf.basis.phs3`) or a string for a predefined RBF (e.g., 'phs3'). See
    `rbf.basis` for all the available options. `SparseRBF` instances are not
    supported.

  order : int, optional
    Order of the added polynomial terms. Set this to `-1` for no added
    polynomial terms.

  '''
  def __init__(self, y, d,
               sigma=0.0,
               k=20,
               eps=1.0,
               phi='phs3',
               order=1):
    y = np.asarray(y, dtype=float)
    assert_shape(y, (None, None), 'y')

    d = np.asarray(d, dtype=float)
    assert_shape(d, (y.shape[0],), 'd')

    if np.isscalar(sigma):
      sigma = np.full(y.shape[0], sigma, dtype=float)
    else:
      sigma = np.asarray(sigma, dtype=float)
      assert_shape(sigma, (y.shape[0],), 'sigma')

    phi = get_rbf(phi)
    if isinstance(phi, SparseRBF):
      raise ValueError('SparseRBF instances are not supported')

    tree = KDTree(y)

    self.y = y
    self.d = d
    self.sigma = sigma
    self.k = k
    self.eps = eps
    self.phi = phi
    self.order = order
    self.tree = tree

  def __call__(self, x, diff=None, chunk_size=100):
    '''
    Evaluates the interpolant at `x`

    Parameters
    ----------
    x : (N, D) float array
      Target points

    diff : (D,) int array, optional
      Derivative order for each spatial dimension

    chunk_size : int, optional
      Break `x` into chunks with this size and evaluate the interpolant for
      each chunk

    Returns
    -------
    (N,) float array

    '''
    x = np.asarray(x, dtype=float)
    assert_shape(x, (None, self.y.shape[1]), 'x')

    if chunk_size is not None:
      out = np.zeros((x.shape[0],), dtype=float)
      for start in range(0, x.shape[0], chunk_size):
        stop = start + chunk_size
        out[start:stop] = self(x[start:stop], diff=diff, chunk_size=None)

      return out

    pwr = powers(self.order, self.y.shape[1])
    if pwr.shape[0] > self.k:
      raise ValueError(
        'The polynomial order is too high for the number of nearest neighbors')

    # get the indices of the k nearest observations for each interpolation
    # point
    _, nbr = self.tree.query(x, self.k)

    # build the left-hand-side interpolation matrix consisting of the RBF
    # and polyomials evaluated at each neighborhood
    K = self.phi(self.y[nbr], self.y[nbr], eps=self.eps)
    # add the smoothing term to the diagonals of K
    K[:, range(self.k), range(self.k)] += self.sigma[nbr]**2
    P = mvmonos(self.y[nbr], pwr)
    Pt = np.einsum('ijk->ikj', P)
    Z = np.zeros((x.shape[0], pwr.shape[0], pwr.shape[0]), dtype=float)
    LHS = np.concatenate(
      (np.concatenate((K, P), axis=2),
       np.concatenate((Pt, Z), axis=2)),
      axis=1)

    # build the right-hand-side data vector consisting of the observations for
    # each neighborhood and extra zeros
    z = np.zeros((x.shape[0], pwr.shape[0]), dtype=float)
    rhs = np.concatenate((self.d[nbr], z), axis=1)

    # solve for the RBF and polynomial coefficients
    coeff = np.linalg.solve(LHS, rhs)
    phi_coeff = coeff[:, :self.k]
    poly_coeff = coeff[:, self.k:]

    # evaluate the interpolant at the interpolation points
    K = self.phi(x[:, None], self.y[nbr], eps=self.eps, diff=diff)[:, 0]
    P = mvmonos(x, pwr, diff=diff)
    out = (K*phi_coeff).sum(axis=1) + (P*poly_coeff).sum(axis=1)
    return out
