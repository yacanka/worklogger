"""Small pure-Python Ed25519 helpers for signing and verification."""

from __future__ import annotations

from hashlib import sha512

FIELD_MODULUS = 2**255 - 19
GROUP_ORDER = 2**252 + 27742317777372353535851937790883648493
CURVE_D = (-121665 * pow(121666, FIELD_MODULUS - 2, FIELD_MODULUS)) % FIELD_MODULUS
SQRT_M1 = pow(2, (FIELD_MODULUS - 1) // 4, FIELD_MODULUS)
BASE_Y = (4 * pow(5, FIELD_MODULUS - 2, FIELD_MODULUS)) % FIELD_MODULUS


def public_key_from_seed(seed: bytes) -> bytes:
    """Derive a 32-byte Ed25519 public key from a 32-byte seed."""
    scalar = _secret_scalar(seed)
    return _encode_point(_scalar_mult(_base_point(), scalar))


def sign(seed: bytes, message: bytes) -> bytes:
    """Sign a message with a 32-byte Ed25519 seed."""
    digest = sha512(seed).digest()
    scalar = _clamp_scalar(digest[:32])
    prefix = digest[32:]
    public_key = _encode_point(_scalar_mult(_base_point(), scalar))
    nonce = _hint(prefix + message)
    point_r = _scalar_mult(_base_point(), nonce)
    encoded_r = _encode_point(point_r)
    challenge = _hint(encoded_r + public_key + message)
    scalar_s = (nonce + challenge * scalar) % GROUP_ORDER
    return encoded_r + scalar_s.to_bytes(32, "little")


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Verify a detached Ed25519 signature."""
    if len(public_key) != 32 or len(signature) != 64:
        return False
    try:
        point_a = _decode_point(public_key)
        point_r = _decode_point(signature[:32])
    except ValueError:
        return False
    scalar_s = int.from_bytes(signature[32:], "little")
    if scalar_s >= GROUP_ORDER:
        return False
    challenge = _hint(signature[:32] + public_key + message)
    left = _scalar_mult(_base_point(), scalar_s)
    right = _edwards_add(point_r, _scalar_mult(point_a, challenge))
    return left == right


def _base_point() -> tuple[int, int]:
    x_value = _recover_x(BASE_Y, 0)
    return x_value, BASE_Y


def _secret_scalar(seed: bytes) -> int:
    return _clamp_scalar(sha512(seed).digest()[:32])


def _clamp_scalar(value: bytes) -> int:
    buffer = bytearray(value)
    buffer[0] &= 248
    buffer[31] &= 63
    buffer[31] |= 64
    return int.from_bytes(buffer, "little")


def _hint(data: bytes) -> int:
    return int.from_bytes(sha512(data).digest(), "little") % GROUP_ORDER


def _inv(value: int) -> int:
    return pow(value, FIELD_MODULUS - 2, FIELD_MODULUS)


def _recover_x(y_value: int, x_sign: int) -> int:
    numerator = (y_value * y_value - 1) % FIELD_MODULUS
    denominator = (CURVE_D * y_value * y_value + 1) % FIELD_MODULUS
    x_value = pow(numerator * _inv(denominator), (FIELD_MODULUS + 3) // 8, FIELD_MODULUS)
    if (x_value * x_value - numerator * _inv(denominator)) % FIELD_MODULUS:
        x_value = (x_value * SQRT_M1) % FIELD_MODULUS
    if x_value % 2 != x_sign:
        x_value = FIELD_MODULUS - x_value
    return x_value


def _edwards_add(point_p: tuple[int, int], point_q: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = point_p
    x2, y2 = point_q
    factor = CURVE_D * x1 * x2 * y1 * y2
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + factor)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - factor)
    return x3 % FIELD_MODULUS, y3 % FIELD_MODULUS


def _scalar_mult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    if scalar == 0:
        return 0, 1
    half = _scalar_mult(point, scalar // 2)
    doubled = _edwards_add(half, half)
    return doubled if scalar % 2 == 0 else _edwards_add(doubled, point)


def _encode_point(point: tuple[int, int]) -> bytes:
    x_value, y_value = point
    encoded = y_value | ((x_value & 1) << 255)
    return encoded.to_bytes(32, "little")


def _decode_point(data: bytes) -> tuple[int, int]:
    y_value = int.from_bytes(data, "little") & ((1 << 255) - 1)
    x_value = _recover_x(y_value, data[31] >> 7)
    point = x_value, y_value
    if not _is_on_curve(point):
        raise ValueError("point is not on the Ed25519 curve")
    return point


def _is_on_curve(point: tuple[int, int]) -> bool:
    x_value, y_value = point
    left = (-x_value * x_value + y_value * y_value - 1) % FIELD_MODULUS
    right = (CURVE_D * x_value * x_value * y_value * y_value) % FIELD_MODULUS
    return left == right
