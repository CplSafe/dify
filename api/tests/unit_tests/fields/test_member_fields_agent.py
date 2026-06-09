"""Verify Account profile schema exposes is_agent + agent_status."""


def test_account_response_schema_declares_agent_fields():
    """The Pydantic ``Account`` schema must declare ``is_agent`` and
    ``agent_status`` so the serialised /account/profile response carries
    them. The frontend reads these to decide whether to redirect to
    /agent/dashboard on login.
    """
    from fields.member_fields import Account

    fields = Account.model_fields
    assert "is_agent" in fields
    assert "agent_status" in fields

    # is_agent defaults to False (normal users)
    assert fields["is_agent"].default is False
    # agent_status optional, defaults to None
    assert fields["agent_status"].default is None


def test_account_response_serializes_with_agent_fields():
    """Serializing an object exposing is_agent / agent_status produces
    those keys in the JSON output (and they have the right values)."""
    from types import SimpleNamespace

    from fields.member_fields import Account

    fake_account = SimpleNamespace(
        id="acct-1",
        name="X",
        email="x@x.com",
        is_password_set=True,
        is_system_admin=False,
        is_agent=True,
        agent_status="active",
        interface_language=None,
        interface_theme=None,
        timezone=None,
        last_login_at=None,
        last_login_ip=None,
        created_at=None,
        avatar=None,
        avatar_url=None,
    )
    out = Account.model_validate(fake_account, from_attributes=True).model_dump(mode="json")
    assert out["is_agent"] is True
    assert out["agent_status"] == "active"
