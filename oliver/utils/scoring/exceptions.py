"""Expected domain errors raised by canonical assessment input handling."""


class UnassessableEmailError(ValueError):
    """The latest email has no usable participant-authored assessment content."""
