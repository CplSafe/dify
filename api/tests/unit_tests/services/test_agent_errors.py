def test_agent_errors_are_importable_and_distinct():
    from services.errors.agent import (
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
