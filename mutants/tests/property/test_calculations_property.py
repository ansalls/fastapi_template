import pytest
from app.calculations import (
    BankAccount,
    InsufficientFunds,
    add,
    divide,
    multiply,
    subtract,
)
from hypothesis import given
from hypothesis import strategies as st

pytestmark = [pytest.mark.unit, pytest.mark.property]


@given(st.integers(min_value=-10_000, max_value=10_000), st.integers(min_value=-10_000, max_value=10_000))
def test_add_is_commutative(a: int, b: int):
    assert add(a, b) == add(b, a)


@given(st.integers(min_value=-10_000, max_value=10_000), st.integers(min_value=-10_000, max_value=10_000))
def test_multiply_is_commutative(a: int, b: int):
    assert multiply(a, b) == multiply(b, a)


@given(st.integers(min_value=-10_000, max_value=10_000), st.integers(min_value=-10_000, max_value=10_000))
def test_subtract_reverses_add(a: int, b: int):
    assert subtract(add(a, b), b) == a


@given(
    st.integers(min_value=-1_000, max_value=1_000),
    st.integers(min_value=-1_000, max_value=1_000).filter(lambda x: x != 0),
)
def test_divide_reverses_multiply_for_non_zero(a: int, b: int):
    assert divide(multiply(a, b), b) == a


@given(
    st.integers(min_value=0, max_value=1_000_000),
    st.integers(min_value=0, max_value=1_000_000),
)
def test_deposit_and_withdraw_same_amount_preserves_balance(
    starting_balance: int, amount: int
):
    account = BankAccount(starting_balance)
    account.deposit(amount)
    account.withdraw(amount)
    assert account.balance == starting_balance


@given(
    st.integers(min_value=0, max_value=1_000_000),
    st.integers(min_value=1, max_value=1_000_000),
)
def test_withdraw_more_than_balance_raises(
    starting_balance: int, extra_amount: int
):
    account = BankAccount(starting_balance)
    with pytest.raises(InsufficientFunds):
        account.withdraw(starting_balance + extra_amount)
