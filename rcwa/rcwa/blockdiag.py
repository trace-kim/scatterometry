"""
2x2 blocks of diagonal matrices: the structure of every RCWA matrix in a homogeneous region.

In a uniform layer (and in the gap and external regions) the harmonics decouple, so each
2Nh x 2Nh matrix [[A, B], [C, D]] in the [x-block; y-block] stacking has diagonal A, B, C, D.
`DiagBlocks` stores them as an (Nh, 2, 2) array, one 2x2 matrix per harmonic, which makes
products, inverses and Redheffer star products O(Nh) instead of O(Nh^3).

Products with dense arrays return dense arrays, so a DiagBlocks can stand in for a dense
matrix wherever it is multiplied or solved against.
"""
from __future__ import annotations

from .backend import get_array_module


class DiagBlocks:
    """A 2Nh x 2Nh matrix whose four Nh x Nh blocks are diagonal."""

    __array_ufunc__ = None  # make ndarray @ DiagBlocks defer to __rmatmul__
    __array_priority__ = 1000  # the same for CuPy

    def __init__(self, blocks):
        self.blocks = blocks  # (Nh, 2, 2): blocks[h] = [[A_hh, B_hh], [C_hh, D_hh]]

    # ---- construction ----------------------------------------------------------------

    @classmethod
    def from_diagonals(cls, a, b, c, d) -> "DiagBlocks":
        xp = get_array_module()
        a, b, c, d = (xp.asarray(v, dtype=xp.complex128) for v in xp.broadcast_arrays(a, b, c, d))
        return cls(xp.stack([xp.stack([a, b], axis=-1), xp.stack([c, d], axis=-1)], axis=-2))

    @classmethod
    def identity(cls, Nh: int) -> "DiagBlocks":
        xp = get_array_module()
        return cls(xp.broadcast_to(xp.eye(2, dtype=xp.complex128), (Nh, 2, 2)).copy())

    @classmethod
    def diagonal(cls, values) -> "DiagBlocks":
        """diag(values) for a length-2Nh vector."""
        Nh = values.shape[0] // 2
        return cls.from_diagonals(values[:Nh], 0.0, 0.0, values[Nh:])

    # ---- properties ------------------------------------------------------------------

    @property
    def Nh(self) -> int:
        return self.blocks.shape[0]

    @property
    def shape(self):
        return (2 * self.Nh, 2 * self.Nh)

    def to_dense(self):
        xp = get_array_module()
        b = self.blocks
        return xp.block([[xp.diag(b[:, i, j]) for j in range(2)] for i in range(2)])

    def copy(self) -> "DiagBlocks":
        return DiagBlocks(self.blocks.copy())

    def inv(self) -> "DiagBlocks":
        xp = get_array_module()
        return DiagBlocks(xp.linalg.inv(self.blocks))

    def solve(self, rhs):
        """self^-1 @ rhs for a DiagBlocks or a dense vector/matrix."""
        return self.inv() @ rhs

    # ---- arithmetic ------------------------------------------------------------------

    def __matmul__(self, other):
        xp = get_array_module()
        if isinstance(other, DiagBlocks):
            return DiagBlocks(xp.matmul(self.blocks, other.blocks))
        other = xp.asarray(other)
        Nh, b = self.Nh, self.blocks
        top, bottom = other[:Nh], other[Nh:]
        shape = (Nh,) + (1,) * (other.ndim - 1)
        a, bb, c, d = (b[:, i, j].reshape(shape) for i, j in ((0, 0), (0, 1), (1, 0), (1, 1)))
        return xp.concatenate([a * top + bb * bottom, c * top + d * bottom], axis=0)

    def __rmatmul__(self, other):
        xp = get_array_module()
        other = xp.asarray(other)
        Nh, b = self.Nh, self.blocks
        left, right = other[..., :Nh], other[..., Nh:]
        return xp.concatenate([left * b[:, 0, 0] + right * b[:, 1, 0],
                               left * b[:, 0, 1] + right * b[:, 1, 1]], axis=-1)

    def __add__(self, other: "DiagBlocks") -> "DiagBlocks":
        return DiagBlocks(self.blocks + other.blocks)

    def __sub__(self, other: "DiagBlocks") -> "DiagBlocks":
        return DiagBlocks(self.blocks - other.blocks)

    def __neg__(self) -> "DiagBlocks":
        return DiagBlocks(-self.blocks)

    def __mul__(self, scalar) -> "DiagBlocks":
        return DiagBlocks(self.blocks * scalar)

    __rmul__ = __mul__


def dense(matrix):
    """`matrix` as a dense array."""
    return matrix.to_dense() if isinstance(matrix, DiagBlocks) else matrix


def identity_like(*matrices):
    """Identity matching `matrices`: DiagBlocks if all of them are, else dense."""
    xp = get_array_module()
    if all(isinstance(m, DiagBlocks) for m in matrices):
        return DiagBlocks.identity(matrices[0].Nh)
    return xp.eye(matrices[0].shape[0], dtype=xp.complex128)


def eye_minus(matrix):
    """I - matrix, keeping the DiagBlocks structure when there is one."""
    xp = get_array_module()
    if isinstance(matrix, DiagBlocks):
        return DiagBlocks.identity(matrix.Nh) - matrix
    return xp.eye(matrix.shape[0], dtype=xp.complex128) - matrix


def homogeneous_q(Kx, Ky, eps_r: complex, mu_r: complex) -> DiagBlocks:
    """Q of a homogeneous medium: (1/mu) [[Kx Ky, mu eps - Kx^2], [Ky^2 - mu eps, -Ky Kx]]."""
    me = mu_r * eps_r
    return DiagBlocks.from_diagonals(Kx * Ky, me - Kx**2, Ky**2 - me, -Ky * Kx) * (1.0 / mu_r)


def homogeneous_modes(Kx, Ky, eps_r: complex, mu_r: complex, kz):
    """(W, V, lam) of a homogeneous medium with longitudinal wavenumbers kz (length Nh).

    W = I, lam = j kz for both polarizations, V = Q lam^-1.
    """
    xp = get_array_module()
    lam = xp.concatenate([1j * kz, 1j * kz])
    Q = homogeneous_q(Kx, Ky, eps_r, mu_r)
    V = Q @ DiagBlocks.diagonal(1.0 / lam)
    return DiagBlocks.identity(Kx.size), V, lam
