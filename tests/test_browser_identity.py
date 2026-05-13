from ali_mvp.browser_identity import BrowserIdentityWarning, validate_browser_identity


def test_validate_browser_identity_returns_user_agent_major_mismatch_warning():
    warning = validate_browser_identity(
        configured_user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        configured_accept_language="en-US,en;q=0.9",
        effective_user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        effective_language="en-US",
        effective_languages=["en-US", "en"],
    )

    assert warning == BrowserIdentityWarning(
        code="user_agent_major_mismatch",
        configured={"user_agent_major": 124},
        effective={"user_agent_major": 126},
    )


def test_validate_browser_identity_returns_accept_language_mismatch_warning():
    warning = validate_browser_identity(
        configured_user_agent="",
        configured_accept_language="en-US,en;q=0.9",
        effective_user_agent="",
        effective_language="fr-FR",
        effective_languages=["fr-FR", "fr"],
    )

    assert warning == BrowserIdentityWarning(
        code="accept_language_mismatch",
        configured={"accept_language_primary": "en-US"},
        effective={"navigator_language": "fr-FR"},
    )


def test_validate_browser_identity_falls_back_to_effective_languages_when_language_is_empty():
    warning = validate_browser_identity(
        configured_user_agent="",
        configured_accept_language="en-US,en;q=0.9",
        effective_user_agent="",
        effective_language="",
        effective_languages=["fr-FR", "fr"],
    )

    assert warning == BrowserIdentityWarning(
        code="accept_language_mismatch",
        configured={"accept_language_primary": "en-US"},
        effective={"navigator_language": "fr-FR"},
    )


def test_validate_browser_identity_returns_none_when_identity_is_consistent():
    warning = validate_browser_identity(
        configured_user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        configured_accept_language="en-US,en;q=0.9",
        effective_user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        effective_language="en-US",
        effective_languages=["en-US", "en"],
    )

    assert warning is None
