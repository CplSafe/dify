"""Domain exceptions for the agent system."""
from services.errors.base import BaseServiceError


class AgentError(BaseServiceError):
    """Base class for agent-system domain errors."""


class AgentNotFoundError(AgentError):
    pass


class AgentSuspendedError(AgentError):
    pass


class AgentAccountAlreadyExistsError(AgentError):
    """The given account is already registered as an agent."""


class InvalidAgentInvitationCodeError(AgentError):
    pass


class AlreadyBoundError(AgentError):
    """Customer already bound to an agent — caller should switch to rebind flow."""


class SelfBindError(AgentError):
    """An agent cannot bind themselves as their own invitee."""


class RebindCooldownActiveError(AgentError):
    """90-day cooldown after a previous approved rebind has not elapsed."""


class DuplicatePendingRebindError(AgentError):
    pass


class RebindRequestNotFoundError(AgentError):
    pass


class WithdrawalAmountTooSmallError(AgentError):
    pass


class InsufficientWithdrawableBalanceError(AgentError):
    pass


class DuplicatePendingWithdrawalError(AgentError):
    pass


class WithdrawalRequestNotFoundError(AgentError):
    pass
