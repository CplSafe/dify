def test_agent_errors_are_importable_and_distinct():
    """Verify the full domain-exception surface exists and inherits correctly.

    Imports are intentionally "unused" — their presence IS the test:
    a missing class would surface as ImportError here before any service
    code that depends on it even loads.
    """
    from services.errors.agent import (  # noqa: F401
        AgentAccountAlreadyExistsError,
        AgentError,
        AgentNotFoundError,
        AgentSuspendedError,
        AlreadyBoundError,
        DuplicatePendingRebindError,
        DuplicatePendingWithdrawalError,
        InsufficientWithdrawableBalanceError,
        InvalidAgentInvitationCodeError,
        RebindCooldownActiveError,
        RebindRequestNotFoundError,
        SelfBindError,
        WithdrawalAmountTooSmallError,
        WithdrawalRequestNotFoundError,
    )
    from services.errors.base import BaseServiceError

    assert issubclass(AgentNotFoundError, AgentError)
    assert issubclass(AgentSuspendedError, AgentError)
    assert issubclass(AgentError, BaseServiceError)
